import SwiftUI
import SceneKit
import AppKit

/// Genuine 3D scene. The download bar remains controlled exclusively by real progress.
struct RobotView: View {
    var progress: Double?
    var running: Bool
    var completed: Bool = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var startedAt = Date()
    @State private var accessibleInteraction = 0

    private func phase(at now: Date) -> RobotPhase {
        if !running { return completed ? .celebration : .sleep }
        guard let progress else { return .wake }
        if progress <= 0 {
            // A single song can remain at 0% until it finishes. Keep the little
            // scene entertaining without claiming any download has completed.
            let elapsed = now.timeIntervalSince(startedAt)
            if elapsed < 3 { return .wake }
            if elapsed < 8 { return .exercise }
            return .battle
        }
        if progress < 0.10 { return .wake }
        if progress < 0.30 { return .exercise }
        return .battle
    }

    var body: some View {
        Group {
            if running, let progress, progress <= 0, !reduceMotion {
                TimelineView(.periodic(from: .now, by: 0.5)) { context in
                    let mode = phase(at: context.date)
                    RobotSceneView(phase: mode, reduceMotion: reduceMotion, interactionID: accessibleInteraction)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(mode.accessibilityDescription)
                        .accessibilityHint("Haz clic, o pulsa Return, para saludar al robot.")
                        .accessibilityAddTraits(.isButton)
                        .accessibilityAction(named: Text("Saludar al robot")) { accessibleInteraction += 1 }
                }
            } else {
                let mode = phase(at: Date())
                RobotSceneView(phase: mode, reduceMotion: reduceMotion, interactionID: accessibleInteraction)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(mode.accessibilityDescription)
                    .accessibilityHint("Haz clic, o pulsa Return, para saludar al robot.")
                    .accessibilityAddTraits(.isButton)
                    .accessibilityAction(named: Text("Saludar al robot")) { accessibleInteraction += 1 }
            }
        }
        .onChange(of: running) { _, active in if active { startedAt = Date() } }
    }
}

private enum RobotPhase: Equatable {
    case sleep, wake, exercise, battle, celebration
    var accessibilityDescription: String {
        switch self {
        case .sleep: return "Robot tridimensional durmiendo mientras espera"
        case .wake: return "Robot tridimensional despertando mientras se prepara la descarga"
        case .exercise: return "Robot tridimensional haciendo ejercicio durante la descarga"
        case .battle: return "Robot tridimensional jugando con patos y lanzando rayos de colores"
        case .celebration: return "Robot tridimensional celebrando que la descarga terminó"
        }
    }
}

private struct RobotSceneView: NSViewRepresentable {
    let phase: RobotPhase
    let reduceMotion: Bool
    let interactionID: Int

    func makeCoordinator() -> Stage { Stage() }
    func makeNSView(context: Context) -> RobotSceneCanvas {
        let view = RobotSceneCanvas(frame: .zero)
        view.onInteraction = { [weak stage = context.coordinator] in stage?.interact() }
        context.coordinator.requestRedraw = { [weak view] in view?.needsDisplay = true }
        view.setAccessibilityElement(true)
        view.setAccessibilityRole(.button)
        view.setAccessibilityLabel("Mascota robot. Haz clic para saludar.")
        view.scene = context.coordinator.scene
        view.backgroundColor = .clear
        view.allowsCameraControl = false
        view.autoenablesDefaultLighting = false
        view.antialiasingMode = .multisampling2X
        view.preferredFramesPerSecond = 24
        view.rendersContinuously = !reduceMotion
        view.isPlaying = !reduceMotion
        context.coordinator.update(phase, reduced: reduceMotion)
        context.coordinator.lastInteractionID = interactionID
        return view
    }
    func updateNSView(_ view: RobotSceneCanvas, context: Context) {
        context.coordinator.update(phase, reduced: reduceMotion)
        if context.coordinator.lastInteractionID != interactionID {
            context.coordinator.lastInteractionID = interactionID
            context.coordinator.interact()
        }
        view.preferredFramesPerSecond = phase == .sleep ? 8 : (phase == .celebration ? 12 : 24)
        view.rendersContinuously = !reduceMotion
        view.isPlaying = !reduceMotion
    }
    static func dismantleNSView(_ view: RobotSceneCanvas, coordinator: Stage) {
        view.isPlaying = false
        view.rendersContinuously = false
        view.scene = nil
        view.onInteraction = nil
        coordinator.requestRedraw = nil
    }
}

