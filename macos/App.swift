import SwiftUI
import AppKit
import Foundation

private enum Theme {
    static let bg = Color(red: 0.075, green: 0.025, blue: 0.035)
    static let panel = Color(red: 0.125, green: 0.055, blue: 0.068)
    static let panel2 = Color(red: 0.16, green: 0.07, blue: 0.082)
    static let red = Color(red: 0.96, green: 0.19, blue: 0.23)
    static let muted = Color(red: 0.73, green: 0.64, blue: 0.65)
    static let stroke = Color.white.opacity(0.08)
}

private struct BackendEvent: Decodable {
    let type: String
    let message: String?
    let current: Int?
    let total: Int?
    let failed: Int?
}

private final class StreamBuffer: @unchecked Sendable {
    var bytes = Data()
}

@MainActor
final class DownloadModel: ObservableObject {
    @Published var url = ""
    @Published var mode = "playlist"
    @Published var quality = "320"
    @Published var destination = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first?.path ?? FileManager.default.homeDirectoryForCurrentUser.path
    @Published var newFolder = ""
    @Published var artwork = true
    @Published var workers = 6
    @Published var mounted = false
    @Published var testing = false
    @Published var capacityText: String?
    @Published var running = false
    @Published var completed = false
    @Published var stopping = false
    @Published var status = "Listo para comenzar"
    @Published var song = ""
    @Published var progress: Double?
    @Published var completedCount: Int?
    @Published var totalCount: Int?
    @Published var log: [String] = []
    @Published var showLog = false
    @Published var errorMessage: String?
    private var timer: Timer?
    private var task: Process?
    private var terminationObserver: NSObjectProtocol?
    private let outputQueue = DispatchQueue(label: "com.pendrive.music.output")
    private var lastEventType = ""

