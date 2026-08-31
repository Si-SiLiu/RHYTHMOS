import Foundation
import Vision
import ImageIO
import CoreImage
import CoreImage.CIFilterBuiltins

func fail(_ code: String) -> Never {
    let payload = ["error": code]
    let data = try! JSONSerialization.data(withJSONObject: payload)
    FileHandle.standardOutput.write(data)
    exit(2)
}

guard CommandLine.arguments.count == 2 else { fail("missing_image_path") }
let url = URL(fileURLWithPath: CommandLine.arguments[1]) as CFURL
guard let source = CGImageSourceCreateWithURL(url, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    fail("image_decode_failed")
}

func enhancedImage(_ image: CGImage) -> CGImage? {
    // Small, low-contrast nutrition labels benefit substantially from a local
    // contrast pass before Vision sees them. Keep the geometry unchanged in
    // normalized coordinates so the table parser can still align columns.
    let input = CIImage(cgImage: image)
    let controls = CIFilter.colorControls()
    controls.inputImage = input
    controls.saturation = 0
    controls.contrast = 1.65
    controls.brightness = 0
    guard let contrasted = controls.outputImage else { return nil }
    let sharpen = CIFilter.sharpenLuminance()
    sharpen.inputImage = contrasted
    sharpen.sharpness = 0.65
    guard let output = sharpen.outputImage else { return nil }
    return CIContext(options: [.useSoftwareRenderer: false]).createCGImage(output, from: output.extent)
}

func recognize(_ image: CGImage) throws -> [VNRecognizedTextObservation] {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    // Nutrition labels in this app are commonly Chinese/English mixtures.
    request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]
    try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
    return request.results ?? []
}

func boxCenter(_ box: CGRect) -> CGPoint {
    CGPoint(x: box.midX, y: box.midY)
}

func boxesRepresentSameText(_ left: CGRect, _ right: CGRect) -> Bool {
    let a = boxCenter(left)
    let b = boxCenter(right)
    let xTolerance = max(left.width, right.width) * 0.65 + 0.008
    let yTolerance = max(left.height, right.height) * 0.65 + 0.008
    return abs(a.x - b.x) <= xTolerance && abs(a.y - b.y) <= yTolerance
}

do {
    var observations = try recognize(image)
    if let enhanced = enhancedImage(image) {
        for candidate in try recognize(enhanced) {
            guard let candidateText = candidate.topCandidates(1).first else { continue }
            let candidateBox = candidate.boundingBox
            if let existingIndex = observations.firstIndex(where: {
                boxesRepresentSameText($0.boundingBox, candidateBox)
            }), let existingText = observations[existingIndex].topCandidates(1).first {
                // Prefer the clearer recognition, while retaining the original
                // when Vision assigns equal confidence to both variants.
                if candidateText.confidence > existingText.confidence {
                    observations[existingIndex] = candidate
                }
            } else {
                observations.append(candidate)
            }
        }
    }
    observations.sort { $0.boundingBox.midY > $1.boundingBox.midY }

    let blocks: [[String: Any]] = observations.compactMap { observation in
        let top = observation.topCandidates(3)
        guard let candidate = top.first else { return nil }
        let box = observation.boundingBox
        return [
            "text": candidate.string,
            "confidence": Double(candidate.confidence),
            "candidates": top.map { ["text": $0.string, "confidence": Double($0.confidence)] },
            "bounding_box": [
                "x": Double(box.origin.x), "y": Double(box.origin.y),
                "width": Double(box.size.width), "height": Double(box.size.height)
            ]
        ]
    }

    let os = ProcessInfo.processInfo.operatingSystemVersion
    let payload: [String: Any] = [
        "engine": "macos_vision",
        "engine_version": "\(os.majorVersion).\(os.minorVersion).\(os.patchVersion)",
        "image_size": ["width": image.width, "height": image.height],
        "text_blocks": blocks,
        "processing_warnings": []
    ]

    let data = try JSONSerialization.data(withJSONObject: payload)
    FileHandle.standardOutput.write(data)
} catch {
    fail("vision_request_failed")
}