private final class RobotSceneCanvas: SCNView {
    var onInteraction: (() -> Void)?
    override var acceptsFirstResponder: Bool { true }
    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        onInteraction?()
    }
    override func keyDown(with event: NSEvent) {
        if event.keyCode == 36 { onInteraction?() }
        else { super.keyDown(with: event) }
    }
    override func accessibilityPerformPress() -> Bool {
        onInteraction?()
        return true
    }
}

/// Nodes, meshes, lights and animation all remain in SceneKit; no pre-rendered sprites.
private final class Stage: NSObject {
    let scene = SCNScene()
    private let interactionRoot = SCNNode()
    private let robot = SCNNode()
    private let head = SCNNode()
    private let leftArm = SCNNode()
    private let rightArm = SCNNode()
    private let eyelids = SCNNode()
    private let eyes = SCNNode()
    private let duckA = SCNNode()
    private let duckB = SCNNode()
    private let lasers = SCNNode()
    private let sleepZ = SCNNode()
    private let stars = SCNNode()
    private var current: RobotPhase?
    private var reduced = false
    var lastInteractionID = 0
    var requestRedraw: (() -> Void)?

    override init() {
        super.init()
        setupScene()
    }

    private func color(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ a: CGFloat = 1) -> NSColor {
        NSColor(calibratedRed: r, green: g, blue: b, alpha: a)
    }
    private func material(_ color: NSColor, metal: CGFloat = 0.0, glow: CGFloat = 0.0) -> SCNMaterial {
        let m = SCNMaterial()
        m.diffuse.contents = color
        m.lightingModel = .blinn
        m.specular.contents = NSColor(white: 0.7, alpha: 1)
        m.shininess = 35 + 60 * metal
        if glow > 0 { m.emission.contents = color.withAlphaComponent(glow) }
        return m
    }
    private func box(_ w: CGFloat, _ h: CGFloat, _ d: CGFloat, _ radius: CGFloat, _ c: NSColor, _ x: Float, _ y: Float, _ z: Float) -> SCNNode {
        let geometry = SCNBox(width: w, height: h, length: d, chamferRadius: radius)
        geometry.materials = [material(c)]
        let node = SCNNode(geometry: geometry); node.position = SCNVector3(x,y,z); return node
    }
    private func ball(_ radius: CGFloat, _ c: NSColor, _ x: Float, _ y: Float, _ z: Float, glow: CGFloat = 0) -> SCNNode {
        let geometry = SCNSphere(radius: radius); geometry.segmentCount = 24; geometry.materials = [material(c, glow: glow)]
        let node = SCNNode(geometry: geometry); node.position = SCNVector3(x,y,z); return node
    }
    private func cylinder(_ radius: CGFloat, _ height: CGFloat, _ c: NSColor, _ x: Float, _ y: Float, _ z: Float) -> SCNNode {
        let geometry=SCNCylinder(radius: radius,height: height); geometry.radialSegmentCount=20; geometry.materials=[material(c)]
        let n=SCNNode(geometry: geometry); n.position=SCNVector3(x,y,z); return n
    }

    private func setupScene() {
        scene.background.contents = NSColor.clear
        let camera = SCNCamera(); camera.usesOrthographicProjection = true; camera.orthographicScale = 2.8
        camera.zNear = 0.1; camera.zFar = 100
        let cameraNode=SCNNode(); cameraNode.camera=camera; cameraNode.position=SCNVector3(0,3.0,10.5)
        cameraNode.look(at: SCNVector3(0,1.35,0)); scene.rootNode.addChildNode(cameraNode)

        let ambient = SCNLight(); ambient.type = .ambient; ambient.color = color(0.68,0.45,0.48); ambient.intensity=650
        let ambientNode=SCNNode(); ambientNode.light=ambient; scene.rootNode.addChildNode(ambientNode)
        let key=SCNLight(); key.type = .directional; key.color=NSColor.white; key.intensity=1150
        key.castsShadow=true; key.shadowRadius=3; key.shadowSampleCount=8; key.shadowColor=NSColor.black.withAlphaComponent(0.35)
        let keyNode=SCNNode(); keyNode.light=key; keyNode.eulerAngles=SCNVector3(-Float.pi/3,-Float.pi/5,0); scene.rootNode.addChildNode(keyNode)
        let fill=SCNLight(); fill.type = .omni; fill.color=color(1,0.17,0.22); fill.intensity=450
        let fillNode=SCNNode(); fillNode.light=fill; fillNode.position=SCNVector3(-4,3,3); scene.rootNode.addChildNode(fillNode)

        // A rounded platform anchors the toys in a tiny stage without hiding the UI.
        let platform=cylinder(2.45,0.17,color(0.24,0.055,0.075),0,-0.05,0)
        scene.rootNode.addChildNode(platform)
        let lip=cylinder(2.30,0.045,color(0.41,0.09,0.12),0,0.055,0)
        scene.rootNode.addChildNode(lip)
        robot.position=SCNVector3(-0.85,0.08,0)
        interactionRoot.addChildNode(robot); scene.rootNode.addChildNode(interactionRoot)
        buildRobot(); buildDuck(duckA, scale: 1.0); buildDuck(duckB, scale: 0.72)
        duckA.position=SCNVector3(1.02,0.10,0.05); duckB.position=SCNVector3(1.67,0.10,-0.5)
        scene.rootNode.addChildNode(duckA); scene.rootNode.addChildNode(duckB)
        buildLaser(); buildZzz(); buildStars()
    }

