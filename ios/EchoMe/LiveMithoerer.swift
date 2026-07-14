// LiveMithoerer.swift
// Live-Mithören über das Mikrofon: Gespräch im Raum, YouTube von einem
// anderen Gerät, Vorträge — Satz für Satz erkennen (on-device) und an die
// Übersetzung weiterreichen. Handy-Telefonate kann iOS grundsätzlich nicht
// abgreifen; das hier hört, was das Mikrofon hört.
// ACHTUNG: Ungetestetes Grundgerüst — siehe README_iOS.md.

import AVFoundation
import Combine
import Speech

@MainActor
final class LiveMithoerer: NSObject, ObservableObject {
    @Published var laeuft = false
    @Published var zwischenstand = ""   // aktuell erkannter (noch offener) Satz

    /// Wird für jeden abgeschlossenen Satz aufgerufen.
    var beiSatz: ((String) -> Void)?

    private let engine = AVAudioEngine()
    private var erkenner: SFSpeechRecognizer?
    private var anfrage: SFSpeechAudioBufferRecognitionRequest?
    private var aufgabe: SFSpeechRecognitionTask?
    private var stillTimer: Timer?
    private var letzterStand = ""

    func start(sprache: Locale) throws {
        guard let erk = SFSpeechRecognizer(locale: sprache), erk.isAvailable,
              erk.supportsOnDeviceRecognition else {
            throw NSError(domain: "EchoMe", code: 1, userInfo: [
                NSLocalizedDescriptionKey:
                "Lokales Diktatmodell für diese Sprache fehlt — Einstellungen → Allgemein → Tastatur → Diktat aktivieren."])
        }
        erkenner = erk

        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .default,
                                options: [.defaultToSpeaker, .allowBluetoothA2DP])
        try session.setActive(true)

        starteErkennung()

        let eingang = engine.inputNode
        let format = eingang.outputFormat(forBus: 0)
        eingang.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] puffer, _ in
            self?.anfrage?.append(puffer)
        }
        engine.prepare()
        try engine.start()
        laeuft = true
    }

    private func starteErkennung() {
        anfrage = SFSpeechAudioBufferRecognitionRequest()
        anfrage?.requiresOnDeviceRecognition = true   // nichts verlässt das Gerät
        anfrage?.shouldReportPartialResults = true
        anfrage?.addsPunctuation = true
        letzterStand = ""

        aufgabe = erkenner?.recognitionTask(with: anfrage!) { [weak self] ergebnis, _ in
            guard let self, let ergebnis else { return }
            Task { @MainActor in
                self.letzterStand = ergebnis.bestTranscription.formattedString
                self.zwischenstand = self.letzterStand
                // ~1,3 s keine neuen Wörter -> Satz abschließen, neu lauschen
                self.stillTimer?.invalidate()
                self.stillTimer = Timer.scheduledTimer(withTimeInterval: 1.3,
                                                       repeats: false) { _ in
                    Task { @MainActor in self.satzAbschliessen() }
                }
            }
        }
    }

    private func satzAbschliessen() {
        let satz = letzterStand.trimmingCharacters(in: .whitespacesAndNewlines)
        aufgabe?.cancel(); aufgabe = nil
        anfrage?.endAudio(); anfrage = nil
        zwischenstand = ""
        if !satz.isEmpty { beiSatz?(satz) }
        if laeuft { starteErkennung() }   // sofort weiter lauschen
    }

    func stop() {
        laeuft = false
        stillTimer?.invalidate()
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        aufgabe?.cancel(); aufgabe = nil
        anfrage = nil
        zwischenstand = ""
    }
}
