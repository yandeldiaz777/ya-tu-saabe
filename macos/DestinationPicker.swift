import SwiftUI
import AppKit
import Combine

/// Choose an existing destination without creating or writing anything.
/// The caller/backend validates and creates the optional child folder on download.
struct DestinationPicker: View {
    @Binding var selection: String
    @Binding var newFolder: String
    var translucent: Bool = false

    private let accent = Color(red: 0.96, green: 0.19, blue: 0.23)
    private let muted = Color(red: 0.73, green: 0.64, blue: 0.65)
    private let refreshTimer = Timer.publish(every: 3, on: .main, in: .common).autoconnect()
    @State private var volumeDetails: String?
    @State private var isAvailable = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center, spacing: 12) {
                Image(systemName: "externaldrive.fill")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(accent)
                    .frame(width: 42, height: 42)
                    .background(accent.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 4) {
                    Text("GUARDAR EN")
                        .font(.system(size: 10, weight: .bold)).tracking(1.1)
                        .foregroundStyle(muted)
                    Text(destinationTitle)
                        .font(.system(size: 14, weight: .bold)).foregroundStyle(.white)
                        .lineLimit(1).truncationMode(.middle)
                    Text(detailText)
                        .font(.system(size: 11)).foregroundStyle(isAvailable ? muted : .orange)
                        .lineLimit(2)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Button("Elegir carpeta…", action: chooseFolder)
                    .font(.system(size: 11, weight: .semibold))
                    .buttonStyle(.bordered)
                    .accessibilityHint("Selecciona una carpeta del Mac o de un pendrive conectado")
            }
            HStack(spacing: 9) {
                Image(systemName: "folder.badge.plus").foregroundStyle(accent)
                    .accessibilityHidden(true)
                TextField("Nueva carpeta (opcional)", text: $newFolder)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .accessibilityLabel("Nombre de nueva carpeta, opcional")
            }
            .padding(.horizontal, 12).padding(.vertical, 10)
            .background(Color.black.opacity(0.20), in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.white.opacity(0.08)))
            Text("Déjalo vacío para guardar directamente en la carpeta elegida.")
                .font(.system(size: 10)).foregroundStyle(muted)
        }
        .padding(18)
        .background(Color(red: 0.125, green: 0.055, blue: 0.068).opacity(translucent ? 0.72 : 0.95), in: RoundedRectangle(cornerRadius: 19))
        .overlay(RoundedRectangle(cornerRadius: 19).stroke(Color.white.opacity(0.08)))
        .onAppear(perform: refreshVolume)
        .onChange(of: selection) { _, _ in refreshVolume() }
        .onReceive(refreshTimer) { _ in refreshVolume() }
    }

    private var destinationTitle: String {
        guard !selection.isEmpty else { return "Elige una carpeta" }
        let url = URL(fileURLWithPath: selection, isDirectory: true).standardizedFileURL
        return url.path == "/" ? "Macintosh HD" : (url.lastPathComponent.isEmpty ? url.path : url.lastPathComponent)
    }

    private var detailText: String {
        guard !selection.isEmpty else { return "Puedes elegir el Mac o un pendrive." }
        guard isAvailable else { return "Carpeta no disponible. Elige otra o conecta el dispositivo." }
        let displayPath = (selection as NSString).abbreviatingWithTildeInPath
        return [displayPath, volumeDetails].compactMap { $0 }.joined(separator: " · ")
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.title = "Dónde guardar tu música"
        panel.message = "Selecciona una carpeta en el Mac o en un pendrive."
        panel.prompt = "Usar esta carpeta"
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = true
        if !selection.isEmpty, FileManager.default.fileExists(atPath: selection) {
            panel.directoryURL = URL(fileURLWithPath: selection, isDirectory: true)
        }
        if panel.runModal() == .OK, let url = panel.url {
            selection = url.standardizedFileURL.path
        }
    }

    private func refreshVolume() {
        var isDirectory: ObjCBool = false
        isAvailable = !selection.isEmpty && FileManager.default.fileExists(atPath: selection, isDirectory: &isDirectory) && isDirectory.boolValue
        guard isAvailable else { volumeDetails = nil; return }
        let url = URL(fileURLWithPath: selection, isDirectory: true)
        let volumeName = (try? url.resourceValues(forKeys: [.volumeNameKey]))?.volumeName
        guard let attrs = try? FileManager.default.attributesOfFileSystem(forPath: selection),
              let size = (attrs[.systemSize] as? NSNumber)?.doubleValue,
              let free = (attrs[.systemFreeSize] as? NSNumber)?.doubleValue,
              size > 0, free >= 0 else {
            volumeDetails = volumeName
            return
        }
        let locale = Locale(identifier: "es_ES")
        let totalGB = String(format: "%.1f", locale: locale, size / 1_000_000_000)
        let freeGB = String(format: "%.1f", locale: locale, free / 1_000_000_000)
        let capacity = "\(freeGB) GB libres de \(totalGB) GB"
        volumeDetails = [volumeName, capacity].compactMap { $0 }.joined(separator: " · ")
    }
}
