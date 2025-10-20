# Schulmanager Integration – Changelog

## 0.5.2 (2025-10-20)

### Features
- **Multi-School Support** (Issue #2): Unterstützung für Accounts mit Kindern an mehreren Schulen
  - `institutionId` wird nach erfolgreichem Login automatisch extrahiert und gespeichert
  - Bei Re-Authentication wird gespeicherte `institutionId` verwendet
  - Config Flow aktiviert automatisch Debug-Dumps für bessere Fehlerdiagnose
  - Betroffene Dateien: `api_client.py`, `config_flow.py`, `__init__.py`

## 0.5.1 (2025-10-20)

### Bugfixes
- **Schedule Sensor HTML Table Ordering**: Fixed HTML attribute in schedule sensors (`schedule_today`, `schedule_tomorrow`) to display lessons in correct chronological order by class hour number. Previously, lessons were displayed in the order received from API, which could be unsorted. Now lessons are sorted by `classHour.number` before rendering the HTML table.
  - Affected file: `sensor.py` (ScheduleSensor.extra_state_attributes)
  - Added: `get_hour_number()` helper function for robust hour number extraction
  - Lessons without hour number are placed at end (hour=999)

### Repository/CI Changes
- **Removed nightly validation workflow**: Entfernt `.github/workflows/validate.yml` um nächtliche Fehler-Mails während der Beta-Phase zu vermeiden. Die HACS-Validierung erfolgt weiterhin bei Releases über die `release.yml` Workflow. Kann bei v1.0.0+ wieder aktiviert werden.

## 0.5.0

- Pro Schüler eigene Kalender:
  - „SCHÜLERNAME Stundenplan" (Titel: Fach – Raum)
  - „SCHÜLERNAME Arbeiten"
- Doppelte Termine vermeiden: Ausfälle + Ersatzstunde in derselben Stunde werden zusammengeführt; der Ausfall steht in der Beschreibung
- Emoji-Hervorhebung (optional): ❌ Ausfall, 🔁 Vertretung/Sonderstunde/Lehrerwechsel, 🚪 Raumwechsel, 📝 Prüfung
- Optionen:
  - Wochenvorschau für den Stundenplan (1–3 Wochen)
  - Emoji-Hervorhebung an/aus
  - Ausfälle ausblenden, wenn Hervorhebung aus ist (oder als „X" im Titel anzeigen)
  - Abkühlzeit für manuelle Aktualisierung
- Vereinheitlichte Schedule-Fallbacks (today/tomorrow/week/changes)
- Verbesserte Zeitenzuordnung per Stundennummer (Fallback, falls API-Zeiten fehlen)
- Typing/Lint/Diagnostics verfeinert

## 0.4.0

- Stable unique IDs per student/subject; runtime data via `entry.runtime_data`
- Diagnostics with redaction; reduced debug dumps to only `*response*.json`
- Events for new data (post-initial refresh only):
  - `schulmanager_homework_new`
  - `schulmanager_grade_new`
- Schedule changes are merged into hour blocks (adjacent/duplicate lessons consolidated)
- Grades normalized (e.g., `0~2` → `2.0`), tendency captured as `plus`/`minus`
- Grade entities expose readable summaries:
  - `grades_summary`
  - `grades_summary_markdown`
- Coordinator cooldown + manual refresh button cooldown
- DeviceInfo `sw_version` only on the service device (integration version)
- Translations aligned (EN/DE) with strings.json
- TypedDicts for schedule/grades; stronger typing in coordinator/platforms

## 0.3.x and earlier

- Initial custom integration iterations (homework, schedule, exams, grades)
