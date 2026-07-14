// Sprecher.swift
// Sprachausgabe mit AVSpeechSynthesizer inkl. Personal Voice (eigene Stimme)
// und einfacher Spul-Logik über Satzgrenzen.
// ACHTUNG: Ungetestetes Starterprojekt — siehe README_iOS.md.

import AVFoundation
import Combine
import SwiftUI

@MainActor
final class Sprecher: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {
    @Published var spielt = false
    @Published var stimmenInfo = ""   // zeigt an, welche Stimme gerade spricht

    private let synth = AVSpeechSynthesizer()
    private var saetze: [String] = []
    private var index = 0
    private var sprache = "de"
    private var eigeneStimme = true

    override init() {
        super.init()
        synth.delegate = self
        // Zugriff auf die Personal Voice des Nutzers anfragen (iOS 17+)
        AVSpeechSynthesizer.requestPersonalVoiceAuthorization { _ in }
    }

    /// Ist die eigene Stimme (Personal Voice) nutzbar? Klartext für die UI.
    static func personalVoiceStatus() -> String {
        switch AVSpeechSynthesizer.personalVoiceAuthorizationStatus {
        case .authorized:
            let vorhanden = AVSpeechSynthesisVoice.speechVoices()
                .contains { $0.voiceTraits.contains(.isPersonalVoice) }
            return vorhanden
                ? "✅ Deine Personal Voice ist bereit."
                : "⚠️ Zugriff erlaubt, aber keine Personal Voice gefunden — in Einstellungen → Bedienungshilfen → Personal Voice erstellen (Training + eine Nacht warten)."
        case .denied:
            return "❌ Zugriff verweigert — Einstellungen → Bedienungshilfen → Personal Voice → \"Apps dürfen Zugriff anfordern\" aktivieren."
        case .unsupported:
            return "❌ Dieses iPhone unterstützt Personal Voice nicht (braucht iOS 17+)."
        default:
            return "⚠️ Zugriff noch nicht angefragt — einmal ▶ Play drücken und die Abfrage erlauben."
        }
    }

    /// Ohne .playback-Kategorie bleibt die Sprachausgabe bei aktiviertem
    /// Stummschalter des iPhones KOMPLETT stumm — haeufigster Grund fuer
    /// "Play tut nichts".
    private func aktiviereAudio() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .spokenAudio)
        try? session.setActive(true)
    }

    func playPause(text: String, sprache: String, eigeneStimme: Bool,
                   startZeichen: Int = 0) {
        if synth.isSpeaking && !synth.isPaused {
            synth.pauseSpeaking(at: .word)
            spielt = false
            return
        }
        if synth.isPaused {
            synth.continueSpeaking()
            spielt = true
            return
        }
        // Neu starten: Text in Sätze teilen, damit Spulen möglich ist
        aktiviereAudio()
        self.sprache = sprache
        self.eigeneStimme = eigeneStimme
        saetze = text.split(whereSeparator: { ".!?".contains($0) })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        // Wiedergabe beim Satz starten, in dem der Cursor steht
        index = 0
        var summe = 0
        for (i, satz) in saetze.enumerated() {
            summe += satz.count + 1
            if startZeichen < summe { index = i; break }
        }
        sprichAktuellenSatz()
    }

    func stopp() {
        synth.stopSpeaking(at: .immediate)
        index = 0
        spielt = false
    }

    /// Für den Live-Modus: Satz sofort in die Sprech-Warteschlange legen
    /// (AVSpeechSynthesizer spielt Utterances automatisch nacheinander ab).
    func sprichZusatz(text: String, sprache: String, eigeneStimme: Bool) {
        let satz = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !satz.isEmpty else { return }
        aktiviereAudio()
        self.sprache = sprache
        self.eigeneStimme = eigeneStimme
        let utterance = AVSpeechUtterance(string: satz)
        utterance.voice = passendeStimme()
        synth.speak(utterance)
    }

    /// „⏪ 10 s“: ein Satz zurück (Satzgrenzen als praktikable Näherung)
    func spuleZurueck() { springe(um: -1) }
    /// „10 s ⏩“: ein Satz vor
    func spuleVor() { springe(um: +1) }

    private func springe(um schritt: Int) {
        guard !saetze.isEmpty else { return }
        synth.stopSpeaking(at: .immediate)
        index = min(max(0, index + schritt), saetze.count - 1)
        sprichAktuellenSatz()
    }

    private func sprichAktuellenSatz() {
        guard index < saetze.count else { spielt = false; return }
        let utterance = AVSpeechUtterance(string: saetze[index])
        utterance.voice = passendeStimme()
        synth.speak(utterance)
        spielt = true
    }

    private func passendeStimme() -> AVSpeechSynthesisVoice? {
        let alle = AVSpeechSynthesisVoice.speechVoices()

        // Wunsch des Nutzers: Personal Voice IMMER verwenden, in jeder
        // Zielsprache (fremdsprachig klingt die Aussprache dann wie der
        // Sprecher selbst in dieser Sprache — bewusste Entscheidung).
        if eigeneStimme,
           let pv = alle.first(where: { $0.voiceTraits.contains(.isPersonalVoice) }) {
            stimmenInfo = pv.language.hasPrefix(sprache)
                ? "Es spricht: deine Personal Voice"
                : "Es spricht: deine Personal Voice (fremdsprachiger Text — Aussprache trägt deine Sprechweise)"
            return pv
        }
        if eigeneStimme {
            stimmenInfo = "Personal Voice nicht verfügbar — Einstellungen → Bedienungshilfen → Personal Voice prüfen"
        }

        // Sonst: beste NATIVE Stimme der Zielsprache (Premium > Enhanced >
        // Standard). Die Standard-Kompaktstimmen klingen blechern.
        func guete(_ v: AVSpeechSynthesisVoice) -> Int {
            switch v.quality {
            case .premium: return 3
            case .enhanced: return 2
            default: return 1
            }
        }
        let kandidaten = alle.filter { $0.language.hasPrefix(sprache)
                                       && !$0.voiceTraits.contains(.isPersonalVoice) }
        if let beste = kandidaten.max(by: { guete($0) < guete($1) }) {
            let stufe = ["", " (Standard — bessere Stimme ladbar, siehe Anleitung)",
                         " (Enhanced)", " (Premium)"][guete(beste)]
            stimmenInfo = "Es spricht: \(beste.name)\(stufe)"
            if eigeneStimme {
                stimmenInfo += " — Personal Voice spricht nur Deutsch"
            }
            return beste
        }
        stimmenInfo = "Keine Stimme für \"\(sprache)\" installiert"
        return AVSpeechSynthesisVoice(language: sprache)
    }

    // Nächsten Satz anschließen
    nonisolated func speechSynthesizer(_ s: AVSpeechSynthesizer,
                                       didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor in
            index += 1
            if index < saetze.count && spielt {
                sprichAktuellenSatz()
            } else {
                spielt = false
            }
        }
    }
}
