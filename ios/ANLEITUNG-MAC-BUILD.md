# Schritt für Schritt: Die iOS-App auf dein iPhone bringen

> **Hinweis bei bestehendem Projekt:** Der Code-Ordner heißt seit der
> Umbenennung `ios/EchoMe/` (früher `ios/LiveUebersetzer/`), die Startdatei
> `EchoMeApp.swift`. Ein bereits eingerichtetes Xcode-Projekt musst du
> **nicht** neu anlegen — Projekt- und Dateinamen dort dürfen alt bleiben;
> einfach nur die Datei-**Inhalte** aus dem Repo übernehmen (Swift ist der
> Dateiname egal). Nur bei einem frischen Projekt gilt: Product Name `EchoMe`.

Diese Anleitung setzt **keine Xcode-Erfahrung** voraus. Dauer beim ersten Mal:
ca. 45–60 Minuten (inkl. Downloads).

## Was du brauchst

- Einen **Mac** (macOS 14 „Sonoma" oder neuer; geliehen reicht — der Mac ist
  nur zum Bauen nötig, danach läuft alles auf dem iPhone)
- Dein **iPhone mit iOS 18** + Ladekabel
- Eine **Apple-ID** (deine normale reicht — kostenlos; nur für den App Store
  bräuchte man das 99-€-Entwicklerprogramm)

## Teil 1: Vorbereitung am iPhone (10 Min., schon heute möglich)

1. **Personal Voice erstellen** (dein Stimmklon, einmalig ~15 Min. Sprechen):
   *Einstellungen → Bedienungshilfen → Personal Voice → Personal Voice
   erstellen* — dem Assistenten folgen, Sätze vorlesen. Die Stimme wird
   über Nacht auf dem iPhone fertig berechnet.
2. Dort außerdem aktivieren: **„Apps dürfen Zugriff anfordern"**.
3. **Entwicklermodus** einschalten: *Einstellungen → Datenschutz &
   Sicherheit → Entwicklermodus* → an → iPhone neu starten.
   (Falls der Punkt fehlt: erscheint erst, nachdem Xcode einmal versucht
   hat, die App zu installieren — dann später nachholen.)

## Teil 2: Am Mac (einmalig)

1. **Xcode installieren**: App Store → „Xcode" (kostenlos, ~10 GB — Geduld).
   Beim ersten Start Lizenz bestätigen und Komponenten installieren lassen.
2. **Projekt anlegen**:
   - Xcode → *Create New Project* → **iOS → App** → Next
   - Product Name: `EchoMe` · Interface: **SwiftUI** ·
     Language: **Swift** → Next → Speicherort wählen → Create
3. **Unseren Code hineinnehmen**:
   - Dieses Repository laden: Terminal öffnen und
     `git clone https://github.com/armhana/echome-ai.git`
     (oder auf GitHub: *Code → Download ZIP*)
   - Im Finder den Ordner `echome-ai/ios/EchoMe/` öffnen und
     **alle sechs .swift-Dateien** in den Xcode-Projektnavigator ziehen
     (linke Spalte, auf den gelben Ordner `EchoMe`).
     Im Dialog: „Copy items if needed" ✓ → Finish.
   - Die von Xcode selbst erzeugten `ContentView.swift` und
     `EchoMeApp.swift` **löschen** (Rechtsklick → Delete →
     Move to Trash), unsere ersetzen sie.
4. **Berechtigungs-Texte eintragen** (Pflicht, sonst stürzt die App ab):
   - Projektnavigator: oberster blauer Eintrag `EchoMe` →
     Target `EchoMe` → Reiter **Info** → unter „Custom iOS Target
     Properties" per ➕ zwei Einträge anlegen:
     | Key | Wert |
     |---|---|
     | `Privacy - Speech Recognition Usage Description` | Transkribiert Ihre Videos lokal auf dem Gerät. |
     | `Privacy - Photo Library Usage Description` | Wählt das zu übersetzende Video aus Ihrer Mediathek. |
     | `Privacy - Microphone Usage Description` | Live-Mithören: erkennt Sprache in Ihrer Umgebung, lokal auf dem Gerät. |
5. **Signieren**: Reiter **Signing & Capabilities** →
   „Automatically manage signing" ✓ → bei *Team* → „Add an Account…" →
   mit deiner Apple-ID anmelden → dein „(Personal Team)" auswählen.
   Falls ein Fehler zum *Bundle Identifier* kommt: einen eindeutigen Namen
   eintragen, z. B. `de.areum.liveuebersetzer`.

## Teil 3: Auf das iPhone bringen

1. iPhone per **Kabel** an den Mac. Am iPhone „Diesem Computer vertrauen?"
   → Vertrauen.