    init() {
        refreshVolume()
        terminationObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.stop() }
        }
        timer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refreshVolume() }
        }
    }

    deinit {
        timer?.invalidate()
        if let terminationObserver {
            NotificationCenter.default.removeObserver(terminationObserver)
        }
    }

    var canStart: Bool {
        mounted && !testing && !running && !url.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    func refreshVolume() {
        let targetURL = URL(fileURLWithPath: destination, isDirectory: true).standardizedFileURL
        let target = targetURL.path
        var isDirectory: ObjCBool = false
        let found = FileManager.default.fileExists(atPath: target, isDirectory: &isDirectory) && isDirectory.boolValue
        mounted = found
        let volumeURL = (try? targetURL.resourceValues(forKeys: [.volumeURLKey]))?.volume
        testing = found && volumeURL.map { FileManager.default.fileExists(atPath: $0.appendingPathComponent("1.h2w").path) } == true
        guard found else {
            capacityText = nil
            return
        }
        do {
            let info = try FileManager.default.attributesOfFileSystem(forPath: destination)
            guard let total = (info[.systemSize] as? NSNumber)?.doubleValue,
                  let available = (info[.systemFreeSize] as? NSNumber)?.doubleValue,
                  total > 0, available >= 0 else {
                capacityText = "Capacidad no disponible"
                return
            }
            let locale = Locale(identifier: "es_ES")
            let totalGB = String(format: "%.1f", locale: locale, total / 1_000_000_000)
            let freeGB = String(format: "%.1f", locale: locale, available / 1_000_000_000)
            capacityText = "\(totalGB) GB en total · \(freeGB) GB libres"
        } catch {
            capacityText = "Capacidad no disponible"
        }
    }

    func start() {
        refreshVolume()
        let value = url.trimmingCharacters(in: .whitespacesAndNewlines)
        guard mounted else { errorMessage = "Elige una carpeta disponible en el Mac o conecta el pendrive."; return }
        guard !testing else { errorMessage = "El volumen contiene archivos de una prueba F3. Espera a que termine y se limpien antes de descargar."; return }
        guard let parts = URLComponents(string: value), parts.scheme == "https", let host = parts.host?.lowercased(), ["youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com", "youtu.be"].contains(host) else {
            errorMessage = "Pega un enlace HTTPS de YouTube o YouTube Music."
            return
        }
        guard let resource = Bundle.main.resourceURL else { errorMessage = "No se encontró el motor de descarga."; return }
        let backend = resource.appendingPathComponent("backend.py")
        guard FileManager.default.fileExists(atPath: backend.path) else { errorMessage = "Falta el motor de descarga dentro de la app."; return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        let folderName = newFolder.trimmingCharacters(in: .whitespacesAndNewlines)
        p.arguments = ["-u", backend.path, "--url", value, "--mode", mode, "--quality", quality, "--destination", destination, "--workers", String(workers)] + (artwork ? ["--artwork"] : []) + (folderName.isEmpty ? [] : ["--new-folder", folderName])
        var env = ProcessInfo.processInfo.environment
        env["PYTHONUNBUFFERED"] = "1"
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        p.environment = env
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        let accumulator = StreamBuffer()
        log = []
        song = ""
        progress = nil
        completed = false
        completedCount = nil
        totalCount = nil
        lastEventType = ""
        status = "Preparando descarga…"
        stopping = false
        running = true
        task = p
        let handle = pipe.fileHandleForReading
        handle.readabilityHandler = { [weak self] file in
            let data = file.availableData
            guard !data.isEmpty else { return }
            self?.outputQueue.async { [weak self] in
                guard let self = self else { return }
                accumulator.bytes.append(data)
                while let index = accumulator.bytes.firstIndex(of: 10) {
                    let lineData = accumulator.bytes.prefix(upTo: index)
                    accumulator.bytes.removeSubrange(...index)
                    let text = String(data: lineData, encoding: .utf8) ?? ""
                    DispatchQueue.main.async { [weak self] in self?.receive(text) }
                }
            }
        }
        p.terminationHandler = { [weak self] proc in
            handle.readabilityHandler = nil
            let remaining = handle.readDataToEndOfFile()
            self?.outputQueue.async { [weak self] in
                guard let self = self else { return }
                accumulator.bytes.append(remaining)
                let tail = String(data: accumulator.bytes, encoding: .utf8) ?? ""
                accumulator.bytes.removeAll()
                let lines = tail.split(separator: "\n").map(String.init)
                DispatchQueue.main.async { [weak self] in
                    guard let self = self else { return }
                    for line in lines { self.receive(line) }
                    self.running = false
                    if self.stopping { self.status = "Descarga detenida" }
                    else if proc.terminationStatus == 0 && self.lastEventType != "done" { self.status = "Descarga terminada" }
                    else if proc.terminationStatus != 0 && !["done", "error"].contains(self.lastEventType) { self.status = "No se pudo completar la descarga" }
                    self.task = nil
                    self.stopping = false
                    self.refreshVolume()
                }
            }
        }
        do { try p.run() }
        catch {
            handle.readabilityHandler = nil
            task = nil; running = false
            status = "No se pudo iniciar la descarga"
            errorMessage = error.localizedDescription
        }
    }

    func stop() {
        guard running, !stopping, let task = task else { return }
        stopping = true
        status = "Deteniendo de forma segura…"
        if task.isRunning { task.terminate() }
    }

    private func receive(_ line: String) {
        guard !line.isEmpty else { return }
        let event = line.data(using: .utf8).flatMap { try? JSONDecoder().decode(BackendEvent.self, from: $0) }
        let message = event?.message ?? line
        if !message.isEmpty {
            log.append(message)
            if log.count > 150 { log.removeFirst(log.count - 150) }
            lastEventType = event?.type ?? ""
            if event?.type == "error" { status = "Error: " + message; showLog = true }
            else if event?.type == "status" {
                status = message
                if let current = event?.current, let total = event?.total, total > 0 {
                    song = ""
                    completedCount = current
                    totalCount = total
                    progress = min(max(Double(current) / Double(total), 0), 1)
                }
            }
            else if event?.type == "progress" {
                if let range = message.range(of: #"[0-9]+(?:\.[0-9]+)?%"#, options: .regularExpression),
                   let amount = Double(message[range].dropLast()) {
                    status = "Descargando audio · \(Int(amount)) %"
                } else if message.contains("ExtractAudio") { status = "Convirtiendo a MP3…" }
            }
            else if event?.type == "done" {
                status = message
                completed = event?.failed == 0
                if completed { progress = 1 }
            }
        }
    }
}

private struct StatusPill: View {
    var label: String
    var icon: String
    var color: Color
    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: icon).font(.system(size: 11, weight: .bold))
            Text(label).font(.system(size: 11, weight: .semibold))
        }
        .foregroundStyle(color)
        .padding(.horizontal, 11).padding(.vertical, 7)
        .background(color.opacity(0.12), in: Capsule())
    }
}

