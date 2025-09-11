# Schulmanager Online Integration

Diese Integration ermöglicht es, Daten aus Schulmanager Online in Home Assistant zu integrieren.

## Highlights (v0.4.0)

- Ereignisse für neue Daten (erst nach der initialen Aktualisierung):
  - `schulmanager_homework_new` (neue Hausaufgabe)
  - `schulmanager_grade_new` (neue Note)
- Stundenplanänderungen werden blockweise gezählt (adjazente/duplizierte Einträge zusammengeführt)
- Noten werden normalisiert (z. B. `0~2` → `2.0`), Tendenz erfasst (`plus`/`minus`), Originalwert bleibt erhalten
- Noten‑Entitäten mit lesbaren Zusammenfassungen:
  - `grades_summary` (Text)
  - `grades_summary_markdown` (für Markdown‑Karten)
- Diagnostics enthalten sensible Daten geschwärzt; Debug‑Dumps nur noch `*response*.json`
- Nur Service‑Gerät zeigt Integrationsversion (Schülergeräte ohne Firmware‑Angabe)

## Funktionen

### 📅 Stundenplan
- Zeigt aktuelle und kommende Unterrichtsstunden an
- Enthält Fach, Lehrer, Raum und Zeit

### 📝 Hausaufgaben  
- Listet anstehende Hausaufgaben auf
- Mit Fälligkeitsdatum und Details

### 📊 Arbeiten/Klausuren
- Übersicht über geplante Prüfungen
- Inkl. Datum, Fach und Beschreibung

### 🎯 Noten
- Aktuelle Noten nach Fächern
- Gesamtdurchschnitt des Schülers
- Deutsche Notenskala (1-6)

## Konfiguration

Die Integration kann vollständig über die Home Assistant UI konfiguriert werden:

1. **Zugangsdaten**: Schulmanager E-Mail und Passwort
2. **Features**: Einzelne Module aktivieren/deaktivieren
3. **Zeitbereich**: Vergangene/zukünftige Tage für Prüfungen
4. **Cooldown**: Manuelle Aktualisierung 5-30 Minuten (Button „Schulmanager jetzt aktualisieren“)

## Entitäten

### Sensoren
- Stundenplan-Sensoren für jeden Schüler
- Hausaufgaben-Übersicht
- Arbeiten/Klausuren
- Noten nach Fächern
- Gesamtdurchschnitt

### To-Do Listen
- Hausaufgaben als erledigbare Aufgaben

### Kalender
- Prüfungstermine

### Buttons
- Manuelle Aktualisierung

## Automationen / Events

Du kannst auf neue Daten mit Automationen reagieren (erst nachdem die Integration mindestens einmal erfolgreich aktualisiert hat):

```yaml
automation:
  - alias: Neue Hausaufgabe
    trigger:
      - platform: event
        event_type: schulmanager_homework_new
    action:
      - service: persistent_notification.create
        data:
          title: "Neue Hausaufgabe"
          message: "{{ trigger.event.data.student_name }}: {{ trigger.event.data.item.subject }} – {{ trigger.event.data.item.homework }}"

  - alias: Neue Note
    trigger:
      - platform: event
        event_type: schulmanager_grade_new
    action:
      - service: persistent_notification.create
        data:
          title: "Neue Note"
          message: >-
            {{ trigger.event.data.student_name }} – {{ trigger.event.data.subject_name }}:
            {{ trigger.event.data.grade.value }} ({{ trigger.event.data.grade.original_value }})
```

## Lokalisierung

Deutsch und Englisch werden unterstützt. Weitere Sprachen sind auf Anfrage möglich.