    private func buildRobot() {
        let red=color(0.92,0.20,0.26), redLight=color(1.0,0.38,0.36), dark=color(0.14,0.025,0.045)
        let steel=color(0.70,0.76,0.80), white=color(1,0.92,0.84)
        // Torso, screen and cheerful big central button.
        robot.addChildNode(box(1.05,0.85,0.60,0.18,red,0,0.99,0))
        robot.addChildNode(box(0.66,0.26,0.06,0.07,dark,0,1.02,0.32))
        robot.addChildNode(ball(0.065,color(1,0.76,0.50),-0.18,1.03,0.36,glow:0.8))
        robot.addChildNode(box(0.23,0.045,0.025,0.02,color(1,0.76,0.50),0.09,1.02,0.36))
        // Short chunky feet.
        robot.addChildNode(box(0.32,0.28,0.40,0.09,redLight,-0.28,0.23,0.04))
        robot.addChildNode(box(0.32,0.28,0.40,0.09,redLight,0.28,0.23,0.04))
        head.position=SCNVector3(0,1.48,0); robot.addChildNode(head)
        head.addChildNode(box(1.14,0.81,0.67,0.22,redLight,0,0.33,0))
        head.addChildNode(box(0.88,0.49,0.045,0.13,dark,0,0.36,0.35))
        for x: Float in [-0.20,0.20] {
            eyes.addChildNode(ball(0.075,white,x,0.40,0.39,glow:0.8))
            eyelids.addChildNode(box(0.18,0.045,0.025,0.02,white,x,0.40,0.405))
        }
        head.addChildNode(eyes); head.addChildNode(eyelids)
        head.addChildNode(box(0.20,0.035,0.02,0.01,color(1,0.56,0.42),0,0.20,0.39))
        head.addChildNode(cylinder(0.035,0.25,steel,0,0.85,0))
        head.addChildNode(ball(0.095,color(1,0.80,0.49),0,1.02,0,glow:0.5))
        head.addChildNode(ball(0.15,red,-0.61,0.33,0)); head.addChildNode(ball(0.15,red,0.61,0.33,0))
        // Arms are children of pivot nodes so a rotation produces a real movement.
        leftArm.position=SCNVector3(-0.68,1.26,0); rightArm.position=SCNVector3(0.68,1.26,0)
        for arm in [leftArm,rightArm] {
            arm.addChildNode(ball(0.16,steel,0,0,0))
            arm.addChildNode(box(0.23,0.54,0.27,0.09,red,0,-0.26,0))
            arm.addChildNode(ball(0.14,redLight,0,-0.55,0))
            robot.addChildNode(arm)
        }
        let leftWeight=makeWeight(); leftWeight.position=SCNVector3(0,-0.57,0); leftArm.addChildNode(leftWeight)
        let rightWeight=makeWeight(); rightWeight.position=SCNVector3(0,-0.57,0); rightArm.addChildNode(rightWeight)
        leftWeight.name="weight"; rightWeight.name="weight"
    }
    private func makeWeight() -> SCNNode {
        let n=SCNNode(), white=color(0.91,0.93,0.98), burgundy=color(0.45,0.05,0.10)
        let bar=cylinder(0.045,0.52,white,0,0,0); bar.eulerAngles.z=CGFloat.pi/2; n.addChildNode(bar)
        n.addChildNode(box(0.10,0.25,0.18,0.035,burgundy,-0.25,0,0))
        n.addChildNode(box(0.10,0.25,0.18,0.035,burgundy,0.25,0,0)); return n
    }

