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

    /// Ohne .playback-Kategorie bleibt die Sprachausgabe bei aktiviertem
    /// Stummschalter des iPhones KOMPLETT stumm — haeufigster Grund fuer
    /// "Play tut nichts".
    private func aktiviereAudio() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .spokenAudio)
        try? session.setActive(true)
    }

    func playPause(text: String, sprache: String, eigeneStimme: Bool) {
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
        index = 0
        sprichAktuellenSatz()
    }

    func stopp() {
        synth.stopSpeaking(at: .immediate)
        index = 0
        spielt = false
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

        // Personal Voice NUR in ihrer Trainingssprache verwenden — auf
        // Fremdsprachen angewendet klingt sie stark akzentbehaftet.
        if eigeneStimme,
           let pv = alle.first(where: { $0.voiceTraits.contains(.isPersonalVoice)
                                        && $0.language.hasPrefix(sprache) }) {
            stimmenInfo = "Es spricht: deine Personal Voice"
            return pv
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
        stimmenInfo = "Keine Stimme für „\(sprache)" installiert"
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