private struct SectionNumber: View {
    let number: String
    var body: some View {
        Text(number).font(.system(size: 11, weight: .bold, design: .rounded))
            .foregroundStyle(Theme.red)
            .frame(width: 25, height: 25)
            .background(Theme.red.opacity(0.14), in: RoundedRectangle(cornerRadius: 8))
    }
}

private struct ModeChoice: View {
    let icon: String, title: String, subtitle: String
    let selected: Bool
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 13) {
                Image(systemName: icon).font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(selected ? Theme.red : Theme.muted)
                    .frame(width: 37, height: 37)
                    .background((selected ? Theme.red : Color.white).opacity(selected ? 0.13 : 0.05), in: RoundedRectangle(cornerRadius: 11))
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).font(.system(size: 13, weight: .bold)).foregroundStyle(.white)
                    Text(subtitle).font(.system(size: 11)).foregroundStyle(Theme.muted)
                }
                Spacer(minLength: 4)
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(selected ? Theme.red : Color.white.opacity(0.22))
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(selected ? Theme.red.opacity(0.08) : Color.white.opacity(0.025), in: RoundedRectangle(cornerRadius: 15))
            .overlay(RoundedRectangle(cornerRadius: 15).stroke(selected ? Theme.red.opacity(0.65) : Theme.stroke, lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

private struct MainView: View {
    @StateObject private var model = DownloadModel()
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var entertainment = "mascota"
    @State private var showEntertainment = true
    @State private var mascotWalk = false
    var body: some View {
        ZStack {
            LinearGradient(colors: [Color(red: 0.16, green: 0.035, blue: 0.045), Theme.bg, Color(red: 0.055, green: 0.025, blue: 0.033)], startPoint: .topLeading, endPoint: .bottomTrailing)
                .ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 23) {
                    header
                        .padding(showEntertainment && entertainment == "guerra" ? 12 : 0)
                        .background(Color.black.opacity(showEntertainment && entertainment == "guerra" ? 0.68 : 0), in: RoundedRectangle(cornerRadius: 15))
                    destinationCard
                    activityCard
                    inputCard
                    HStack {
                        Image(systemName: "info.circle")
                        Text("Descarga solo contenido que tengas permiso para guardar.")
                    }
                    .font(.system(size: 11)).foregroundStyle(Theme.muted.opacity(0.85))
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.bottom, 5)
                }
                .padding(.horizontal, 36).padding(.top, 28).padding(.bottom, 28)
                .frame(maxWidth: 810)
                .frame(maxWidth: .infinity)
            }
        }
        .preferredColorScheme(.dark)
        .onAppear {
            DispatchQueue.main.async { NSApp.keyWindow?.makeFirstResponder(nil) }
        }
        .onChange(of: model.destination) { _, _ in model.refreshVolume() }
        .background(SpaceKeyMonitor { showEntertainment.toggle() }.frame(width: 0, height: 0))
        .overlay(alignment: .topLeading) {
            if showEntertainment && entertainment == "mascota" && model.running {
                GeometryReader { geometry in
                    RobotView(progress: model.progress, running: model.running, completed: model.completed)
                        .frame(width: 145, height: 100)
                        .opacity(0.92)
                        .offset(x: mascotWalk ? max(0, geometry.size.width - 155) : 10,
                                y: mascotWalk ? max(120, geometry.size.height - 175) : 100)
                        .animation(reduceMotion ? nil : .linear(duration: 12).repeatForever(autoreverses: true), value: mascotWalk)
                        .onAppear { mascotWalk = !reduceMotion }
                        .onDisappear { mascotWalk = false }
                }
                .allowsHitTesting(false)
                .accessibilityHidden(true)
            }
        }
        .overlay {
            if showEntertainment && entertainment == "guerra" {
                WarSceneView(progress: model.progress, running: model.running,
                             completed: model.completed, showLabels: false, overlayMode: true)
                    .ignoresSafeArea()
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
        }
        .onDisappear { model.stop() }
        .frame(minWidth: 680, minHeight: 720)
        .alert("No se pudo continuar", isPresented: Binding(get: { model.errorMessage != nil }, set: { if !$0 { model.errorMessage = nil } })) {
            Button("Entendido", role: .cancel) { model.errorMessage = nil }
        } message: { Text(model.errorMessage ?? "") }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 15).fill(Theme.red.gradient).frame(width: 50, height: 50)
                Image(systemName: "music.note.list").font(.system(size: 22, weight: .bold)).foregroundStyle(.white)
            }.shadow(color: Theme.red.opacity(0.3), radius: 18, y: 5)
            VStack(alignment: .leading, spacing: 5) {
                Text("YA TU SAABE!! 🇩🇴").font(.system(size: 10, weight: .bold)).tracking(1.6).foregroundStyle(Theme.red)
                Text("Tu música, lista para el camino.").font(.system(size: 23, weight: .bold, design: .rounded)).foregroundStyle(.white)
                Text("Guarda canciones o playlists en tu Mac o pendrive.").font(.system(size: 13)).foregroundStyle(Theme.muted)
            }
            Spacer()
        }
    }

    private var destinationCard: some View {
        DestinationPicker(selection: $model.destination, newFolder: $model.newFolder,
                          translucent: showEntertainment && entertainment == "guerra")
            .disabled(model.running)
    }

    private var inputCard: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack(spacing: 9) {
                SectionNumber(number: "01")
                Text("¿Qué quieres descargar?").font(.system(size: 16, weight: .bold)).foregroundStyle(.white)
            }
            HStack(spacing: 10) {
                ModeChoice(icon: "music.note.list", title: "Una playlist", subtitle: "Todas las canciones", selected: model.mode == "playlist") { model.mode = "playlist" }
                ModeChoice(icon: "music.note", title: "Una canción", subtitle: "Solo un audio", selected: model.mode == "single") { model.mode = "single" }
            }
            .disabled(model.running)
            VStack(alignment: .leading, spacing: 9) {
                HStack(spacing: 9) {
                    SectionNumber(number: "02")
                    Text("Pega el enlace").font(.system(size: 15, weight: .bold)).foregroundStyle(.white)
                }
                HStack(spacing: 10) {
                    Image(systemName: "link").foregroundStyle(Theme.red).font(.system(size: 15, weight: .semibold))
                    TextField("https://music.youtube.com/...", text: $model.url)
                        .textFieldStyle(.plain).font(.system(size: 13))
                        .disabled(model.running)
                    if !model.url.isEmpty && !model.running {
                        Button { model.url = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.muted) }.buttonStyle(.plain)
                    }
                }
                .padding(15)
                .background(Color.black.opacity(0.21), in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.stroke))
            }
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Calidad de salida").font(.system(size: 13, weight: .bold))
                    Text("MP3 compatible con tu radio. La calidad final depende del audio original.")
                        .font(.system(size: 11)).foregroundStyle(Theme.muted)
                }
                Spacer()
                Picker("Calidad", selection: $model.quality) {
                    Text("Alta · 192 kbps").tag("192")
                    Text("Muy alta · 256 kbps").tag("256")
                    Text("Máxima · 320 kbps").tag("320")
                }
                .labelsHidden().frame(width: 171).disabled(model.running)
            }
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Velocidad de descarga").font(.system(size: 13, weight: .bold))
                    Text("Más canciones a la vez usan más internet.")
                        .font(.system(size: 11)).foregroundStyle(Theme.muted)
                }
                Spacer()
                Picker("Velocidad", selection: $model.workers) {
                    Text("Normal · 2 a la vez").tag(2)
                    Text("Rápida · 4 a la vez").tag(4)
                    Text("Máxima · 6 a la vez").tag(6)
                }
                .labelsHidden().frame(width: 190).disabled(model.running)
            }
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "photo.on.rectangle.angled")
                    .font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.red)
                    .frame(width: 32, height: 32)
                    .background(Theme.red.opacity(0.12), in: RoundedRectangle(cornerRadius: 9))
                VStack(alignment: .leading, spacing: 4) {
                    Text("Carátula de cada canción").font(.system(size: 13, weight: .bold))
                    Text("Se usa la mejor imagen disponible; puede no ser 4K. El radio puede reducirla o no mostrarla.")
                        .font(.system(size: 11)).foregroundStyle(Theme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 8)
                Toggle("Carátulas", isOn: $model.artwork)
                    .labelsHidden().toggleStyle(.switch).tint(Theme.red).disabled(model.running)
            }
            if model.testing {
                HStack(alignment: .top, spacing: 9) {
                    Image(systemName: "hourglass").foregroundStyle(.orange)
                    Text("La prueba de capacidad aún está usando el volumen. La descarga estará disponible cuando termine.")
                        .fixedSize(horizontal: false, vertical: true)
                }
                .font(.system(size: 12)).foregroundStyle(Color.orange.opacity(0.9))
                .padding(12).frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
            }
            if model.running {
                Button(action: model.stop) {
                    HStack { Image(systemName: "stop.fill"); Text(model.stopping ? "Deteniendo…" : "Detener descarga") }
                        .font(.system(size: 14, weight: .bold)).frame(maxWidth: .infinity).padding(.vertical, 14)
                        .background(Color.white.opacity(0.10), in: RoundedRectangle(cornerRadius: 12))
                }.buttonStyle(.plain).disabled(model.stopping)
            } else {
                Button(action: model.start) {
                    HStack(spacing: 9) { Image(systemName: "arrow.down.to.line.compact"); Text("Descargar música") }
                        .font(.system(size: 14, weight: .bold)).foregroundStyle(.white)
                        .frame(maxWidth: .infinity).padding(.vertical, 14)
                        .background(model.canStart ? Theme.red : Theme.red.opacity(0.3), in: RoundedRectangle(cornerRadius: 12))
                }.buttonStyle(.plain).disabled(!model.canStart)
            }
        }
        .padding(22)
        .background(Theme.panel.opacity(showEntertainment && entertainment == "guerra" ? 0.72 : 0.92), in: RoundedRectangle(cornerRadius: 19))
        .overlay(RoundedRectangle(cornerRadius: 19).stroke(Theme.stroke))
    }

    private var activityCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "waveform.path").foregroundStyle(Theme.red)
                Text("Actividad").font(.system(size: 14, weight: .bold))
                Spacer()
                if !model.log.isEmpty {
                    Button(model.showLog ? "Ocultar detalles" : "Ver detalles") { model.showLog.toggle() }
                        .buttonStyle(.plain).font(.system(size: 11, weight: .semibold)).foregroundStyle(Theme.muted)
                }
            }
            Picker("Entretenimiento", selection: $entertainment) {
                Text("🤖 Mascota interactiva").tag("mascota")
                Text("🌍 Guerra mundial 3D").tag("guerra")
            }
            .pickerStyle(.segmented)
            .accessibilityLabel("Elige qué ver durante la descarga")
            HStack {
                Spacer()
                Button(showEntertainment ? "Ocultar animación · Espacio fuera de campos" : "Mostrar animación · Espacio fuera de campos") {
                    showEntertainment.toggle()
                }
                .buttonStyle(.plain).font(.system(size: 11, weight: .semibold)).foregroundStyle(Theme.muted)
            }
            if showEntertainment && entertainment == "mascota" {
                RobotView(progress: model.progress, running: model.running, completed: model.completed)
                    .frame(maxWidth: .infinity)
                    .frame(height: model.running || model.completed ? 210 : 135)
                    .background(Color.black.opacity(0.13), in: RoundedRectangle(cornerRadius: 14))
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                Text("Toca al robot para saludarlo.")
                    .font(.system(size: 11)).foregroundStyle(Theme.muted)
                    .frame(maxWidth: .infinity, alignment: .center)
            } else if showEntertainment {
                HStack(spacing: 12) {
                    Image(systemName: "globe.americas.fill").font(.system(size: 23)).foregroundStyle(Theme.red)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(warCaption(progress: model.progress, running: model.running, completed: model.completed))
                            .font(.system(size: 13, weight: .bold)).foregroundStyle(.white)
                        Text(warFlags(progress: model.progress, running: model.running, completed: model.completed))
                            .font(.system(size: 12, weight: .semibold)).foregroundStyle(.white.opacity(0.92))
                        Text("Representación histórica simplificada · avanza con las canciones procesadas")
                            .font(.system(size: 11)).foregroundStyle(Theme.muted)
                    }
                    Spacer()
                }.padding(12).background(Color.black.opacity(0.35), in: RoundedRectangle(cornerRadius: 12))
            }
            HStack(alignment: .center, spacing: 12) {
                if model.running { ProgressView().controlSize(.small).tint(Theme.red) }
                else { Circle().fill(Theme.muted.opacity(0.45)).frame(width: 7, height: 7) }
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.status).font(.system(size: 12)).foregroundStyle(Theme.muted).lineLimit(3)
                    if model.running, let current = model.completedCount, let total = model.totalCount {
                        Text("\(current) de \(total) canciones procesadas")
                            .font(.system(size: 11, weight: .semibold)).foregroundStyle(.white.opacity(0.82))
                    } else if model.running {
                        Text("Preparando canciones…").font(.system(size: 11)).foregroundStyle(Theme.muted)
                    }
                }
                Spacer()
                if model.running, let progress = model.progress, model.totalCount != nil {
                    Text("\(Int((progress * 100).rounded())) %")
                        .font(.system(size: 13, weight: .bold, design: .rounded)).foregroundStyle(Theme.red)
                        .monospacedDigit()
                }
            }
            if model.running && !model.song.isEmpty && model.status != model.song {
                Text(model.song).font(.system(size: 11)).foregroundStyle(Theme.muted.opacity(0.85)).lineLimit(2)
            }
            if model.running, let progress = model.progress {
                ProgressView(value: progress).tint(Theme.red)
                    .animation(reduceMotion ? nil : .easeOut(duration: 0.25), value: progress)
                    .accessibilityLabel("Progreso de canciones procesadas")
            }
            if model.showLog {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(Array(model.log.enumerated()), id: \.offset) { idx, entry in
                                Text(entry).font(.system(size: 11, design: .monospaced)).foregroundStyle(Theme.muted).frame(maxWidth: .infinity, alignment: .leading).id(idx)
                            }
                        }
                    }
                    .frame(maxHeight: 120)
                    .onChange(of: model.log.count) { _, _ in if !model.log.isEmpty { proxy.scrollTo(model.log.count - 1, anchor: .bottom) } }
                }
            }
        }
        .padding(18)
        .background(Theme.panel.opacity(0.72), in: RoundedRectangle(cornerRadius: 17))
        .overlay(RoundedRectangle(cornerRadius: 17).stroke(Theme.stroke))
    }
}

