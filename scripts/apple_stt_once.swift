import AVFoundation
import Foundation
import Speech

struct CLIArgs {
    let maxSeconds: TimeInterval
    let startupTimeout: TimeInterval
    let language: String
    let silenceEndMs: Int
    let minSpeechMs: Int
    let energyFloor: Float
    let energyMultiplier: Float
    let daemon: Bool

    static func parse() -> CLIArgs {
        var maxSeconds: TimeInterval = 8
        var startupTimeout: TimeInterval = 4
        var language = "en-US"
        var silenceEndMs = 420
        var minSpeechMs = 170
        var energyFloor: Float = 0.010
        var energyMultiplier: Float = 2.0
        var daemon = false

        var index = 1
        let argv = CommandLine.arguments
        while index < argv.count {
            let arg = argv[index]
            if arg == "--max-seconds", index + 1 < argv.count {
                maxSeconds = TimeInterval(argv[index + 1]) ?? maxSeconds
                index += 2
                continue
            }
            if arg == "--startup-timeout", index + 1 < argv.count {
                startupTimeout = TimeInterval(argv[index + 1]) ?? startupTimeout
                index += 2
                continue
            }
            if arg == "--language", index + 1 < argv.count {
                language = argv[index + 1]
                index += 2
                continue
            }
            if arg == "--silence-end-ms", index + 1 < argv.count {
                silenceEndMs = Int(argv[index + 1]) ?? silenceEndMs
                index += 2
                continue
            }
            if arg == "--min-speech-ms", index + 1 < argv.count {
                minSpeechMs = Int(argv[index + 1]) ?? minSpeechMs
                index += 2
                continue
            }
            if arg == "--energy-floor", index + 1 < argv.count {
                energyFloor = Float(argv[index + 1]) ?? energyFloor
                index += 2
                continue
            }
            if arg == "--energy-multiplier", index + 1 < argv.count {
                energyMultiplier = Float(argv[index + 1]) ?? energyMultiplier
                index += 2
                continue
            }
            if arg == "--daemon" {
                daemon = true
                index += 1
                continue
            }
            index += 1
        }
        return CLIArgs(
            maxSeconds: max(1, maxSeconds),
            startupTimeout: max(1, startupTimeout),
            language: language,
            silenceEndMs: max(80, silenceEndMs),
            minSpeechMs: max(60, minSpeechMs),
            energyFloor: max(0.001, energyFloor),
            energyMultiplier: max(1.1, energyMultiplier),
            daemon: daemon
        )
    }

    private static func parseDouble(_ value: Any?, default fallback: Double) -> Double {
        if let v = value as? Double { return v }
        if let v = value as? Float { return Double(v) }
        if let v = value as? Int { return Double(v) }
        if let v = value as? NSNumber { return v.doubleValue }
        return fallback
    }

    private static func parseInt(_ value: Any?, default fallback: Int) -> Int {
        if let v = value as? Int { return v }
        if let v = value as? Double { return Int(v) }
        if let v = value as? Float { return Int(v) }
        if let v = value as? NSNumber { return v.intValue }
        return fallback
    }

    static func fromRequestJSON(_ line: String, defaults: CLIArgs) -> CLIArgs {
        guard let data = line.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data),
              let dict = object as? [String: Any]
        else {
            return defaults
        }

        let maxSeconds = parseDouble(dict["max_seconds"], default: defaults.maxSeconds)
        let startupTimeout = parseDouble(dict["startup_timeout"], default: defaults.startupTimeout)
        let language = (dict["language"] as? String) ?? defaults.language
        let silenceEndMs = parseInt(dict["silence_end_ms"], default: defaults.silenceEndMs)
        let minSpeechMs = parseInt(dict["min_speech_ms"], default: defaults.minSpeechMs)
        let energyFloor = Float(parseDouble(dict["energy_floor"], default: Double(defaults.energyFloor)))
        let energyMultiplier = Float(parseDouble(dict["energy_multiplier"], default: Double(defaults.energyMultiplier)))