    private func buildDuck(_ node: SCNNode, scale: Float) {
        let yellow=color(1.0,0.76,0.19), orange=color(1,0.35,0.08), dark=color(0.15,0.07,0.045)
        node.scale=SCNVector3(scale,scale,scale)
        let body=ball(0.52,yellow,0,0.55,0); body.scale=SCNVector3(1,0.82,0.82); node.addChildNode(body)
        node.addChildNode(ball(0.32,yellow,-0.05,1.05,0.10))
        // Two dark shiny eyes on the camera-facing face.
        node.addChildNode(ball(0.055,dark,-0.18,1.12,0.39))
        node.addChildNode(ball(0.055,dark,0.08,1.12,0.39))
        node.addChildNode(ball(0.018,.white,-0.19,1.14,0.44,glow:0.5))
        node.addChildNode(ball(0.018,.white,0.07,1.14,0.44,glow:0.5))
        let beak=box(0.34,0.13,0.18,0.055,orange,-0.05,0.95,0.42); node.addChildNode(beak)
        let wing=ball(0.27,color(1,0.63,0.11),0.12,0.62,0.34); wing.scale=SCNVector3(1.15,0.70,0.40); node.addChildNode(wing)
        node.addChildNode(box(0.27,0.09,0.24,0.04,orange,-0.22,0.10,0.13))
        node.addChildNode(box(0.27,0.09,0.24,0.04,orange,0.20,0.10,0.13))
    }

    private func buildLaser() {
        // A safe, playful beam rather than a weapon; its pulse is entirely decorative.
        let ray=SCNBox(width: 1.35,height: 0.12,length: 0.075,chamferRadius: 0.04)
        ray.materials=[material(color(1,0.94,0.55),glow:1)]
        let node=SCNNode(geometry: ray); node.position=SCNVector3(0.10,1.18,0.49); lasers.addChildNode(node)
        lasers.addChildNode(ball(0.18,color(1,0.98,0.64),0.77,1.18,0.49,glow:1))
        scene.rootNode.addChildNode(lasers)
    }
    private func buildZzz() {
        let txt=SCNText(string: "z z Z", extrusionDepth: 0.05)
        txt.font=NSFont.systemFont(ofSize: 0.30,weight:.bold); txt.flatness=0.1
        txt.materials=[material(color(1,0.76,0.72),glow:0.4)]
        let node=SCNNode(geometry:txt); node.position=SCNVector3(-0.1,2.55,0.25); sleepZ.addChildNode(node)
        scene.rootNode.addChildNode(sleepZ)
    }
    private func buildStars() {
        let colors=[color(1,0.76,0.30),color(1,0.35,0.44),color(1,0.94,0.68)]
        for (i,position) in [SCNVector3(-1.75,2.48,0),SCNVector3(1.48,2.55,0),SCNVector3(0.15,2.72,0),SCNVector3(2.05,1.9,0)].enumerated() {
            let star=ball(0.07,colors[i%colors.count],Float(position.x),Float(position.y),Float(position.z),glow:0.9)
            star.scale=SCNVector3(1,1.8,1); stars.addChildNode(star)
        }
        scene.rootNode.addChildNode(stars)
    }