private struct SpaceKeyMonitor: NSViewRepresentable {
    var toggle: () -> Void

    final class Coordinator {
        weak var view: NSView?
        var monitor: Any?
        var toggle: () -> Void
        init(toggle: @escaping () -> Void) { self.toggle = toggle }
        func install() {
            monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
                guard let self, let window = self.view?.window, event.window === window,
                      event.keyCode == 49, !event.isARepeat,
                      event.modifierFlags.intersection([.command, .control, .option]).isEmpty else { return event }
                if let editor = window.firstResponder as? NSTextView, editor.isFieldEditor { return event }
                if let control = window.firstResponder as? NSControl, !(control is NSTextField) { return event }
                self.toggle()
                return nil
            }
        }
        func remove() {
            if let monitor { NSEvent.removeMonitor(monitor); self.monitor = nil }
        }
        deinit { remove() }
    }
    func makeCoordinator() -> Coordinator { Coordinator(toggle: toggle) }
    func makeNSView(context: Context) -> NSView {
        let view = NSView(frame: .zero)
        context.coordinator.view = view
        context.coordinator.install()
        return view
    }
    func updateNSView(_ view: NSView, context: Context) { context.coordinator.toggle = toggle }
    static func dismantleNSView(_ view: NSView, coordinator: Coordinator) { coordinator.remove() }
}

@main
struct MusicaSubaruApp: App {
    var body: some Scene {
        Window("YA TU SAABE!!", id: "main") { MainView() }
            .windowStyle(.hiddenTitleBar)
            .defaultSize(width: 810, height: 820)
    }
}