2. In Xcode oben in der Gerätewahl (neben dem Schema-Namen) **dein iPhone**
   auswählen (nicht „Simulator").
3. **▶-Knopf** (Run) drücken. Erster Build dauert ein paar Minuten.
4. **Schlüsselbund-Abfrage** („codesign möchte auf den Schlüssel ‚Apple
   Development…' zugreifen"): Hier ist **NICHT** das Apple-ID-/iCloud-
   Passwort gemeint, sondern das **Anmeldepasswort des Mac-Benutzerkontos**
   — das Passwort, das man nach einem Neustart des Macs eintippt (nicht
   Touch ID). Im Zweifel: Mac neu starten, das dort verlangte Passwort ist
   das richtige. Dann **„Immer erlauben"** klicken (sonst fragt jeder Build
   erneut). Geliehener Mac: Besitzer/in muss es eintippen.
5. Beim ersten Start meldet iOS **„Nicht vertrauenswürdiger Entwickler"**.
   Dem Zertifikat vertrauen — der Menüpunkt existiert erst, NACHDEM die
   App installiert wurde:
   - iPhone: *Einstellungen → **Allgemein** → fast ganz unten:
     **VPN & Geräteverwaltung*** (je nach Version „Profile &
     Geräteverwaltung")
   - Abschnitt „ENTWICKLER-APP" → „Apple Development: deine@apple-id"
     antippen → **„…vertrauen"** → bestätigen
   - Das iPhone braucht dabei **Internet** (Apple prüft das Zertifikat)
   - Menüpunkt fehlt? Dann ist die App nicht installiert → in Xcode
     erneut ▶ drücken und warten, bis „Running…" erscheint
6. Beim ersten App-Start Berechtigungen erlauben: Spracherkennung,
   Fotos-Zugriff, **Personal-Voice-Zugriff**.

## Wichtig zu wissen

- **Kostenlose Apple-ID**: Die App läuft 7 Tage, dann einmal neu aus Xcode
  installieren (▶ drücken genügt). Mit Entwicklerprogramm (99 €/Jahr):
  1 Jahr gültig + App-Store-Verteilung möglich.
- **Sprachpakete**: Beim ersten Übersetzen fragt iOS einmalig, ob es das
  Sprachpaket (z. B. Deutsch↔Englisch) laden darf — zustimmen, danach
  ist auch das offline.
- **Personal Voice** ist ein Klon deiner Stimme **inklusive Sprechweise** —
  sie wird nur in ihrer Trainingssprache (Deutsch) verwendet. Für
  „Akzent entfernen" (Deutsch→Deutsch) ist sie ideal; fremde Zielsprachen
  spricht stattdessen die beste installierte native Stimme (die App zeigt
  unter dem Player an, welche Stimme gerade spricht).
- **Bessere Stimmen laden (sehr empfohlen!):** Die vorinstallierten
  Kompaktstimmen klingen blechern. Natürliche Stimmen laden unter
  *Einstellungen → Bedienungshilfen → Gesprochene Inhalte → Stimmen* →
  Sprache wählen → eine Stimme mit **(Premium)** oder **(Enhanced)**
  herunterladen (im WLAN, je ~100–300 MB). Die App nutzt automatisch die
  beste vorhandene.
- **Eigene Stimme, die in JEDER Sprache nativ klingt**, kann nur die
  PC-Version (XTTS-Stimmklon) — Apples Personal Voice ist auf die
  Trainingssprache beschränkt.
- Der Code ist ein **ungetestetes Grundgerüst** — auf einem Windows-PC
  geschrieben. Wenn Xcode beim Bauen Fehler zeigt: Fehlermeldung kopieren
  und mir schicken, ich liefere die Korrektur.

## Wenn etwas hakt — die drei häufigsten Stolpersteine

| Meldung | Lösung |
|---|---|
| „Signing for … requires a development team" | Teil 2, Schritt 5: Apple-ID als Team hinterlegen |
| „codesign möchte auf den Schlüssel … zugreifen" | Teil 3, Schritt 4: **Mac-Anmeldepasswort** (nicht iCloud!) + „Immer erlauben" |
| „Could not launch … untrusted developer" | Teil 3, Schritt 5: unter *Allgemein → VPN & Geräteverwaltung* vertrauen (Internet nötig; Punkt erscheint erst nach Installation) |
| „Cannot find 'X' in scope" / „does not conform to protocol" | Fehlender Import oben in der Datei — Datei aktuell aus dem Repo übernehmen und Meldung melden |
| App startet, stürzt bei Videoauswahl ab | Teil 2, Schritt 4: die Privacy-Einträge fehlen |
| Absturz beim Start von „Live mithören" | Privacy-Eintrag *Microphone Usage Description* fehlt (Teil 2, Schritt 4) |
| „Übersetzung fehlgeschlagen: translation request empty" | Video enthielt keine erkennbare Sprache — oder alte Codefassung: `ContentView.swift` aktuell aus dem Repo übernehmen |
| Play drückt sich, aber kein Ton | 1. **Stummschalter** des iPhones war die Ursache älterer Codefassungen — `Sprecher.swift` aktualisieren, dann spielt es trotz Lautlos · 2. Lautstärke hoch · 3. verbundenen Bluetooth-Kopfhörer prüfen |
