// Renders page specs (JSON) to PNG with CoreText, which shapes Indic scripts correctly.
// (Pillow on this Mac has no libraqm, so it would draw conjuncts and vowel signs in the wrong order.)
// Usage: swift render.swift <dir>   -> for every <dir>/*.spec.json writes <dir>/<name>.png
// Spec: {"w":1240,"h":1754,"items":[{"t":"text","x":..,"y":..,"s":size,"f":"PostScriptName","a":"l|r|c","c":[r,g,b]},
//                                    {"t":"rect","x":..,"y":..,"w":..,"h":..,"lw":1,"fill":[r,g,b]?},
//                                    {"t":"line","x1":..,"y1":..,"x2":..,"y2":..,"lw":1}]}  (y grows downward)
import AppKit

let dir = URL(fileURLWithPath: CommandLine.arguments[1])
let files = try FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)
    .filter { $0.lastPathComponent.hasSuffix(".spec.json") }
func col(_ a: Any?) -> NSColor {
    let v = (a as? [Double]) ?? [0, 0, 0]
    return NSColor(srgbRed: v[0] / 255, green: v[1] / 255, blue: v[2] / 255, alpha: 1)
}
for f in files {
    let out = URL(fileURLWithPath: f.path.replacingOccurrences(of: ".spec.json", with: ".png"))
    if FileManager.default.fileExists(atPath: out.path) { continue }
    let spec = try JSONSerialization.jsonObject(with: Data(contentsOf: f)) as! [String: Any]
    let W = spec["w"] as! Int, H = spec["h"] as! Int
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: W, pixelsHigh: H, bitsPerSample: 8,
                               samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
                               bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    let ctx = NSGraphicsContext(bitmapImageRep: rep)!
    NSGraphicsContext.current = ctx
    // flip so y grows downward like the spec
    let tr = NSAffineTransform(); tr.translateX(by: 0, yBy: CGFloat(H)); tr.scaleX(by: 1, yBy: -1); tr.concat()
    NSColor.white.setFill(); NSRect(x: 0, y: 0, width: W, height: H).fill()
    for it in spec["items"] as! [[String: Any]] {
        let t = it["t"] as! String
        let d = { (k: String) -> CGFloat in CGFloat((it[k] as? Double) ?? 0) }
        if t == "text" {
            let font = NSFont(name: it["f"] as! String, size: d("s")) ?? { fatalError("font \(it["f"]!)") }()
            let s = NSAttributedString(string: it["v"] as! String,
                                       attributes: [.font: font, .foregroundColor: col(it["c"])])
            let sz = s.size()
            var x = d("x")
            if (it["a"] as? String) == "r" { x -= sz.width } else if (it["a"] as? String) == "c" { x -= sz.width / 2 }
            // drawing in a flipped context: use a flipped sub-context so glyphs are upright
            NSGraphicsContext.saveGraphicsState()
            let t2 = NSAffineTransform(); t2.translateX(by: x, yBy: d("y") + sz.height); t2.scaleX(by: 1, yBy: -1); t2.concat()
            s.draw(at: .zero)
            NSGraphicsContext.restoreGraphicsState()
        } else if t == "rect" {
            let r = NSRect(x: d("x"), y: d("y"), width: d("w"), height: d("h"))
            if it["fill"] != nil { col(it["fill"]).setFill(); r.fill() }
            NSColor.black.setStroke(); let p = NSBezierPath(rect: r); p.lineWidth = max(d("lw"), 1); p.stroke()
        } else if t == "line" {
            let p = NSBezierPath(); p.move(to: NSPoint(x: d("x1"), y: d("y1"))); p.line(to: NSPoint(x: d("x2"), y: d("y2")))
            p.lineWidth = max(d("lw"), 1); col(it["c"]).setStroke(); p.stroke()
        }
    }
    NSGraphicsContext.restoreGraphicsState()
    try rep.representation(using: .png, properties: [:])!.write(to: out)
}
print("rendered", files.count)
