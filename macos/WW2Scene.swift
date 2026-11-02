import SwiftUI
import SceneKit
import AppKit

/// A stylized, non-graphic historical illustration; progress is controlled by the download.
struct WarSceneView: View {
    var progress: Double?
    var running: Bool
    var completed: Bool = false
    var showLabels: Bool = true
    var overlayMode: Bool = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var step: WarChapter { resolveWarChapter(progress: progress, running: running, completed: completed) }

    var body: some View {
        GeometryReader { geo in
            let compact = geo.size.height < 480
            ZStack {
                if !overlayMode { Color(red:0.025, green:0.043, blue:0.058) }
                WarWorldScene(chapter: step, reduceMotion: reduceMotion, overlayMode: overlayMode)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("Mapa tridimensional esquemático. \(step.accessibility)")
                if showLabels {
                    LinearGradient(colors:[.black.opacity(0.70),.clear,.clear,.black.opacity(0.62)], startPoint:.top, endPoint:.bottom)
                        .allowsHitTesting(false)
                    VStack(alignment:.leading, spacing:0) {
                    HStack(alignment:.top) {
                        VStack(alignment:.leading, spacing:8) {
                            HStack(spacing:8) {
                                Circle().fill(Color(red:0.91,green:0.32,blue:0.20)).frame(width:7,height:7)
                                Text("ATLAS · 1939–1945").tracking(2).font(.system(size:11,weight:.bold,design:.rounded))
                            }.foregroundStyle(Color(red:0.95,green:0.72,blue:0.53))
                            Text("Segunda Guerra Mundial")
                                .font(.system(size: compact ? 18 : min(max(geo.size.width * 0.032, 22), 38),weight:.bold,design:.rounded))
                                .foregroundStyle(.white)
                            if !compact {
                                Text("Una historia en movimiento")
                                    .font(.system(size:13)).foregroundStyle(.white.opacity(0.63))
                            }
                        }
                        Spacer(minLength:30)
                        if !compact {
                            Text("VISTA 3D")
                                .font(.system(size:10,weight:.bold)).tracking(1.2)
                                .foregroundStyle(.white.opacity(0.75)).padding(.horizontal,12).padding(.vertical,8)
                                .background(.white.opacity(0.10),in:Capsule())
                        }
                    }
                    Spacer()
                    HStack(alignment:.bottom,spacing:24) {
                        VStack(alignment:.leading,spacing:7) {
                            Text(step.period)
                                .font(.system(size:11,weight:.bold)).tracking(1.4)
                                .foregroundStyle(Color(red:1,green:0.57,blue:0.40))
                            Text(step.title)
                                .font(.system(size:compact ? 16 : min(max(geo.size.width * 0.024, 20), 29),weight:.bold,design:.rounded))
                                .foregroundStyle(.white)
                            Text(step.summary)
                                .font(.system(size:compact ? 11 : 13)).foregroundStyle(.white.opacity(0.78))
                                .fixedSize(horizontal:false,vertical:true).frame(maxWidth:640,alignment:.leading)
                        }
                        Spacer(minLength:15)
                        if running, let p=progress {
                            Text("\(Int((max(0,min(1,p))*100).rounded())) %")
                                .font(.system(size:23,weight:.bold,design:.rounded)).monospacedDigit()
                                .foregroundStyle(.white)
                        }
                    }
                    .padding(.bottom,compact ? 8 : 20)
                    GeometryReader { track in
                        ZStack(alignment:.leading) {
                            Capsule().fill(.white.opacity(0.15))
                            if let p=progress, running || completed {
                                Capsule().fill(LinearGradient(colors:[Color(red:0.90,green:0.23,blue:0.19),Color(red:1,green:0.64,blue:0.35)],startPoint:.leading,endPoint:.trailing))
                                    .frame(width:track.size.width*max(0,min(1,p)))
                                    .animation(reduceMotion ? nil : .easeInOut(duration:0.4),value:p)
                            }
                        }
                    }.frame(height:4)
                    HStack {
                        Text("Representación esquemática · La cronología avanza con las canciones procesadas")
                        Spacer()
                        if !running && !completed { Text("Esperando la descarga") }
                    }.font(.system(size:compact ? 9 : 10)).foregroundStyle(.white.opacity(0.48)).padding(.top,compact ? 4 : 10)
                    }
                    .padding(.horizontal,compact ? 18 : max(30,geo.size.width*0.055))
                    .padding(.top,compact ? 15 : max(38,geo.size.height*0.06))
                    .padding(.bottom,compact ? 12 : max(30,geo.size.height*0.045))
                    .allowsHitTesting(false)
                }
            }.ignoresSafeArea()
        }
    }
}

