// Reads text out of an image with Vision, printing one line per observation as
// `confidence<TAB>x<TAB>y<TAB>w<TAB>h<TAB>text` in *image pixel* coordinates
// with the origin at the top left -- the space `screencapture` produces and
// `window_probe` bounds convert into, so a caller never has to flip an axis.
//
// This exists because the EVE launcher is an Electron app: its account list is
// not in the game client's memory (so `eve_read` cannot help) and it exposes
// nothing useful over the accessibility API -- `AXUIElement` on its window
// returns `missing value` for every child. Reading the pixels is the only way
// to find a named character, and hard-coding the avatar's position is what
// CLAUDE.md tells you not to do, since it is per-layout.
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count >= 2 else {
    FileHandle.standardError.write("usage: ocr_probe <image.png>\n".data(using: .utf8)!)
    exit(2)
}
guard let image = NSImage(contentsOfFile: args[1]),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("could not read image\n".data(using: .utf8)!)
    exit(1)
}

let width = CGFloat(cgImage.width), height = CGFloat(cgImage.height)
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false

do {
    try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
} catch {
    FileHandle.standardError.write("vision failed: \(error)\n".data(using: .utf8)!)
    exit(1)
}

for observation in (request.results ?? []) {
    guard let candidate = observation.topCandidates(1).first else { continue }
    // Vision's box is normalised with the origin at the *bottom* left; flip it.
    let box = observation.boundingBox
    let x = box.minX * width
    let w = box.width * width
    let h = box.height * height
    let y = (1.0 - box.maxY) * height
    let text = candidate.string.replacingOccurrences(of: "\t", with: " ")
    print(String(format: "%.3f\t%.0f\t%.0f\t%.0f\t%.0f\t%@",
                 candidate.confidence, x, y, w, h, text))
}
