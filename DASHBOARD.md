# 📊 Beispiel-Dashboards (Sections)

Moderne Dashboard-Beispiele mit der aktuellen Entitätsstruktur. Passe die Entity-IDs an deine Installation an: Bei Neuinstallationen ab Home Assistant 2026.8 beginnen sie mit dem Bereich, z. B. `sensor.schule_max_mustermann_stundenplan_heute` statt `sensor.max_mustermann_stundenplan_heute`.

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
          {{ state_attr('sensor.max_mustermann_stundenplan_heute', 'plain') }}
      - type: entities
        title: "🔔 Änderungen"
        show_header_toggle: false
        entities:
          - sensor.max_mustermann_stundenplan_anderungen
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
          - sensor.max_mustermann_tage_bis_nachste_arbeit
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
          {{ state_attr('sensor.max_mustermann_stundenplan_heute', 'plain') }}
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
          - sensor.max_mustermann_noten_ma
          - sensor.max_mustermann_noten_de
          - sensor.max_mustermann_noten_en
  - type: grid
    cards:
      - type: entities
        title: "🔔 Änderungen & Termine"
        show_header_toggle: false
        entities:
          - sensor.max_mustermann_stundenplan_anderungen
          - sensor.max_mustermann_tage_bis_nachste_arbeit
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
            {{ state_attr('sensor.max_mustermann_stundenplan_heute', 'plain') }}
```

## Hinweise

- **Entity-Namen**: Werden automatisch aus dem Schülernamen generiert (z.B. `max_mustermann`); die IDs gelten für Home Assistant auf Deutsch
- **plain-Attribut**: Stundenplan-Sensoren haben ein `plain`-Attribut mit lesbarer Text-Version (perfekt für Benachrichtigungen und Sprachausgabe)
- **Emoji-Logik**: ❌ Entfall, 🔁 Vertretung/geänderter Unterricht, 🚪 Raumwechsel, 📝 Prüfung
- **Multi-School**: Bei mehreren Schulen erhält jeder Schüler einen `sensor.<name>_schule` zur Identifikation
- **Noten-Sensoren**: Werden pro Fach erstellt und nach dem Fachkürzel benannt (z.B. `sensor.max_mustermann_noten_ma`); im Punktesystem mit Einheit „Punkte“
