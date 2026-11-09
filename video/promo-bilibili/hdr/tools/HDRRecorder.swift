import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreMedia
import CoreVideo

final class Capture: NSObject, SCStreamOutput, SCStreamDelegate {
    let writer: AVAssetWriter
    let input: AVAssetWriterInput
    let adaptor: AVAssetWriterInputPixelBufferAdaptor
    var firstPTS: CMTime?
    var lastPTS = CMTime.invalid
    var count = 0
    var dropped = 0
    var printed = false
    let fps: Int32
    let width: Int
    let height: Int

    init(url: URL, width: Int, height: Int, fps: Int32, bitrate: Int) throws {
        self.width = width; self.height = height; self.fps = fps
        try? FileManager.default.removeItem(at: url)
        writer = try AVAssetWriter(outputURL: url, fileType: .mov)
        let settings: [String: Any] = [
            AVVideoCodecKey: AVVideoCodecType.hevc,
            AVVideoWidthKey: width,
            AVVideoHeightKey: height,
            AVVideoCompressionPropertiesKey: [
                AVVideoAverageBitRateKey: bitrate,
                AVVideoProfileLevelKey: kVTProfileLevel_HEVC_Main10_AutoLevel as String,
                kVTCompressionPropertyKey_HDRMetadataInsertionMode as String: kVTHDRMetadataInsertionMode_Auto as String,
                AVVideoExpectedSourceFrameRateKey: Int(fps),
                AVVideoMaxKeyFrameIntervalKey: Int(fps) * 2,
            ],
            AVVideoColorPropertiesKey: [
                AVVideoColorPrimariesKey: AVVideoColorPrimaries_ITU_R_2020,
                AVVideoTransferFunctionKey: AVVideoTransferFunction_SMPTE_ST_2084_PQ,
                AVVideoYCbCrMatrixKey: AVVideoYCbCrMatrix_ITU_R_2020,
            ],
        ]
        input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        input.expectsMediaDataInRealTime = true
        adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: nil)
        super.init()
        guard writer.canAdd(input) else { throw NSError(domain: "rec", code: 1) }
        writer.add(input)
    }

    func start() throws {
        guard writer.startWriting() else { throw writer.error ?? NSError(domain: "rec", code: 2) }
        writer.startSession(atSourceTime: .zero)
        print("writer started status=\(writer.status.rawValue)")
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen, sampleBuffer.isValid, let pb = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        guard let arr = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
              let raw = arr.first?[.status] as? Int, let st = SCFrameStatus(rawValue: raw), st == .complete else { dropped += 1; return }
        let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        if firstPTS == nil {
            firstPTS = pts
            print("firstPTS=\(pts.seconds) pb=\(CVPixelBufferGetWidth(pb))x\(CVPixelBufferGetHeight(pb)) pf=\(CVPixelBufferGetPixelFormatType(pb))")
            let keys = [kCVImageBufferColorPrimariesKey, kCVImageBufferTransferFunctionKey, kCVImageBufferYCbCrMatrixKey, kCVImageBufferMasteringDisplayColorVolumeKey, kCVImageBufferContentLightLevelInfoKey]
            for k in keys { print("attach \(k as String) = \(String(describing: CVBufferCopyAttachment(pb, k as CFString, nil)))") }
        }
        let t = CMTimeSubtract(pts, firstPTS!)
        if lastPTS.isValid && t <= lastPTS { dropped += 1; return }
        while !input.isReadyForMoreMediaData { usleep(500) }
        if adaptor.append(pb, withPresentationTime: t) {
            lastPTS = t; count += 1
            if count % 120 == 0 { print("frames=\(count) t=\(String(format:"%.2f",t.seconds))") }
        } else {
            dropped += 1
            if !printed { print("append error \(String(describing: writer.error))"); printed = true }
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) { print("stream stopped error=\(error)") }

    func finish() {
        input.markAsFinished()
        let sem = DispatchSemaphore(value: 0)
        writer.finishWriting { sem.signal() }
        sem.wait()
        print("finish status=\(writer.status.rawValue) err=\(String(describing: writer.error)) frames=\(count) dropped=\(dropped)")
    }
}

@main struct Rec {
 static func main() async throws {
  let a = CommandLine.arguments
  guard a.count >= 8 else { print("usage: out seconds x y w h fps [bitrateMbps]"); return }
  let out = a[1], seconds = Double(a[2])!, x = Double(a[3])!, y = Double(a[4])!, w = Double(a[5])!, h = Double(a[6])!, fps = Int32(a[7])!
  let mbps = a.count > 8 ? Int(a[8])! : 60
  let presetArg = a.count > 9 ? a[9] : "rec"
  print("preflight=\(CGPreflightScreenCaptureAccess()) out=\(out) \(seconds)s rect=\(x),\(y),\(w),\(h) fps=\(fps)")
  let c = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
  guard let d = c.displays.first else { print("no display"); return }
  let preset: SCStreamConfiguration.Preset
  switch presetArg {
  case "canonical": preset = .captureHDRStreamCanonicalDisplay
  case "local": preset = .captureHDRStreamLocalDisplay
  default: preset = .captureHDRRecordingPreservedSDRHDR10
  }
  let cfg = SCStreamConfiguration(preset: preset)
  print("preset=\(presetArg)")
  cfg.width = Int(w * 2); cfg.height = Int(h * 2)
  cfg.sourceRect = CGRect(x: x, y: y, width: w, height: h)
  cfg.showsCursor = false
  cfg.minimumFrameInterval = CMTime(value: 1, timescale: fps)
  cfg.queueDepth = 8
  print("cfg w=\(cfg.width) h=\(cfg.height) pf=\(cfg.pixelFormat) dr=\(cfg.captureDynamicRange.rawValue) cs=\(String(describing: cfg.colorSpaceName)) matrix=\(String(describing: cfg.colorMatrix))")
  let filter = SCContentFilter(display: d, excludingWindows: [])
  let cap = try Capture(url: URL(fileURLWithPath: out), width: cfg.width, height: cfg.height, fps: fps, bitrate: mbps * 1_000_000)
  try cap.start()
  let stream = SCStream(filter: filter, configuration: cfg, delegate: cap)
  let q = DispatchQueue(label: "capture", qos: .userInteractive)
  try stream.addStreamOutput(cap, type: .screen, sampleHandlerQueue: q)
  try await stream.startCapture()
  print("capture started")
  try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
  try await stream.stopCapture()
  print("capture stopped")
  cap.finish()
 }
}