private func resolveWarChapter(progress: Double?, running: Bool, completed: Bool) -> WarChapter {
    guard running || completed else { return .waiting }
    guard let p = progress ?? (completed ? 1 : nil) else { return .waiting }
    switch min(max(p, 0), 1) {
    case ..<0.16: return .poland
    case ..<0.31: return .west
    case ..<0.48: return .global
    case ..<0.64: return .africaPacific
    case ..<0.80: return .normandy
    case ..<0.95: return .europeEnd
    default: return .japanEnd
    }
}

func warCaption(progress: Double?, running: Bool, completed: Bool = false) -> String {
    let chapter = resolveWarChapter(progress:progress, running:running, completed:completed)
    return "\(chapter.period) · \(chapter.title)"
}

/// Persistent text accompaniment for compact displays and VoiceOver.
/// A red square identifies the historical USSR without using today's Russian flag.
func warFlags(progress: Double?, running: Bool, completed: Bool = false) -> String {
    switch resolveWarChapter(progress: progress, running: running, completed: completed) {
    case .waiting: return "🌍 1939–1945"
    case .poland: return "🇵🇱 Polonia"
    case .west: return "🇫🇷 Francia"
    case .global: return "🟥 URSS  ·  🇺🇸 Estados Unidos"
    case .africaPacific: return "🇯🇵 Japón  ·  🇺🇸 Estados Unidos  ·  Norte de África"
    case .normandy: return "🇫🇷 Francia"
    case .europeEnd: return "🏳️ Alemania · rendición"
    case .japanEnd: return "🇯🇵 Japón"
    }
}

private enum WarChapter: Int, Equatable {
    case waiting, poland, west, global, africaPacific, normandy, europeEnd, japanEnd
    var period:String {
        switch self {
        case .waiting: return "1939 — 1945"
        case .poland: return "1939 · COMIENZO"
        case .west: return "1940 · EUROPA OCCIDENTAL"
        case .global: return "1941 · LA GUERRA SE EXTIENDE"
        case .africaPacific: return "1942–1943 · VARIOS FRENTES"
        case .normandy: return "1944 · EUROPA"
        case .europeEnd: return "1945 · EUROPA"
        case .japanEnd: return "1945 · PACÍFICO"
        }
    }
    var title:String {
        switch self {
        case .waiting: return "Un recorrido por seis años de historia"
        case .poland: return "La invasión de Polonia"
        case .west: return "La guerra llega al oeste"
        case .global: return "Un conflicto mundial"
        case .africaPacific: return "África y el Pacífico"
        case .normandy: return "El desembarco de Normandía"
        case .europeEnd: return "El fin de la guerra en Europa"
        case .japanEnd: return "Hiroshima, Nagasaki y el final"
        }
    }
    var summary:String {
        switch self {
        case .waiting: return "Inicia una playlist para recorrer los acontecimientos a medida que se descargan las canciones."
        case .poland: return "Alemania invade Polonia y comienza la guerra en Europa."
        case .west: return "La ofensiva alemana alcanza Europa occidental; el Reino Unido continúa en guerra."
        case .global: return "Alemania invade la Unión Soviética y el ataque japonés a Pearl Harbor amplía la guerra."
        case .africaPacific: return "Las campañas se desarrollan en el norte de África y en el océano Pacífico."
        case .normandy: return "Las fuerzas aliadas desembarcan en Francia y avanzan hacia el este."
        case .europeEnd: return "Las fuerzas aliadas avanzan hacia Alemania, que se rinde en mayo."
        case .japanEnd: return "Estados Unidos lanza bombas atómicas sobre Hiroshima y Nagasaki. Japón se rinde en 1945."
        }
    }
    var accessibility:String { "\(period). \(title). \(summary)" }
}

private struct WarWorldScene: NSViewRepresentable {
    var chapter: WarChapter
    var reduceMotion: Bool
    var overlayMode: Bool
    func makeCoordinator() -> WarStage { WarStage() }
    func makeNSView(context: Context) -> SCNView {
        let view=SCNView(frame:.zero)
        view.scene=context.coordinator.scene
        view.wantsLayer=true
        view.layer?.isOpaque=false
        view.backgroundColor = overlayMode ? .clear : NSColor(calibratedRed:0.025,green:0.043,blue:0.058,alpha:1)
        view.allowsCameraControl=true
        view.autoenablesDefaultLighting=false
        view.antialiasingMode = .multisampling2X
        view.preferredFramesPerSecond=24
        view.isPlaying = !reduceMotion
        view.rendersContinuously = !reduceMotion
        context.coordinator.setOverlay(overlayMode)
        context.coordinator.show(chapter, reduced:reduceMotion)
        return view
    }
    func updateNSView(_ view:SCNView, context:Context) {
        view.backgroundColor = overlayMode ? .clear : NSColor(calibratedRed:0.025,green:0.043,blue:0.058,alpha:1)
        context.coordinator.setOverlay(overlayMode)
        context.coordinator.show(chapter, reduced:reduceMotion)
        view.preferredFramesPerSecond = chapter == .waiting ? 8 : 24
        view.rendersContinuously = !reduceMotion
        view.isPlaying = !reduceMotion
    }
    static func dismantleNSView(_ view:SCNView, coordinator:WarStage) {
        view.isPlaying=false; view.rendersContinuously=false; view.scene=nil
    }
}

