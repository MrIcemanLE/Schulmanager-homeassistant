# 📊 Beispiel-Dashboards (Sections)

Nachfolgend moderne Beispiele auf Basis der neuen Entitäten/Struktur. Passe die Entitätsnamen (Schüler‑IDs/Slugs) an deine Installation an.

## Stundenplan & Arbeiten

```yaml
type: sections
sections:
  - type: grid
    cards:
      - type: calendar
        title: "📅 Max Mustermann Stundenplan"
        entities:
          - calendar.max_mustermann_stundenplan
      - type: calendar
        title: "🗓️ Max Mustermann Arbeiten"
        entities:
          - calendar.max_mustermann_arbeiten
```

## Änderungen & Hausaufgaben

```yaml
type: sections
sections:
  - type: grid
    cards:
      - type: entities
        title: "🔔 Änderungen"
        show_header_toggle: false
        entities:
          - sensor.schulmanager_<schueler_id>_schedule_changes
      - type: todo-list
        title: "📝 Hausaufgaben"
        entity: todo.schulmanager_<schueler_id>_homework
```

## Noten Überblick

```yaml
type: sections
sections:
  - type: grid
    cards:
      - type: entities
        title: "🧮 Noten Überblick"
        show_header_toggle: false
        entities:
          - sensor.schulmanager_<schueler_id>_grades_overall
```

Hinweise
- Die Kalender‑Titel werden mit Schülernamen erzeugt (z. B. „Max Mustermann Stundenplan“).
- Der Sensor `schedule_changes` liefert zusätzlich strukturierte Attribute (z. B. `llm_structured_data`) und eine Zusammenfassung.
- Für den Stundenplan werden Doppeltermine (Ausfall + Ersatz) vermieden: der Ausfall erscheint in der Beschreibung des Ersatztermins.

