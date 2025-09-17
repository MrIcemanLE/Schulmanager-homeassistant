# 🏫 Schulmanager Online – Home Assistant Integration

Bringt Stundenplan, Arbeiten (Klausuren/Tests), Hausaufgaben und Noten aus Schulmanager Online direkt in Home Assistant. Mit Ereignissen bei neuen Daten, Kalendern pro Schüler und smarten Optionen.

## ✨ Funktionen

- 📅 Stundenplan-Kalender je Schüler
  - Titel: „Fach – Raum“ (z. B. „Mathe – R102“)
  - Hervorhebung per Emoji (optional): ❌ Ausfall, 🔁 Vertretung/Sonderstunde/Lehrerwechsel, 🚪 Raumwechsel, 📝 Prüfung
  - Doppelte Einträge vermieden: Bei Ersatzstunde wird Ausfall in der Beschreibung erwähnt
- 🗓️ Arbeiten-Kalender je Schüler mit Terminen und Details
- 📝 Hausaufgaben als To‑Do‑Liste je Schüler (Status bleibt erhalten)
- 🧮 Noten je Fach + Gesamtdurchschnitt, inkl. Zusammenfassungen (Text/Markdown)
- 🔔 Ereignisse bei neuen Hausaufgaben/Noten (nach der Ersteinrichtung)
- 🧰 Diagnosen mit sicherer Schwärzung sensibler Daten

## 🔧 Einrichtung

1. Integration hinzufügen: „Schulmanager Online“ auswählen und Zugangsdaten eingeben
2. Schüler werden automatisch erkannt; Geräte und Entitäten werden angelegt
3. Optionen anpassen (Einstellungen → Integrationen → Schulmanager → Optionen):
   - „Stundenplan abrufen“ / „Arbeiten abrufen“ / „Hausaufgaben abrufen“ / „Noten abrufen“
   - „Stundenplan Wochen im Voraus (1–3)“
   - „Emoji-Hervorhebung für Änderungen/Ausfälle verwenden“
   - „Ausfälle ausblenden, wenn Hervorhebung aus ist“
   - Abkühlzeit für manuelle Aktualisierung (Buttons/Service)

Hinweis: Die Integration ruft Perioden-Updates asynchron ab und respektiert eine konfigurierbare manuelle Abkühlzeit.

## 🧭 Entitäten & Geräte

- Geräte pro Schüler sowie ein Dienst‑Gerät für die Integration
- Kalender:
  - „SCHÜLERNAME Stundenplan“
  - „SCHÜLERNAME Arbeiten“
- Sensoren je Schüler:
  - Stundenplan heute / morgen (Planmäßig/Abweichung)
  - Stundenplan Änderungen (Anzahl + strukturierte Details)
  - Tage bis nächste Arbeit
  - Noten je Fach + Gesamt
- To‑Do:
  - „Hausaufgaben“ je Schüler

## 🧩 Lovelace – Beispiel (Sections)

```yaml
type: sections
sections:
  - type: grid
    cards:
      - type: calendar
        title: "📅 {{ state_attr('device_tracker.me', 'friendly_name') }} Stundenplan"
        entities:
          - calendar.<dein_schueler_slug>_stundenplan
      - type: calendar
        title: "🗓️ Arbeiten"
        entities:
          - calendar.<dein_schueler_slug>_arbeiten
  - type: grid
    cards:
      - type: entities
        title: "🔔 Änderungen"
        entities:
          - sensor.schulmanager_<schueler_id>_schedule_changes
      - type: entities
        title: "📝 Hausaufgaben"
        entities:
          - todo.schulmanager_<schueler_id>_homework
  - type: grid
    cards:
      - type: entities
        title: "🧮 Noten Überblick"
        entities:
          - sensor.schulmanager_<schueler_id>_grades_overall
```

Ersetze `<dein_schueler_slug>`/`<schueler_id>` entsprechend deinen Entitäten. Die Kalender‑Entitäten werden mit dem Schülernamen angelegt (z. B. „Max Mustermann Stundenplan“).

## 🚀 Manuelle Aktualisierung

- Button „Schulmanager jetzt aktualisieren“ oder Service `schulmanager.refresh`
- Abkühlzeit verhindert zu häufige Abrufe

## 🔔 Ereignisse

- `schulmanager_homework_new` bei neuen Hausaufgaben
- `schulmanager_grade_new` bei neuen Noten

## ℹ️ Hinweise

- Zeiten im Stundenplan werden aus der API übernommen; wenn nicht vorhanden, wird per Stundennummer ein gängiges Raster (45 Min + Pausen) verwendet.
- Die Integration prüft auf doppelte Einträge: Ausfall + Ersatzstunde derselben Stunde erscheinen als ein Termin, der Ausfall steht in der Beschreibung.

