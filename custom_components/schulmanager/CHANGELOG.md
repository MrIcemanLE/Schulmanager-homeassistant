# Changelog

## 0.5.0 – Stundenplan‑Kalender, Emojis, Deduplizierung, Optionen

- Pro Schüler eigene Kalender:
  - „SCHÜLERNAME Stundenplan“ (Titel: Fach – Raum)
  - „SCHÜLERNAME Arbeiten“
- Doppelte Termine vermeiden: Ausfälle + Ersatzstunde in derselben Stunde werden zusammengeführt; der Ausfall steht in der Beschreibung
- Emoji‑Hervorhebung (optional): ❌ Ausfall, 🔁 Vertretung/Sonderstunde/Lehrerwechsel, 🚪 Raumwechsel, 📝 Prüfung
- Optionen:
  - Wochenvorschau für den Stundenplan (1–3 Wochen)
  - Emoji‑Hervorhebung an/aus
  - Ausfälle ausblenden, wenn Hervorhebung aus ist (oder als „X“ im Titel anzeigen)
  - Abkühlzeit für manuelle Aktualisierung
- Vereinheitlichte Schedule‑Fallbacks (today/tomorrow/week/changes)
- Verbesserte Zeitenzuordnung per Stundennummer (Fallback, falls API‑Zeiten fehlen)
- Typing/Lint/Diagnostics verfeinert

## 0.4.0 – Referenz

- Stabile unique IDs (permanente Schüler/Fach‑IDs)
- Diagnostik mit Geheimnis‑Schwärzung
- Laufzeitdaten auf `entry.runtime_data`
- Ereignisse bei neuen Daten (Hausaufgaben/Noten)
- Stundenplanänderungen konsolidiert
- Noten normalisiert, Tendenzen, Zusammenfassungen
- Cooldown‑Handling für Buttons/Coordinator
- Debug‑Dumps nur noch Response‑Dateien
- `DeviceInfo sw_version` nur auf dem Service‑Gerät (Integrationsversion)
- Übersetzungen EN/DE, Typisierung via TypedDicts