    func interact() {
        interactionRoot.removeAction(forKey: "saludo")
        interactionRoot.position = SCNVector3Zero
        interactionRoot.eulerAngles = SCNVector3Zero
        if reduced {
            // A stationary sparkle acknowledges the interaction without motion.
            stars.isHidden = false
            requestRedraw?()
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
                guard let self, self.current != .celebration else { return }
                self.stars.isHidden = true
                self.requestRedraw?()
            }
            return
        }
        let up = SCNAction.group([.moveBy(x: 0, y: 0.22, z: 0, duration: 0.20),
                                  .rotateBy(x: 0, y: 0.20, z: 0.12, duration: 0.20)])
        let down = SCNAction.group([.moveBy(x: 0, y: -0.22, z: 0, duration: 0.28),
                                    .rotateBy(x: 0, y: -0.20, z: -0.12, duration: 0.28)])
        interactionRoot.runAction(.sequence([up, down]), forKey: "saludo")
    }

    func update(_ phase: RobotPhase, reduced: Bool) {
        guard current != phase || self.reduced != reduced else { return }
        current=phase; self.reduced=reduced
        [robot,head,leftArm,rightArm,duckA,duckB,lasers,sleepZ,stars].forEach { $0.removeAllActions() }
        robot.position=SCNVector3(-0.85,0.08,0); robot.eulerAngles=SCNVector3Zero
        head.eulerAngles=SCNVector3Zero; leftArm.eulerAngles=SCNVector3Zero; rightArm.eulerAngles=SCNVector3Zero
        duckA.position=SCNVector3(1.02,0.10,0.05); duckB.position=SCNVector3(1.67,0.10,-0.5)
        duckA.eulerAngles=SCNVector3Zero; duckB.eulerAngles=SCNVector3Zero
        sleepZ.position=SCNVector3Zero; stars.opacity=1; lasers.opacity=1
        duckA.isHidden = phase != .battle && phase != .celebration
        duckB.isHidden = phase != .battle && phase != .celebration
        lasers.isHidden = phase != .battle
        sleepZ.isHidden = phase != .sleep
        stars.isHidden = phase != .celebration
        eyes.isHidden = phase == .sleep; eyelids.isHidden = phase != .sleep
        [leftArm,rightArm].forEach { arm in arm.childNode(withName:"weight",recursively:false)?.isHidden = phase != .exercise }
        if phase == .sleep { head.eulerAngles.z = -0.17 }
        if phase == .battle { rightArm.eulerAngles.z = CGFloat.pi/2; lasers.opacity = 1 }
        if phase == .celebration { leftArm.eulerAngles.z = -1.6; rightArm.eulerAngles.z = 1.6 }
        guard !reduced else { return }
        func repeatAction(_ actions: [SCNAction]) -> SCNAction { .repeatForever(.sequence(actions)) }
        switch phase {
        case .sleep:
            robot.runAction(repeatAction([.moveBy(x:0,y:0.035,z:0,duration:1.4),.moveBy(x:0,y:-0.035,z:0,duration:1.4)]))
            sleepZ.runAction(repeatAction([.moveBy(x:0.08,y:0.18,z:0,duration:1.8),.moveBy(x:-0.08,y:-0.18,z:0,duration:0)]))
        case .wake:
            head.runAction(repeatAction([.rotateTo(x:0,y:0,z:0.16,duration:0.5),.rotateTo(x:0,y:0,z:-0.16,duration:0.5)]))
            rightArm.runAction(repeatAction([.rotateTo(x:0,y:0,z:1.2,duration:0.5),.rotateTo(x:0,y:0,z:0.4,duration:0.5)]))
        case .exercise:
            leftArm.runAction(repeatAction([.rotateTo(x:0,y:0,z:-1.6,duration:0.45),.rotateTo(x:0,y:0,z:-0.3,duration:0.45)]))
            rightArm.runAction(repeatAction([.rotateTo(x:0,y:0,z:1.6,duration:0.45),.rotateTo(x:0,y:0,z:0.3,duration:0.45)]))
            robot.runAction(repeatAction([.moveBy(x:0,y:0.15,z:0,duration:0.45),.moveBy(x:0,y:-0.15,z:0,duration:0.45)]))
        case .battle:
            lasers.opacity=0
            lasers.runAction(repeatAction([.fadeOpacity(to:1,duration:0.08),.wait(duration:0.45),.fadeOpacity(to:0,duration:0.15),.wait(duration:0.22)]))
            duckA.runAction(repeatAction([.moveBy(x:-0.25,y:0.24,z:0,duration:0.32),.moveBy(x:0.25,y:-0.24,z:0,duration:0.32),.wait(duration:0.12)]))
            duckB.runAction(repeatAction([.group([.rotateTo(x:0,y:0,z:0.30,duration:0.4),.moveBy(x:-0.18,y:0.08,z:0,duration:0.4)]),.group([.rotateTo(x:0,y:0,z:-0.30,duration:0.4),.moveBy(x:0.18,y:-0.08,z:0,duration:0.4)])]))
            head.runAction(repeatAction([.rotateTo(x:0,y:0,z:0.12,duration:0.5),.rotateTo(x:0,y:0,z:-0.12,duration:0.5)]))
        case .celebration:
            robot.runAction(repeatAction([.moveBy(x:0,y:0.30,z:0,duration:0.32),.moveBy(x:0,y:-0.30,z:0,duration:0.32),.wait(duration:0.20)]))
            stars.runAction(repeatAction([.fadeOpacity(to:0.25,duration:0.5),.fadeOpacity(to:1,duration:0.5)]))
            duckA.runAction(repeatAction([.rotateTo(x:0,y:0,z:0.20,duration:0.4),.rotateTo(x:0,y:0,z:-0.20,duration:0.4)]))
        }
    }
}