        return CLIArgs(
            maxSeconds: max(1, maxSeconds),
            startupTimeout: max(1, startupTimeout),
            language: language,
            silenceEndMs: max(80, silenceEndMs),
            minSpeechMs: max(60, minSpeechMs),
            energyFloor: max(0.001, energyFloor),
            energyMultiplier: max(1.1, energyMultiplier),
            daemon: defaults.daemon
        )
    }
}

struct STTOutput: Codable {
    let text: String
    let firstSpeechMs: Int?
    let speechDurationMs: Int?
    let speechEndToTranscriptMs: Int?
    let recognitionTotalMs: Int
    let error: String?
}

enum SpeechAuthCache {
    private static var checked = false
    private static var authorized = false
    private static let lock = NSLock()

    static func ensureAuthorized() -> Bool {
        lock.lock()
        if checked {
            let value = authorized
            lock.unlock()
            return value
        }
        lock.unlock()

        let semaphore = DispatchSemaphore(value: 0)
        var status: SFSpeechRecognizerAuthorizationStatus = .notDetermined
        SFSpeechRecognizer.requestAuthorization { newStatus in
            status = newStatus
            semaphore.signal()
        }
        _ = semaphore.wait(timeout: .now() + 6)

        lock.lock()
        checked = true
        authorized = (status == .authorized)
        let value = authorized
        lock.unlock()
        return value
    }
}

final class AppleSpeechOneShot {
    private let args: CLIArgs
    private let startDate = Date()
    private var firstSpeechAt: Date?
    private var lastSpeechAt: Date?
    private var lastTranscript = ""
    private var finishError: String?
    private var isFinished = false
    private let finishLock = NSLock()
    private let stateLock = NSLock()
    private let done = DispatchSemaphore(value: 0)
    private var adaptiveNoiseFloor: Float = 0.003

    private let audioEngine = AVAudioEngine()
    private var recognitionTask: SFSpeechRecognitionTask?
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognizer: SFSpeechRecognizer?

    init(args: CLIArgs) {
        self.args = args
    }

    func run() -> STTOutput {
        guard SpeechAuthCache.ensureAuthorized() else {
            return output(error: "Speech permission not authorized.")
        }

        recognizer = SFSpeechRecognizer(locale: Locale(identifier: args.language))
        guard let recognizer else {
            return output(error: "Could not initialize SFSpeechRecognizer.")
        }
        if !recognizer.isAvailable {
            return output(error: "Speech recognizer is currently unavailable.")
        }

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        if #available(macOS 10.15, *) {
            request.requiresOnDeviceRecognition = true
        }
        recognitionRequest = request