private final class WarStage: NSObject {
    let scene=SCNScene()
    private let chapterRoot=SCNNode()
    private let cameraNode=SCNNode()
    private let oceanNode=SCNNode()
    private let terrainNode=SCNNode()
    private let foregroundRoot=SCNNode()
    private var active:WarChapter?
    private var reduced=false
    private var overlayActive=false

    override init() { super.init(); buildWorld() }
    private func color(_ r:CGFloat,_ g:CGFloat,_ b:CGFloat,_ a:CGFloat=1) -> NSColor { NSColor(calibratedRed:r,green:g,blue:b,alpha:a) }
    private func material(_ c:NSColor, emissive:CGFloat=0) -> SCNMaterial {
        let m=SCNMaterial(); m.diffuse.contents=c; m.lightingModel = .blinn
        m.specular.contents=NSColor(white:0.4,alpha:1); m.shininess=28
        if emissive > 0 { m.emission.contents=c.withAlphaComponent(emissive) }
        return m
    }
    private func box(_ w:CGFloat,_ h:CGFloat,_ d:CGFloat,_ c:NSColor,_ radius:CGFloat=0.04) -> SCNNode {
        let geo=SCNBox(width:w,height:h,length:d,chamferRadius:radius); geo.materials=[material(c)]
        return SCNNode(geometry:geo)
    }
    private func ball(_ r:CGFloat,_ c:NSColor) -> SCNNode {
        let geo=SCNSphere(radius:r); geo.segmentCount=20; geo.materials=[material(c)]; return SCNNode(geometry:geo)
    }
    private func pt(_ lon:Float,_ lat:Float,_ y:Float=0.31) -> SCNVector3 {
        SCNVector3(lon/180*9.4,y,-lat/90*4.7)
    }
    private func buildWorld() {
        scene.background.contents=color(0.025,0.043,0.058)
        cameraNode.camera=SCNCamera(); cameraNode.camera!.usesOrthographicProjection=true
        cameraNode.camera!.orthographicScale=6.2; cameraNode.camera!.zFar=100
        cameraNode.position=SCNVector3(0,17,17); cameraNode.look(at:SCNVector3(0,0,0))
        cameraNode.addChildNode(foregroundRoot)
        scene.rootNode.addChildNode(cameraNode)
        let ambient=SCNNode(); ambient.light=SCNLight(); ambient.light!.type = .ambient
        ambient.light!.color=NSColor(white:0.72,alpha:1); scene.rootNode.addChildNode(ambient)
        let sun=SCNNode(); sun.light=SCNLight(); sun.light!.type = .directional
        sun.light!.color=NSColor(white:0.88,alpha:1); sun.eulerAngles=SCNVector3(-0.9,0.5,0)
        scene.rootNode.addChildNode(sun)
        // Extend the ocean beyond the terrain's edges so the camera can approach
        // Japan without exposing an artificial rectangular board against black.
        let sea=SCNPlane(width:90,height:60)
        let seaMaterial=SCNMaterial(); seaMaterial.diffuse.contents=color(0.503633,0.728262,0.860924)
        seaMaterial.lightingModel = .constant; seaMaterial.isDoubleSided=true; sea.materials=[seaMaterial]
        let ocean=SCNNode(geometry:sea); ocean.eulerAngles.x = -.pi/2; ocean.position.y = -0.03
        oceanNode.addChildNode(ocean); scene.rootNode.addChildNode(oceanNode)
        terrainNode.addChildNode(makeTerrain()); scene.rootNode.addChildNode(terrainNode)
        scene.rootNode.addChildNode(chapterRoot)
    }
    func setOverlay(_ overlay: Bool) {
        if overlayActive != overlay { overlayActive=overlay; active=nil }
        scene.background.contents = overlay ? NSColor.clear : color(0.025,0.043,0.058)
        oceanNode.opacity = overlay ? 0.12 : 1
        terrainNode.opacity = overlay ? 0.18 : 1
    }
    private func makeTerrain() -> SCNNode {
        // Natural Earth II, public domain, supplies land cover and shaded relief.
        // Heights derived from its colors are illustrative, not a terrain survey.
        let url=Bundle.main.url(forResource:"WW2Map",withExtension:"png")
        let img=url.flatMap { NSImage(contentsOf:$0) }
        let bitmap=url.flatMap { try? Data(contentsOf:$0) }.flatMap { NSBitmapImageRep(data:$0) }
        let nx=180, ny=90
        var vertices=[SCNVector3](), uvs=[CGPoint](), indices=[Int32]()
        vertices.reserveCapacity((nx+1)*(ny+1)); uvs.reserveCapacity((nx+1)*(ny+1))
        for j in 0...ny {
            for i in 0...nx {
                let u=Float(i)/Float(nx), v=Float(j)/Float(ny)
                var height:Float=0.015
                if let bitmap, let sample=bitmap.colorAt(x:min(bitmap.pixelsWide-1,Int(u*Float(bitmap.pixelsWide-1))), y:min(bitmap.pixelsHigh-1,Int(v*Float(bitmap.pixelsHigh-1))))?.usingColorSpace(.deviceRGB) {
                    let r=sample.redComponent, g=sample.greenComponent, b=sample.blueComponent
                    let water = b > g*1.08 && b > r*1.25
                    if !water {
                        let luminance = (r+g+b)/3
                        height=Float(0.055 + max(0,luminance-0.52)*0.42)
                    }
                }
                vertices.append(SCNVector3((u-0.5)*18.8,height,(v-0.5)*9.4))
                uvs.append(CGPoint(x:CGFloat(u),y:CGFloat(v)))
            }
        }
        for j in 0..<ny {
            for i in 0..<nx {
                let a=Int32(j*(nx+1)+i), b=a+1, c=a+Int32(nx+1), d=c+1
                indices.append(contentsOf:[a,c,b,b,c,d])
            }
        }
        let geometry=SCNGeometry(sources:[SCNGeometrySource(vertices:vertices),SCNGeometrySource(textureCoordinates:uvs)],
                                 elements:[SCNGeometryElement(indices:indices,primitiveType:.triangles)])
        let mat=SCNMaterial(); mat.diffuse.contents=img ?? NSImage(); mat.lightingModel = .constant; mat.isDoubleSided=true
        geometry.materials=[mat]
        return SCNNode(geometry:geometry)
    }
    private func marker(_ lon:Float,_ lat:Float,_ color:NSColor) -> SCNNode {
        let root=SCNNode(); root.position=pt(lon,lat)
        let ringGeo=SCNTorus(ringRadius:0.42,pipeRadius:0.045); ringGeo.materials=[material(color,emissive:0.25)]
        let ring=SCNNode(geometry:ringGeo); root.addChildNode(ring)
        let core=ball(0.12,color); core.position.y=0.06; root.addChildNode(core)
        if !reduced { ring.runAction(.repeatForever(.sequence([.scale(to:1.18,duration:0.9),.scale(to:0.88,duration:0.9)]))) }
        return root
    }
    private func soldier(_ lon:Float,_ lat:Float,_ tint:NSColor) -> SCNNode {
        let root=SCNNode(); root.position=pt(lon,lat,0.36)
        let dark=color(0.19,0.22,0.17), skin=color(0.73,0.61,0.46)
        let torso=box(0.23,0.34,0.14,tint,0.05); torso.position.y=0.42; root.addChildNode(torso)
        let belt=box(0.24,0.04,0.15,dark,0.01); belt.position.y=0.32; root.addChildNode(belt)
        let backpack=box(0.19,0.24,0.09,dark,0.03); backpack.position=SCNVector3(0,0.42,-0.11); root.addChildNode(backpack)
        let head=ball(0.11,skin); head.position.y=0.68; root.addChildNode(head)
        for x:Float in [-0.042,0.042] {
            let eye=ball(0.012,dark); eye.position=SCNVector3(x,0.69,0.102); root.addChildNode(eye)
        }
        let helmet=ball(0.12,tint); helmet.scale=SCNVector3(1,0.43,1); helmet.position.y=0.76; root.addChildNode(helmet)
        let brim=box(0.24,0.02,0.21,tint,0.03); brim.position.y=0.74; root.addChildNode(brim)
        func limb(_ x:Float,_ y:Float,_ height:CGFloat,_ width:CGFloat,_ c:NSColor) -> SCNNode {
            let pivot=SCNNode(); pivot.position=SCNVector3(x,y,0)
            let shape=SCNCapsule(capRadius:width/2,height:height); shape.materials=[material(c)]
            let piece=SCNNode(geometry:shape); piece.position = SCNVector3(0,-Float(height)/2,0); pivot.addChildNode(piece)
            root.addChildNode(pivot); return pivot
        }
        let leftLeg=limb(-0.065,0.29,0.30,0.09,dark), rightLeg=limb(0.065,0.29,0.30,0.09,dark)
        let leftArm=limb(-0.15,0.56,0.27,0.08,tint), rightArm=limb(0.15,0.56,0.27,0.08,tint)
        let rifle=box(0.33,0.035,0.035,dark,0.01); rifle.position=SCNVector3(0.10,0.38,0.12); root.addChildNode(rifle)
        for x:Float in [-0.063,0.063] {
            let pocket=box(0.065,0.08,0.015,dark,0.008); pocket.position=SCNVector3(x,0.45,0.075); root.addChildNode(pocket)
        }
        root.scale=SCNVector3(1.3,1.3,1.3)
        if !reduced {
            let swing=SCNAction.repeatForever(.sequence([.rotateBy(x:0.50,y:0,z:0,duration:0.32),.rotateBy(x:-1.0,y:0,z:0,duration:0.64),.rotateBy(x:0.50,y:0,z:0,duration:0.32)]))
            let reverse=SCNAction.repeatForever(.sequence([.rotateBy(x:-0.50,y:0,z:0,duration:0.32),.rotateBy(x:1.0,y:0,z:0,duration:0.64),.rotateBy(x:-0.50,y:0,z:0,duration:0.32)]))
            leftLeg.runAction(swing); rightArm.runAction(swing); rightLeg.runAction(reverse); leftArm.runAction(reverse)
            root.runAction(.repeatForever(.sequence([.moveBy(x:0.28,y:0,z:0,duration:1.8),.moveBy(x:-0.28,y:0,z:0,duration:1.8)])))
        }
        return root
    }
    private func ship(_ lon:Float,_ lat:Float,_ tint:NSColor) -> SCNNode {
        let root=SCNNode(); root.position=pt(lon,lat,0.22)
        let hull=box(0.75,0.13,0.27,tint,0.06); hull.position.y=0.05; root.addChildNode(hull)
        let cabin=box(0.25,0.18,0.16,color(0.67,0.69,0.64),0.03); cabin.position=SCNVector3(0.04,0.18,0); root.addChildNode(cabin)
        let mast=box(0.025,0.20,0.025,color(0.8,0.79,0.70),0); mast.position=SCNVector3(-0.05,0.35,0); root.addChildNode(mast)
        for x:Float in [-0.24,0.27] {
            let turret=SCNCylinder(radius:0.055,height:0.055); turret.materials=[material(color(0.30,0.34,0.32))]
            let node=SCNNode(geometry:turret); node.position=SCNVector3(x,0.14,0); root.addChildNode(node)
            let barrel=box(0.12,0.025,0.025,color(0.23,0.27,0.25),0.006); barrel.position=SCNVector3(x+0.08,0.16,0); root.addChildNode(barrel)
        }
        root.scale=SCNVector3(1.3,1.3,1.3)
        if !reduced { root.runAction(.repeatForever(.sequence([.group([.rotateBy(x:0,y:0,z:0.08,duration:1.5),.moveBy(x:0.35,y:0,z:0,duration:1.5)]),.group([.rotateBy(x:0,y:0,z:-0.08,duration:1.5),.moveBy(x:-0.35,y:0,z:0,duration:1.5)])]))) }
        return root
    }
    private func plane(_ lon:Float,_ lat:Float,_ tint:NSColor) -> SCNNode {
        let root=SCNNode(); root.position=pt(lon,lat,0.65)
        let hull=box(0.65,0.10,0.12,tint,0.05); root.addChildNode(hull)
        let wings=box(0.18,0.045,0.64,tint,0.025); root.addChildNode(wings)
        let tail=box(0.12,0.13,0.22,tint,0.02); tail.position.x = -0.25; root.addChildNode(tail)
        let cockpit=ball(0.09,color(0.18,0.32,0.34)); cockpit.scale=SCNVector3(1.4,0.55,0.75); cockpit.position=SCNVector3(0.06,0.08,0); root.addChildNode(cockpit)
        root.scale=SCNVector3(1.35,1.35,1.35)
        if !reduced { root.runAction(.repeatForever(.sequence([.moveBy(x:0.8,y:0.07,z:0,duration:2.8),.moveBy(x:-0.8,y:-0.07,z:0,duration:2.8)]))) }
        return root
    }
    private func tank(_ lon:Float,_ lat:Float,_ tint:NSColor) -> SCNNode {
        let root=SCNNode(); root.position=pt(lon,lat,0.20)
        let tracks=box(0.55,0.10,0.32,color(0.17,0.18,0.16)); root.addChildNode(tracks)
        for side:Float in [-0.17,0.17] { for x:Float in [-0.20,-0.10,0,0.10,0.20] {
            let wheelGeo=SCNCylinder(radius:0.055,height:0.035); wheelGeo.materials=[material(color(0.36,0.37,0.30))]
            let wheel=SCNNode(geometry:wheelGeo); wheel.eulerAngles.x = .pi/2; wheel.position=SCNVector3(x,0,side); root.addChildNode(wheel)
        } }
        let body=box(0.43,0.16,0.27,tint,0.045); body.position.y=0.12; root.addChildNode(body)
        let turret=box(0.22,0.12,0.20,tint,0.05); turret.position.y=0.24; root.addChildNode(turret)
        let gun=box(0.32,0.035,0.035,tint,0.015); gun.position=SCNVector3(0.24,0.24,0); root.addChildNode(gun)
        root.scale=SCNVector3(1.35,1.35,1.35)
        if !reduced { root.runAction(.repeatForever(.sequence([.moveBy(x:0.35,y:0,z:0,duration:1.6),.moveBy(x:-0.35,y:0,z:0,duration:1.6)]))) }
        return root
    }
    /// Actors attached to the camera remain visibly in the foreground of the
    /// interface while the smaller markers retain their geographic positions.
    private func stageForeground(_ chapter:WarChapter, scale:Double) {
        guard overlayActive, chapter != .waiting else { return }
        let s=Float(scale/3.4)
        foregroundRoot.scale=SCNVector3(s,s,s)
        let olive=color(0.34,0.38,0.27), khaki=color(0.50,0.45,0.31), steel=color(0.36,0.42,0.40)
        func moving(_ node:SCNNode, y:Float, duration:Double, reverse:Bool=false) {
            let carrier=SCNNode()
            carrier.position=SCNVector3(reverse ? 2.8 : -2.8,y,-8)
            node.position=SCNVector3Zero; carrier.addChildNode(node); foregroundRoot.addChildNode(carrier)
            if !reduced {
                let distance:CGFloat = reverse ? -5.6 : 5.6
                let march=SCNAction.sequence([.moveBy(x:distance,y:0,z:0,duration:duration),.fadeOut(duration:0.25),.moveBy(x:-distance,y:0,z:0,duration:0),.fadeIn(duration:0.25),.wait(duration:0.3)])
                carrier.runAction(.repeatForever(march))
            }
        }
        func foot(_ y:Float,_ reverse:Bool=false) {
            let actor=soldier(0,0,olive); actor.scale=SCNVector3(2.0,2.0,2.0)
            moving(actor,y:y,duration:10.5,reverse:reverse)
        }
        func armour(_ y:Float) {
            let actor=tank(0,0,khaki); actor.scale=SCNVector3(1.85,1.85,1.85)
            moving(actor,y:y,duration:13.0)
        }
        func vessel(_ y:Float) {
            let actor=ship(0,0,steel); actor.scale=SCNVector3(1.75,1.75,1.75)
            moving(actor,y:y,duration:14.0,reverse:true)
        }
        func aircraft(_ y:Float) {
            let actor=plane(0,0,olive); actor.scale=SCNVector3(1.45,1.45,1.45)
            moving(actor,y:y,duration:8.0)
        }
        switch chapter {
        case .waiting: break
        case .poland: foot(-2.35); armour(-2.0)
        case .west: foot(-2.3); aircraft(2.0)
        case .global: foot(-2.35); vessel(-2.1)
        case .africaPacific: foot(-2.35); vessel(-2.25); aircraft(2.05)
        case .normandy: foot(-2.35); vessel(-2.05)
        case .europeEnd: foot(-2.35); armour(-2.0)
        case .japanEnd: foot(-2.35); vessel(-2.2)
        }
    }
    private func movement(_ startLon:Float,_ startLat:Float,_ endLon:Float,_ endLat:Float,_ tint:NSColor) -> SCNNode {
        let root=SCNNode()
        let start=pt(startLon,startLat,0.52), end=pt(endLon,endLat,0.52)
        let source=SCNGeometrySource(vertices:[start,end])
        let element=SCNGeometryElement(indices:[Int32(0),Int32(1)],primitiveType:.line)
        let line=SCNGeometry(sources:[source],elements:[element]); line.materials=[material(tint,emissive:0.8)]
        root.addChildNode(SCNNode(geometry:line))
        let dot=ball(0.10,tint); dot.position=start; root.addChildNode(dot)
        if !reduced {
            let move=SCNAction.move(to:end,duration:2.0); move.timingMode = .easeInEaseOut
            dot.runAction(.repeatForever(.sequence([move,.fadeOut(duration:0.15),.move(to:start,duration:0),.fadeIn(duration:0.15),.wait(duration:0.35)])))
        }
        return root
    }
    private enum FlagKind { case poland, france, usa, ussr, japan, surrender }

