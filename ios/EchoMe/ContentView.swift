// ContentView.swift
// Hauptoberfläche: Video/Audio/Text hinein → übersetzen → in eigener Stimme
// (Personal Voice) oder Standardstimme ausgeben. Plus Live-Mithören.
// ACHTUNG: Ungetestetes Starterprojekt — siehe README_iOS.md.

import SwiftUI
import PhotosUI
import Translation
import UniformTypeIdentifiers

/// Videos aus der Mediathek als DATEI übernehmen (Apples empfohlener Weg).
struct FilmDatei: Transferable {
    let url: URL
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { film in
            SentTransferredFile(film.url)
        } importing: { empfangen in
            let ziel = FileManager.default.temporaryDirectory
                .appendingPathComponent("eingabe_\(UUID().uuidString).\(empfangen.file.pathExtension)")
            try? FileManager.default.removeItem(at: ziel)
            try FileManager.default.copyItem(at: empfangen.file, to: ziel)
            return FilmDatei(url: ziel)
        }
    }
}

struct ContentView: View {
    @State private var videoItem: PhotosPickerItem?
    @State private var videoURL: URL?
    @State private var zeigeDateiwahl = false
    @State private var texteingabe = ""
    @State private var transkript = ""
    @State private var uebersetzung = ""
    @State private var textAuswahl: TextSelection? = nil  // Cursor im Übersetzungsfeld
    @State private var status = "Bereit."
    @State private var arbeitet = false

    // Sprachen: Quelle (Video/Audio/Live) und Ziel — Vorbelegung Gerätesprache
    @State private var quellsprache = Locale.current.language.languageCode?.identifier ?? "de"
    @State private var zielsprache = Locale.current.language.languageCode?.identifier ?? "de"
    @State private var eigeneStimme = true
    @State private var uebersetzungKonfig: TranslationSession.Configuration?

    // Live-Mithören
    @State private var zeigeZustimmung = false
    @State private var liveSaetze: [String] = []          // wartende Original-Sätze
    @State private var liveKonfig: TranslationSession.Configuration?
    @State private var liveProtokoll = ""

    @StateObject private var sprecher = Sprecher()
    @StateObject private var mithoerer = LiveMithoerer()
    private let erkenner = Transkribierer()

    private let sprachen = ["de", "en", "fr", "es", "it", "pt", "nl", "pl", "tr"]

