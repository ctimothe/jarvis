import AVFoundation
import Foundation
import Speech

struct CLIArgs {
    let maxSeconds: TimeInterval
    let startupTimeout: TimeInterval
    let language: String
    let daemon: Bool

    static func parse() -> CLIArgs {
        var maxSeconds: TimeInterval = 8
        var startupTimeout: TimeInterval = 4
        var language = "en-US"
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
            daemon: daemon
        )
    }

    static func fromRequestJSON(_ line: String, defaults: CLIArgs) -> CLIArgs {
        guard let data = line.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data),
              let dict = object as? [String: Any]
        else {
            return defaults
        }

        let maxSeconds = (dict["max_seconds"] as? Double) ?? (dict["max_seconds"] as? NSNumber)?.doubleValue ?? defaults.maxSeconds
        let startupTimeout = (dict["startup_timeout"] as? Double) ?? (dict["startup_timeout"] as? NSNumber)?.doubleValue ?? defaults.startupTimeout
        let language = (dict["language"] as? String) ?? defaults.language

        return CLIArgs(
            maxSeconds: max(1, maxSeconds),
            startupTimeout: max(1, startupTimeout),
            language: language,
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
    private let done = DispatchSemaphore(value: 0)

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
            self?.recognitionRequest?.append(buffer)
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
                    self.lastTranscript = transcript
                    if self.firstSpeechAt == nil {
                        self.firstSpeechAt = Date()
                    }
                    self.lastSpeechAt = Date()
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

        DispatchQueue.global().asyncAfter(deadline: .now() + args.startupTimeout) { [weak self] in
            guard let self else { return }
            if self.firstSpeechAt == nil {
                self.finish()
            }
        }

        DispatchQueue.global().asyncAfter(deadline: .now() + args.maxSeconds) { [weak self] in
            self?.finish()
        }

        _ = done.wait(timeout: .now() + args.maxSeconds + 3)
        cleanupAudio()
        return output(error: finishError)
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
        let totalMs = Int(now.timeIntervalSince(startDate) * 1000)
        let firstMs = firstSpeechAt.map { Int($0.timeIntervalSince(startDate) * 1000) }
        var speechDurationMs: Int?
        var speechEndToTranscriptMs: Int?

        if let first = firstSpeechAt, let last = lastSpeechAt {
            speechDurationMs = Int(last.timeIntervalSince(first) * 1000)
            speechEndToTranscriptMs = Int(now.timeIntervalSince(last) * 1000)
        }

        return STTOutput(
            text: lastTranscript,
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
