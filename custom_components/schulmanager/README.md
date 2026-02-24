# 🏫 Schulmanager Online – Home Assistant Integration

Bringt Stundenplan, Arbeiten, Hausaufgaben und Noten aus Schulmanager Online direkt in Home Assistant.

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/MrIcemanLE/Schulmanager-homeassistant)](https://github.com/MrIcemanLE/Schulmanager-homeassistant/releases)

## ✨ Funktionen

- **📅 Kalender pro Schüler** – Stundenplan, Arbeiten/Klausuren und Schultermine (z.B. Schulball, BLF)
- **📝 Hausaufgaben** – Als To‑Do‑Listen mit Status-Verwaltung
- **🧮 Noten** – Pro Fach und Gesamtdurchschnitt mit detaillierten Zusammenfassungen
- **🔔 Ereignisse** – Bei neuen Hausaufgaben oder Noten
- **🏫 Multi-School Support** – Automatische Verwaltung bei Kindern an mehreren Schulen

## 🔧 Installation

### Über HACS (empfohlen)
1. HACS öffnen → Integrationen → ⋮ (Menü) → Benutzerdefinierte Repositories
2. Repository hinzufügen: `https://github.com/MrIcemanLE/Schulmanager-homeassistant`
3. Kategorie: Integration
4. "Schulmanager Online" suchen und installieren
5. Home Assistant neu starten

### Manuelle Installation
1. Dateien aus `custom_components/schulmanager` nach `<config>/custom_components/schulmanager/` kopieren
2. Home Assistant neu starten

## ⚙️ Einrichtung

1. **Integration hinzufügen**
   - Einstellungen → Geräte & Dienste → Integration hinzufügen
   - "Schulmanager Online" auswählen
   - Zugangsdaten (E-Mail + Passwort) eingeben

2. **Multi-School Accounts**
   - Bei Kindern an mehreren Schulen werden automatisch alle Kinder eingebunden
   - Jeder Schüler erhält einen "Schule"-Sensor zur Identifikation

3. **Konfiguration anpassen**
   - Einstellungen → Integrationen → Schulmanager → Optionen

## 🎛️ Konfigurationsparameter

### Datenquellen aktivieren/deaktivieren
| Parameter | Standard | Beschreibung |
|-----------|----------|--------------|
| **Stundenplan abrufen** | ✅ Ein | Kalender und Sensoren für den Stundenplan |
| **Arbeiten abrufen** | ✅ Ein | Kalender für Klausuren/Tests |
| **Hausaufgaben abrufen** | ✅ Ein | To-Do-Listen für Hausaufgaben |
| **Noten abrufen** | ✅ Ein | Noten-Sensoren pro Fach und Gesamtdurchschnitt |

### Stundenplan-Einstellungen
| Parameter | Standard | Beschreibung |
|-----------|----------|--------------|
| **Stundenplan Wochen im Voraus** | 2 | Wie viele Wochen im Voraus geladen werden (1-3) |
| **Emoji-Hervorhebung** | ✅ Ein | Markiert Änderungen: ❌ Entfall, 🔁 Vertretung, 🚪 Raumwechsel, 📝 Prüfung |
| **Ausfälle ausblenden** | ❌ Aus | Versteckt Ausfälle wenn Emoji-Hervorhebung deaktiviert ist |

### Aktualisierung
| Parameter | Standard | Beschreibung |
|-----------|----------|--------------|
| **Manuelle Aktualisierung Cooldown** | 5 Min | Wartezeit zwischen manuellen Updates (5-30 Min) |

### Erweiterte Einstellungen
| Parameter | Standard | Beschreibung |
|-----------|----------|--------------|
| **Debug-Dumps schreiben** | ❌ Aus | Speichert API-Antworten für Fehlerdiagnose |

## 📊 Entitäten

Die Integration erstellt automatisch Entitäten für jeden Schüler:

### Kalender
- `calendar.<schüler>_stundenplan` – Wöchentlicher Stundenplan mit Änderungen
- `calendar.<schüler>_arbeiten` – Klausuren und Tests
- `calendar.<schüler>_schultermine` – Schulweite Events (z.B. Schulball, BLF)

### Sensoren
- `sensor.<schüler>_schedule_today` – Stundenplan heute (mit HTML-Tabelle)
- `sensor.<schüler>_schedule_tomorrow` – Stundenplan morgen
- `sensor.<schüler>_schedule_changes` – Änderungen für heute/morgen
- `sensor.<schüler>_next_exam_days` – Tage bis zur nächsten Arbeit
- `sensor.<schüler>_noten_<fach>` – Noten pro Fach
- `sensor.<schüler>_noten_gesamt` – Gesamtdurchschnitt
- `sensor.<schüler>_schule` – Schulzugehörigkeit (bei Multi-School)

### To-Do Listen
- `todo.<schüler>_hausaufgaben` – Hausaufgaben mit Status-Verwaltung

### Button
- `button.schulmanager_jetzt_aktualisieren` – Manuelle Aktualisierung

## 🔔 Ereignisse & Automatisierungen

### Neue Hausaufgaben
```yaml
trigger:
  - platform: event
    event_type: schulmanager_homework_new
action:
  - service: notify.mobile_app
    data:
      message: "Neue Hausaufgabe: {{ trigger.event.data.subject }} - {{ trigger.event.data.homework }}"
```

### Neue Noten
```yaml
trigger:
  - platform: event
    event_type: schulmanager_grade_new
action:
  - service: notify.mobile_app
    data:
      message: "Neue Note in {{ trigger.event.data.subject }}: {{ trigger.event.data.grade }}"
```

### Stundenplan-Benachrichtigung
```yaml
trigger:
  - platform: time
    at: "07:00:00"
action:
  - service: notify.mobile_app
    data:
      title: "Stundenplan heute"
      message: |
        {{ state_attr('sensor.schueler_a_schedule_today', 'plain') }}
```

Das neue `plain` Attribut enthält eine lesbare Version des Stundenplans mit Emoji-Markierung.

## 🛠️ Services

### `schulmanager.refresh`
Löst eine manuelle Aktualisierung aus (respektiert Cooldown).

```yaml
service: schulmanager.refresh
```

## 📝 Beispiel Lovelace-Karte

```yaml
type: vertical-stack
cards:
  - type: calendar
    entities:
      - calendar.schueler_a_stundenplan
  - type: todo-list
    entity: todo.schueler_a_hausaufgaben
  - type: entities
    entities:
      - sensor.schueler_a_noten_gesamt
      - sensor.schueler_a_next_exam_days
```

## ❓ Häufige Fragen

**Q: Warum werden keine Noten angezeigt?**
A: Stelle sicher, dass "Noten abrufen" in den Optionen aktiviert ist. Die API liefert nur Noten, die auch im Schulmanager-Portal sichtbar sind.

**Q: Kann ich beide Schulen meiner Kinder nutzen?**
A: Ja! Ab v0.6.0 werden automatisch alle Schulen eingebunden. Jeder Schüler hat einen Diagnose-Sensor, der die Schulzugehörigkeit zeigt.

**Q: Kann ich mehrere Schulmanager-Accounts verwenden?**
A: Ja! Die Integration kann mehrfach eingerichtet werden. Füge einfach die Integration erneut hinzu und verwende andere Zugangsdaten.

**Q: Was bedeuten die Emojis im Stundenplan?**
A: ❌ = Entfall, 🔁 = Vertretung/Sonderstunde/Lehrerwechsel, 🚪 = Raumwechsel, 📝 = Prüfung

**Q: Wie oft aktualisiert die Integration?**
A: Automatisch alle 5 Minuten. Manuelle Updates sind mit einstellbarem Cooldown (Standard: 5 Min) möglich.

## 🐛 Fehlersuche

### Debug-Dumps aktivieren
1. Optionen → "Debug-Dumps schreiben" aktivieren
2. Home Assistant neu starten
3. Debug-Dateien finden unter: `<config>/custom_components/schulmanager/debug/`

### Logs prüfen
Einstellungen → System → Logs → Nach "schulmanager" filtern

## 🤝 Beitragen

Issues und Pull Requests sind willkommen: https://github.com/MrIcemanLE/Schulmanager-homeassistant

## 📄 Lizenz

MIT License – siehe [LICENSE](LICENSE)

---

**Hinweis**: Diese Integration ist nicht offiziell von Schulmanager Online unterstützt.