    var body: some View {
        NavigationStack {
            Form {
                Section("1 · Eingabe: Video, Audio (z. B. Sprachmemo) oder Text") {
                    PhotosPicker("Video aus Mediathek wählen",
                                 selection: $videoItem, matching: .videos)
                    Button("Datei aus „Dateien" wählen (Sprachmemo, MP3, MP4 …)") {
                        zeigeDateiwahl = true
                    }
                    if videoURL != nil {
                        Label("Datei geladen", systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                    }
                    TextField("… oder Text hier einfügen", text: $texteingabe,
                              axis: .vertical)
                        .lineLimit(2...5)
                }

                Section("2 · Sprachen") {
                    Picker("Sprache der Eingabe", selection: $quellsprache) {
                        ForEach(sprachen, id: \.self) { code in
                            Text(Locale.current.localizedString(forLanguageCode: code) ?? code)
                                .tag(code)
                        }
                    }
                    Picker("Zielsprache", selection: $zielsprache) {
                        ForEach(sprachen, id: \.self) { code in
                            Text(Locale.current.localizedString(forLanguageCode: code) ?? code)
                                .tag(code)
                        }
                    }
                    Button("Übersetzen") { starteVerarbeitung() }
                        .disabled((videoURL == nil &&
                                   texteingabe.trimmingCharacters(in: .whitespaces).isEmpty)
                                  || arbeitet)
                    if !transkript.isEmpty {
                        Text(transkript).font(.callout).foregroundStyle(.secondary)
                    }
                }

                Section("3 · Übersetzung — hier korrigieren; Play startet ab dem Cursor") {
                    if uebersetzung.isEmpty {
                        Text("—").foregroundStyle(.tertiary)
                    } else {
                        TextEditor(text: $uebersetzung, selection: $textAuswahl)
                            .font(.callout)
                            .frame(minHeight: 110)
                    }
                }

                Section("4 · Ausgabe") {
                    Toggle("Meine eigene Stimme (Personal Voice)", isOn: $eigeneStimme)
                    if eigeneStimme {
                        Text(Sprecher.personalVoiceStatus())
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    HStack(spacing: 18) {
                        Button { sprecher.spuleZurueck() } label: {
                            Image(systemName: "gobackward.10")
                        }
                        Button {
                            var start = 0
                            if case .selection(let bereich) = textAuswahl?.indices {
                                start = uebersetzung.distance(from: uebersetzung.startIndex,
                                                              to: bereich.lowerBound)
                            }
                            sprecher.playPause(text: uebersetzung,
                                               sprache: zielsprache,
                                               eigeneStimme: eigeneStimme,
                                               startZeichen: start)
                        } label: {
                            Image(systemName: sprecher.spielt ? "pause.circle.fill"
                                                              : "play.circle.fill")
                                .font(.largeTitle)
                        }
                        Button { sprecher.stopp() } label: {
                            Image(systemName: "stop.circle")
                        }
                        Button { sprecher.spuleVor() } label: {
                            Image(systemName: "goforward.10")
                        }
                    }
                    .buttonStyle(.borderless)
                    .disabled(uebersetzung.isEmpty)
                    if !sprecher.stimmenInfo.isEmpty {
                        Text(sprecher.stimmenInfo)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }

                Section("5 · Live mithören (Gespräch im Raum, YouTube, Vortrag)") {
                    Text("Hört über das Mikrofon mit und spricht jede erkannte Aussage " +
                         "übersetzt nach — mit neutraler Standardstimme (schnell und klar). " +
                         "Handy-Telefonate kann iOS-Apps grundsätzlich nicht abgreifen.")
                        .font(.footnote).foregroundStyle(.secondary)
                    Button(mithoerer.laeuft ? "■ Live-Mithören stoppen"
                                            : "▶ Live-Mithören starten") {
                        if mithoerer.laeuft {
                            mithoerer.stop()
                            status = "Live-Mithören gestoppt."
                        } else {
                            zeigeZustimmung = true
                        }
                    }
                    if mithoerer.laeuft && !mithoerer.zwischenstand.isEmpty {
                        Text("🎙 " + mithoerer.zwischenstand)
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                    if !liveProtokoll.isEmpty {
                        Text(liveProtokoll).font(.footnote)
                    }
                }

                Section { Text(status).font(.footnote).foregroundStyle(.secondary) }
            }
            .navigationTitle("EchoMe")
        }
        .onChange(of: videoItem) { ladeVideo() }
        .fileImporter(isPresented: $zeigeDateiwahl,
                      allowedContentTypes: [.audio, .movie]) { ergebnis in
            if case .success(let url) = ergebnis {
                let zugriff = url.startAccessingSecurityScopedResource()
                defer { if zugriff { url.stopAccessingSecurityScopedResource() } }
                let ziel = FileManager.default.temporaryDirectory
                    .appendingPathComponent("import_\(UUID().uuidString).\(url.pathExtension)")
                try? FileManager.default.removeItem(at: ziel)
                do {
                    try FileManager.default.copyItem(at: url, to: ziel)
                    videoURL = ziel
                    status = "Datei bereit."
                } catch {
                    status = "Datei-Import fehlgeschlagen: \(error.localizedDescription)"
                }
            }
        }
        // Einwilligung vor dem Live-Mithören (alle Beteiligten!)
        .alert("Einwilligung erforderlich", isPresented: $zeigeZustimmung) {
            Button("Alle haben zugestimmt — starten") { starteLive() }
            Button("Abbrechen", role: .cancel) {}
        } message: {
            Text("Das Live-Mithören verarbeitet auch die Stimmen anderer Personen. " +
                 "Bitte bestätige, dass ALLE Beteiligten der Verarbeitung zugestimmt " +
                 "haben (§ 201 StGB, DSGVO). Die Verarbeitung bleibt vollständig " +
                 "auf diesem Gerät.")
        }
        // Übersetzung für Datei/Text-Aufträge
        .translationTask(uebersetzungKonfig) { session in
            let text = transkript.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else {
                status = "Keine Sprache erkannt — bitte Datei mit deutlicher Sprache wählen."
                arbeitet = false
                return
            }
            do {
                let antwort = try await session.translate(text)
                uebersetzung = antwort.targetText
                status = "Übersetzung fertig — mit ▶ anhören."
            } catch {
                status = "Übersetzung fehlgeschlagen: \(error.localizedDescription)"
            }
            arbeitet = false
        }
        // Übersetzung für Live-Sätze: nimmt die Warteschlange, spricht sofort
        .translationTask(liveKonfig) { session in
            while !liveSaetze.isEmpty {
                let satz = liveSaetze.removeFirst()
                do {
                    let antwort = try await session.translate(satz)
                    liveProtokoll = "→ " + antwort.targetText
                    sprecher.sprichZusatz(text: antwort.targetText,
                                          sprache: zielsprache,
                                          eigeneStimme: false)  // Live: Standardstimme
                } catch {
                    liveProtokoll = "Übersetzung fehlgeschlagen: \(error.localizedDescription)"
                }
            }
        }
    }

    private func ladeVideo() {
        guard let item = videoItem else { return }
        status = "Lade Video…"
        Task {
            do {
                if let film = try await item.loadTransferable(type: FilmDatei.self) {
                    videoURL = film.url
                    status = "Video bereit."
                } else {
                    status = "Video konnte nicht geladen werden."
                }
            } catch {
                status = "Video-Import fehlgeschlagen: \(error.localizedDescription)"
            }
        }
    }

    private func starteVerarbeitung() {
        let tippText = texteingabe.trimmingCharacters(in: .whitespacesAndNewlines)
        arbeitet = true

        // Fall A: eingetippter/eingefügter Text — keine Erkennung nötig
        if videoURL == nil && !tippText.isEmpty {
            transkript = tippText
            uebersetzeTranskript()
            return
        }

        // Fall B: Video-/Audiodatei transkribieren
        guard let url = videoURL else { arbeitet = false; return }
        status = "Transkribiere lokal…"
        Task {
            do {
                transkript = try await erkenner.transkribiere(
                    videoURL: url, sprache: Locale(identifier: quellsprache))
                uebersetzeTranskript()
            } catch {
                status = "Fehler: \(error.localizedDescription)"
                arbeitet = false
            }
        }
    }

    /// Gemeinsame Übersetzungslogik für Datei- und Text-Eingaben.
    private func uebersetzeTranskript() {
        status = "Übersetze lokal…"
        let quelle = Locale.Language(identifier: quellsprache)
        if quellsprache == zielsprache {
            // Gleiche Sprache (Akzent entfernen): direkt übernehmen
            uebersetzung = transkript
            status = "Gleiche Sprache — Text übernommen, mit ▶ vertonen."
            arbeitet = false
        } else if uebersetzungKonfig?.source?.languageCode?.identifier
                    == quelle.languageCode?.identifier,
                  uebersetzungKonfig?.target?.languageCode?.identifier == zielsprache {
            uebersetzungKonfig?.invalidate()   // gleiches Sprachpaar erneut anstoßen
        } else {
            uebersetzungKonfig = TranslationSession.Configuration(
                source: quelle,
                target: Locale.Language(identifier: zielsprache))
        }
    }

    private func starteLive() {
        mithoerer.beiSatz = { satz in
            liveProtokoll = "🎙 " + satz
            if quellsprache == zielsprache {
                // Gleiche Sprache: direkt neutral nachsprechen (Akzent glätten)
                sprecher.sprichZusatz(text: satz, sprache: zielsprache,
                                      eigeneStimme: false)
            } else {
                liveSaetze.append(satz)
                if liveKonfig == nil {
                    liveKonfig = TranslationSession.Configuration(
                        source: Locale.Language(identifier: quellsprache),
                        target: Locale.Language(identifier: zielsprache))
                } else {
                    liveKonfig?.invalidate()
                }
            }
        }
        do {
            try mithoerer.start(sprache: Locale(identifier: quellsprache))
            status = "Live-Mithören läuft — Sprache der Eingabe: \(quellsprache), Ziel: \(zielsprache)."
        } catch {
            status = "Live-Start fehlgeschlagen: \(error.localizedDescription)"
        }
    }
}