    /// Small, locally drawn flags: illustrative visual markers, not boundary claims.
    private func flagImage(_ kind:FlagKind) -> NSImage {
        let size=NSSize(width:420,height:260)
        let image=NSImage(size:size); image.lockFocus()
        let rect=NSRect(origin:.zero,size:size)
        NSColor.white.setFill(); rect.fill()
        switch kind {
        case .poland:
            color(0.80,0.10,0.19).setFill(); NSRect(x:0,y:0,width:420,height:130).fill()
        case .france:
            color(0.08,0.22,0.56).setFill(); NSRect(x:0,y:0,width:140,height:260).fill()
            color(0.85,0.13,0.18).setFill(); NSRect(x:280,y:0,width:140,height:260).fill()
        case .usa:
            for i in 0..<13 where i % 2 == 0 {
                color(0.74,0.12,0.15).setFill()
                NSRect(x:0,y:CGFloat(i)*20,width:420,height:20).fill()
            }
            color(0.10,0.17,0.39).setFill(); NSRect(x:0,y:120,width:172,height:140).fill()
            NSColor.white.setFill()
            for row in 0..<5 { for col in 0..<6 {
                NSBezierPath(ovalIn:NSRect(x:13+CGFloat(col)*25,y:134+CGFloat(row)*24,width:6,height:6)).fill()
            } }
        case .ussr:
            color(0.72,0.09,0.12).setFill(); rect.fill()
            color(0.97,0.79,0.24).setStroke()
            let emblem=NSBezierPath(); emblem.lineWidth=9
            emblem.move(to:NSPoint(x:45,y:150)); emblem.line(to:NSPoint(x:105,y:214))
            emblem.move(to:NSPoint(x:42,y:205)); emblem.curve(to:NSPoint(x:100,y:153),controlPoint1:NSPoint(x:45,y:163),controlPoint2:NSPoint(x:70,y:150))
            emblem.stroke()
            let star=NSAttributedString(string:"★",attributes:[.font:NSFont.systemFont(ofSize:35),.foregroundColor:color(0.97,0.79,0.24)])
            star.draw(at:NSPoint(x:50,y:215))
        case .japan:
            color(0.72,0.10,0.16).setFill(); NSBezierPath(ovalIn:NSRect(x:150,y:70,width:120,height:120)).fill()
        case .surrender:
            // A white surrender marker, not a claim about Germany's national flag.
            break
        }
        image.unlockFocus(); return image
    }
    private func flag(_ lon:Float,_ lat:Float,_ kind:FlagKind,_ label:String,scale:Float=1.0) -> SCNNode {
        let root=SCNNode(); root.position=pt(lon,lat,0.30); root.scale=SCNVector3(scale,scale,scale)
        let mast=SCNCylinder(radius:0.025,height:1.25); mast.materials=[material(color(0.79,0.78,0.71))]
        let pole=SCNNode(geometry:mast); pole.position.y=0.58; root.addChildNode(pole)
        let banner=SCNPlane(width:0.95,height:0.58)
        let flagMaterial=SCNMaterial(); flagMaterial.diffuse.contents=flagImage(kind)
        flagMaterial.lightingModel = .constant; flagMaterial.isDoubleSided=true; banner.materials=[flagMaterial]
        let flagNode=SCNNode(geometry:banner); flagNode.position=SCNVector3(0.46,1.00,0)
        let facing=SCNBillboardConstraint(); facing.freeAxes = .Y; flagNode.constraints=[facing]
        root.addChildNode(flagNode)
        let text=SCNText(string:label,extrusionDepth:0.002)
        text.font=NSFont.systemFont(ofSize:0.18,weight:.bold); text.flatness=0.005
        let textMaterial=SCNMaterial(); textMaterial.diffuse.contents=NSColor.white; textMaterial.lightingModel = .constant
        text.materials=[textMaterial]
        let word=SCNNode(geometry:text)
        let (low,high)=word.boundingBox
        let width=CGFloat(high.x-low.x)
        let bg=SCNPlane(width:max(width+0.18,0.95),height:0.27)
        let bgMat=SCNMaterial(); bgMat.diffuse.contents=color(0.08,0.10,0.13,0.90); bgMat.lightingModel = .constant; bgMat.isDoubleSided=true
        bg.materials=[bgMat]
        let badge=SCNNode(geometry:bg); badge.position=SCNVector3(0.46,1.43,0)
        let badgeFacing=SCNBillboardConstraint(); badgeFacing.freeAxes = .Y; badge.constraints=[badgeFacing]
        word.position=SCNVector3(-Float((low.x+high.x)/2), -Float((low.y+high.y)/2), 0.012)
        badge.addChildNode(word); root.addChildNode(badge)
        if !reduced { flagNode.runAction(.repeatForever(.sequence([.rotateBy(x:0,y:0,z:0.025,duration:1.3),.rotateBy(x:0,y:0,z:-0.05,duration:2.6),.rotateBy(x:0,y:0,z:0.025,duration:1.3)]))) }
        return root
    }
    private func mushroom(_ lon:Float,_ lat:Float) -> SCNNode {
        let root=SCNNode(); root.position=pt(lon,lat,0.16)
        let cloud=color(0.69,0.66,0.59)
        let stem=SCNCylinder(radius:0.12,height:0.52); stem.materials=[material(cloud)]
        let stemNode=SCNNode(geometry:stem); stemNode.position.y=0.25; root.addChildNode(stemNode)
        for (x,y,z,r): (Float,Float,Float,CGFloat) in [(-0.20,0.57,0,0.19),(0.0,0.68,0,0.25),(0.19,0.58,0,0.19),(0.0,0.56,0.13,0.18)] {
            root.addChildNode({let b=ball(r,cloud);b.position=SCNVector3(x,y,z);return b}())
        }
        let halo=marker(lon,lat,color(0.94,0.54,0.28)); halo.position=SCNVector3Zero; root.addChildNode(halo)
        if !reduced { root.runAction(.repeatForever(.sequence([.fadeOpacity(to:0.7,duration:1.6),.fadeOpacity(to:1,duration:1.6)]))) }
        return root
    }
    func show(_ chapter:WarChapter, reduced:Bool) {
        guard active != chapter || self.reduced != reduced else { return }
        active=chapter; self.reduced=reduced
        chapterRoot.childNodes.forEach { $0.removeAllActions(); $0.removeFromParentNode() }
        foregroundRoot.childNodes.forEach { $0.removeAllActions(); $0.removeFromParentNode() }
        let focus:(Float,Float,Double)
        switch chapter {
        case .waiting: focus=(0,0,6.2)
        // In compact/portrait windows a full-world camera can clip both flags.
        // Center one principal flag while the UI lists every named country.
        case .global: focus=(37,56,3.4)
        case .africaPacific: focus=(144,32,3.4)
        case .poland: focus=(18,51,2.7)
        case .west: focus=(1,49,3.1)
        case .normandy: focus=(-2,49,2.7)
        case .europeEnd: focus=(13,51,3.1)
        case .japanEnd: focus=(133,34,3.0)
        }
        let ground=pt(focus.0,focus.1,0)
        SCNTransaction.begin()
        SCNTransaction.animationDuration = reduced ? 0 : 1.5
        cameraNode.position=SCNVector3(ground.x,17,ground.z+17)
        cameraNode.camera?.orthographicScale=focus.2
        SCNTransaction.commit()
        let red=color(0.78,0.30,0.22), blue=color(0.37,0.66,0.70), tan=color(0.71,0.66,0.47)
        func add(_ nodes:SCNNode...) { nodes.forEach { chapterRoot.addChildNode($0) } }
        switch chapter {
        case .waiting:
            add(marker(20,51,tan), marker(137,35,tan), ship(-28,30,blue))
        case .poland:
            add(marker(19,52,red),tank(14,51,red),soldier(21,51,tan),plane(22,55,red),movement(10,50,22,52,red),flag(19,52,.poland,"POLONIA"))
        case .west:
            add(marker(2,48,red),tank(5,49,red),plane(-2,51,blue),ship(-9,50,blue),movement(10,50,2,48,red),flag(2,48,.france,"FRANCIA"))
        case .global:
            add(marker(37,56,red),tank(30,54,red),soldier(39,55,blue),marker(-157,21,red),ship(144,30,tan),plane(138,37,red),movement(15,51,38,56,red),flag(37,56,.ussr,"URSS",scale:1.7),flag(-157,21,.usa,"EE. UU.",scale:1.7))
        case .africaPacific:
            add(marker(24,30,tan),tank(21,29,tan),soldier(28,31,blue),ship(158,16,blue),plane(142,27,tan),marker(169,19,red),movement(147,28,169,19,blue),flag(144,32,.japan,"JAPÓN",scale:1.5),flag(-157,21,.usa,"EE. UU.",scale:1.5))
        case .normandy:
            add(marker(-1,49,blue),ship(-6,51,blue),ship(-3,52,blue),soldier(1,48,blue),plane(3,52,blue),movement(-8,52,1,48,blue),flag(-1,49,.france,"FRANCIA"))
        case .europeEnd:
            add(marker(13,52,blue),soldier(10,50,blue),tank(19,51,tan),plane(11,54,blue),movement(3,48,13,52,blue),flag(13,52,.surrender,"ALEMANIA · RENDICIÓN"))
        case .japanEnd:
            add(mushroom(132.45,34.39),mushroom(129.88,32.75),ship(151,24,blue),flag(135,35,.japan,"JAPÓN"))
        }
        stageForeground(chapter, scale:focus.2)
    }
}

#if WAR_DEBUG
func renderWarSceneSnapshot(progress: Double, overlay: Bool = false, to file: URL) throws {
    let stage=WarStage()
    stage.setOverlay(overlay)
    stage.show(resolveWarChapter(progress:progress,running:true,completed:false), reduced:true)
    let renderer=SCNRenderer(device:MTLCreateSystemDefaultDevice(), options:nil)
    renderer.scene=stage.scene
    let image=renderer.snapshot(atTime:1.0,with:CGSize(width:1200,height:600),antialiasingMode:.multisampling2X)
    guard let tiff=image.tiffRepresentation, let bitmap=NSBitmapImageRep(data:tiff), let png=bitmap.representation(using:.png,properties:[:]) else { throw NSError(domain:"WarSnapshot",code:1) }
    try png.write(to:file)
}
#endif
