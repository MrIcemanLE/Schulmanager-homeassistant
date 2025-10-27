# Schulmanager Integration – Changelog

## Unveröffentlicht

### Verbesserungen
- Tabellen nutzen jetzt `width="100%"`, damit die Anzeige die gesamte Kartenbreite einnimmt.
- Stundennummern aus der API bleiben erhalten; die Anzeige sortiert nur aufsteigend und fasst Ausfälle mit Ersatzstunden im selben Block zusammen.
- Stundenplan-Zeilen zeigen die Stundenangabe oben, Kopfzeilen sind linksbündig und markierte Änderungen erhalten ein hellblaues Hintergrund-Highlight ohne "Typ"-Präfix bei Sonderstunden.
- Stundenplan-HTML überarbeitet: Jede Stunde nutzt nun zwei Zeilen, Änderungen werden in der Akzentfarbe hervorgehoben und entfallene Fach-/Lehrkraft-/Raum-Informationen in der zweiten Zeile durchgestrichen angezeigt. Ausfälle erscheinen nicht länger als eigener Block.

## 0.5.3 (2025-10-27)

### Funktionen
- **Mehrschul-Auswahl** (Issue #2): Vollständige Unterstützung für Multi-School-Accounts
  - Bei Accounts mit Kindern an mehreren Schulen erscheint nun ein Auswahl-Dialog im Config Flow
  - Die API gibt bei solchen Accounts ein `multipleAccounts`-Array zurück statt eines JWT-Tokens
  - Nach der Schulauswahl erfolgt ein zweiter Login mit der gewählten `institutionId`
  - Der Re-Authentication-Flow behält die gespeicherte `institutionId` bei
  - Neue Übersetzungen für den Schulauswahl-Schritt in `strings.json`
  - Betroffene Dateien: `api_client.py`, `config_flow.py`, `strings.json`

### Fehlerbehebungen
- **Multi-School-Login**: Der bisherige Ansatz (v0.5.2) versuchte, die `institutionId` aus der Login-Response zu extrahieren, aber bei Multi-School-Accounts fehlt das `user`-Objekt komplett. Jetzt wird stattdessen eine explizite Schulauswahl durch den Nutzer ermöglicht.

## 0.5.2 (2025-10-20)

### Funktionen
- **Mehrschul-Unterstützung** (Issue #2): Konten mit Kindern an mehreren Schulen werden zuverlässig verarbeitet
  - `institutionId` wird nach erfolgreichem Login automatisch extrahiert und gespeichert
  - Bei Re-Authentication kommt die gespeicherte `institutionId` erneut zum Einsatz, um Doppelabfragen zu vermeiden
  - Der Config Flow aktiviert nach erfolgreichem Login automatisch Debug-Dumps für eine schnellere Fehlerdiagnose
  - Betroffene Dateien: `api_client.py`, `config_flow.py`, `__init__.py`

## 0.5.1 (2025-10-20)

### Fehlerbehebungen
- **Schedule-Sensor Tabellen-Sortierung**: HTML-Attribut in den Stundenplan-Sensoren (`schedule_today`, `schedule_tomorrow`) korrigiert, sodass Stunden nun chronologisch nach `classHour.number` angezeigt werden. Zuvor erfolgte die Anzeige in API-Reihenfolge, wodurch die Tabelle unsortiert sein konnte. Jetzt werden die Stunden vor dem Rendern der HTML-Tabelle nach `classHour.number` sortiert.
  - Betroffene Datei: `sensor.py` (`ScheduleSensor.extra_state_attributes`)
  - Neu hinzugefügt: Hilfsfunktion `get_hour_number()` für eine robuste Ermittlung der Stundennummer
  - Stunden ohne Stundennummer landen am Ende der Liste (`hour=999`)

### Repository-/CI-Änderungen
- **Nächtliche Validierung entfernt**: `.github/workflows/validate.yml` gestrichen, um Fehlermeldungen während der Beta-Phase zu vermeiden. Die HACS-Validierung läuft weiterhin über den Workflow `release.yml` und kann ab Version 1.0.0 wieder aktiviert werden.

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
- Vereinheitlichte Schedule-Fallbacks (`today`/`tomorrow`/`week`/`changes`)
- Verbesserte Zeitenzuordnung per Stundennummer (Fallback, falls API-Zeiten fehlen)
- Typing/Lint/Diagnostics verfeinert

## 0.4.0

- Stabile eindeutige IDs pro Schüler/Fach; Laufzeitdaten werden über `entry.runtime_data` verwaltet
- Diagnostik mit Schwärzung sensibler Daten; Debug-Dumps auf Dateien vom Muster `*response*.json` reduziert
- Ereignisse für neue Daten (erst nach dem initialen Refresh):
  - `schulmanager_homework_new`
  - `schulmanager_grade_new`
- Änderungen im Stundenplan werden zu Stundenblöcken zusammengeführt (angrenzende/duplizierte Stunden konsolidiert)
- Noten werden normalisiert (z. B. `0~2` → `2.0`), Tendenzen als `plus`/`minus` gespeichert
- Noten-Entitäten liefern lesbare Zusammenfassungen:
  - `grades_summary`
  - `grades_summary_markdown`
- Cooldown für Koordinator sowie manuellen Aktualisierungs-Button
- `DeviceInfo` enthält `sw_version` nur noch am Service-Gerät (Integrationsversion)
- Übersetzungen (EN/DE) mit `strings.json` synchronisiert
- TypedDicts für Stundenplan/Noten; strengere Typisierung in Koordinator und Plattformen

## 0.3.x und älter

- Erste Iterationen der Custom-Integration (Hausaufgaben, Stundenplan, Prüfungen, Noten)