        let inputNode = audioEngine.inputNode
        let format = inputNode.outputFormat(forBus: 0)
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            guard let self else { return }
            self.recognitionRequest?.append(buffer)
            self.trackAudioEnergy(buffer: buffer, now: Date())
        }

        do {
            audioEngine.prepare()
            try audioEngine.start()
        } catch {
            return output(error: "Failed to start audio engine: \(error.localizedDescription)")
        }

        recognitionTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
            guard let self else { return }
            if let result {
                let transcript = result.bestTranscription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
                if !transcript.isEmpty {
                    self.recordTranscriptActivity(transcript, now: Date())
                }
                if result.isFinal {
                    self.finish()
                    return
                }
            }
            if let error {
                self.finish(error: error.localizedDescription)
            }
        }

        let hardDeadline = Date().addingTimeInterval(args.maxSeconds + 3)
        while Date() < hardDeadline {
            if done.wait(timeout: .now() + 0.05) == .success {
                break
            }

            let now = Date()
            let elapsedMs = Int(now.timeIntervalSince(startDate) * 1000)
            let (first, last) = speechTimes()

            if let first {
                let speechMs = Int(now.timeIntervalSince(first) * 1000)
                let lastSignal = last ?? first
                let silenceMs = Int(now.timeIntervalSince(lastSignal) * 1000)
                if speechMs >= args.minSpeechMs && silenceMs >= args.silenceEndMs {
                    finish()
                    continue
                }
            } else if elapsedMs >= Int(args.startupTimeout * 1000) {
                finish()
                continue
            }

            if elapsedMs >= Int(args.maxSeconds * 1000) {
                finish()
                continue
            }
        }

        if !isDone() {
            finish(error: "recognition watchdog timeout")
        }
        _ = done.wait(timeout: .now() + 0.2)
        cleanupAudio()
        return output(error: finishError)
    }

    private func isDone() -> Bool {
        finishLock.lock()
        let value = isFinished
        finishLock.unlock()
        return value
    }

    private func finish(error: String? = nil) {
        finishLock.lock()
        defer { finishLock.unlock() }
        if isFinished {
            return
        }
        isFinished = true
        if let error, !error.isEmpty {
            finishError = error
        }
        recognitionRequest?.endAudio()
        done.signal()
    }

    private func speechTimes() -> (Date?, Date?) {
        stateLock.lock()
        let first = firstSpeechAt
        let last = lastSpeechAt
        stateLock.unlock()
        return (first, last)
    }

    private func recordTranscriptActivity(_ transcript: String, now: Date) {
        stateLock.lock()
        lastTranscript = transcript
        if firstSpeechAt == nil {
            firstSpeechAt = now
        }
        lastSpeechAt = now
        stateLock.unlock()
    }

    private func computeRMS(_ buffer: AVAudioPCMBuffer) -> Float {
        guard let channelData = buffer.floatChannelData?[0] else { return 0.0 }
        let frameLength = Int(buffer.frameLength)
        if frameLength <= 0 { return 0.0 }
        var sum: Float = 0.0
        for i in 0..<frameLength {
            let sample = channelData[i]
            sum += sample * sample
        }
        return sqrt(sum / Float(frameLength))
    }

    private func trackAudioEnergy(buffer: AVAudioPCMBuffer, now: Date) {
        let rms = computeRMS(buffer)
        if rms <= 0.0001 {
            return
        }
        stateLock.lock()
        if firstSpeechAt == nil {
            adaptiveNoiseFloor = (adaptiveNoiseFloor * 0.97) + (rms * 0.03)
        }
        let threshold = max(args.energyFloor, adaptiveNoiseFloor * args.energyMultiplier)
        if rms >= threshold {
            if firstSpeechAt == nil {
                firstSpeechAt = now
            }
            lastSpeechAt = now
        }
        stateLock.unlock()
    }

    private func cleanupAudio() {
        if audioEngine.isRunning {
            audioEngine.stop()
        }
        audioEngine.inputNode.removeTap(onBus: 0)
        recognitionTask?.cancel()
        recognitionTask = nil
        recognitionRequest = nil
    }

    private func output(error: String?) -> STTOutput {
        let now = Date()
        stateLock.lock()
        let first = firstSpeechAt
        let last = lastSpeechAt
        let text = lastTranscript
        stateLock.unlock()

        let totalMs = Int(now.timeIntervalSince(startDate) * 1000)
        let firstMs = first.map { Int($0.timeIntervalSince(startDate) * 1000) }
        var speechDurationMs: Int?
        var speechEndToTranscriptMs: Int?
        if let first, let last {
            speechDurationMs = Int(last.timeIntervalSince(first) * 1000)
            speechEndToTranscriptMs = Int(now.timeIntervalSince(last) * 1000)
        }

        return STTOutput(
            text: text,
            firstSpeechMs: firstMs,
            speechDurationMs: speechDurationMs,
            speechEndToTranscriptMs: speechEndToTranscriptMs,
            recognitionTotalMs: totalMs,
            error: error
        )
    }
}

func printResult(_ result: STTOutput) {
    let encoder = JSONEncoder()
    encoder.keyEncodingStrategy = .convertToSnakeCase
    if let data = try? encoder.encode(result), let text = String(data: data, encoding: .utf8) {
        print(text)
        fflush(stdout)
    } else {
        print("{\"text\":\"\",\"recognition_total_ms\":0,\"error\":\"encoding failure\"}")
        fflush(stdout)
    }
}

let args = CLIArgs.parse()
if args.daemon {
    while let line = readLine() {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            continue
        }
        if trimmed == "quit" || trimmed == "exit" {
            break
        }
        let req = CLIArgs.fromRequestJSON(trimmed, defaults: args)
        let runner = AppleSpeechOneShot(args: req)
        printResult(runner.run())
    }
} else {
    let runner = AppleSpeechOneShot(args: args)
    printResult(runner.run())
}
