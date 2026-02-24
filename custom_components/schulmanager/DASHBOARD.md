# 📊 Beispiel-Dashboards (Sections)

Moderne Dashboard-Beispiele mit der aktuellen Entitätsstruktur. Passe die Schülernamen an deine Installation an.

## Stundenplan & Arbeiten

```yaml
type: sections
sections:
  - type: grid
    cards:
      - type: calendar
        title: "📅 Stundenplan"
        entities:
          - calendar.max_mustermann_stundenplan
      - type: calendar
        title: "🗓️ Arbeiten & Klausuren"
        entities:
          - calendar.max_mustermann_arbeiten
      - type: calendar
        title: "🎉 Schultermine"
        entities:
          - calendar.max_mustermann_schultermine
```

## Heutiger Stundenplan

```yaml
type: sections
sections:
  - type: grid
    cards:
      - type: markdown
        title: "📚 Stundenplan heute"
        content: |
          {{ state_attr('sensor.max_mustermann_schedule_today', 'plain') }}
      - type: entities
        title: "🔔 Änderungen"
        show_header_toggle: false
        entities:
          - sensor.max_mustermann_schedule_changes
```

## Hausaufgaben & Noten

```yaml
type: sections
sections:
  - type: grid
    cards:
      - type: todo-list
        title: "📝 Hausaufgaben"
        entity: todo.max_mustermann_hausaufgaben
      - type: entities
        title: "🧮 Noten Überblick"
        show_header_toggle: false
        entities:
          - sensor.max_mustermann_noten_gesamt
          - sensor.max_mustermann_next_exam_days
```

## Vollständige Übersicht

```yaml
type: sections
sections:
  - type: grid
    cards:
      - type: calendar
        title: "📅 Stundenplan"
        entities:
          - calendar.max_mustermann_stundenplan
      - type: calendar
        title: "🎉 Schultermine"
        entities:
          - calendar.max_mustermann_schultermine
      - type: markdown
        title: "📚 Heute"
        content: |
          {{ state_attr('sensor.max_mustermann_schedule_today', 'plain') }}
  - type: grid
    cards:
      - type: todo-list
        title: "📝 Hausaufgaben"
        entity: todo.max_mustermann_hausaufgaben
      - type: entities
        title: "🧮 Noten"
        show_header_toggle: false
        entities:
          - sensor.max_mustermann_noten_gesamt
          - sensor.max_mustermann_noten_mathematik
          - sensor.max_mustermann_noten_deutsch
          - sensor.max_mustermann_noten_englisch
  - type: grid
    cards:
      - type: entities
        title: "🔔 Änderungen & Termine"
        show_header_toggle: false
        entities:
          - sensor.max_mustermann_schedule_changes
          - sensor.max_mustermann_next_exam_days
```

## Automation-Beispiel: Tägliche Stundenplan-Benachrichtigung

```yaml
automation:
  - alias: "Schulmanager: Stundenplan morgens"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: notify.mobile_app
        data:
          title: "Stundenplan heute"
          message: |
            {{ state_attr('sensor.max_mustermann_schedule_today', 'plain') }}
```

## Hinweise

- **Entity-Namen**: Werden automatisch aus dem Schülernamen generiert (z.B. `max_mustermann`)
- **plain-Attribut**: Stundenplan-Sensoren haben ein `plain`-Attribut mit lesbarer Text-Version (perfekt für Benachrichtigungen und Sprachausgabe)
- **Emoji-Logik**: ❌ Entfall, 🔁 Vertretung, 🚪 Raumwechsel, 📝 Prüfung
- **Multi-School**: Bei mehreren Schulen erhält jeder Schüler einen `sensor.<name>_schule` zur Identifikation
- **Noten-Sensoren**: Werden pro Fach erstellt (z.B. `sensor.max_mustermann_noten_mathematik`)
