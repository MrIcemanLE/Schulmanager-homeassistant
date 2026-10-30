# 🏫 Schulmanager Online – Home Assistant Integration

Bringt Stundenplan, Arbeiten, Hausaufgaben und Noten aus Schulmanager Online direkt in Home Assistant.

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/MrIcemanLE/Schulmanager-homeassistant)](https://github.com/MrIcemanLE/Schulmanager-homeassistant/releases)

## ✨ Funktionen

- **📅 Kalender pro Schüler** – Stundenplan, Arbeiten/Klausuren und Schultermine (z.B. Schulball, BLF)
- **📝 Hausaufgaben** – Als To‑Do‑Listen mit Status-Verwaltung
- **🧮 Noten** – Pro Fach und Gesamtdurchschnitt mit detaillierten Zusammenfassungen, inkl. Punktesystem der gymnasialen Oberstufe (Sek II, 0–15 Punkte)
- **🔔 Ereignisse** – Bei neuen Hausaufgaben oder Noten
- **✉️ Elternbriefe & Nachrichten** – Anzahl ungelesener Elternbriefe und Messenger-Nachrichten (ohne etwas als gelesen zu markieren)
- **🏫 Multi-School Support** – Automatische Verwaltung bei Kindern an mehreren Schulen

## 🔧 Installation

### Über HACS (empfohlen)
1. HACS öffnen → ⋮ (Menü oben rechts) → **Benutzerdefinierte Repositories**
2. Repository `https://github.com/MrIcemanLE/Schulmanager-homeassistant` mit Typ **Integration** hinzufügen
3. In HACS nach „Schulmanager Online“ suchen und herunterladen
4. Home Assistant neu starten

Voraussetzung: Home Assistant 2024.6 oder neuer.

### Manuelle Installation
1. Dateien aus `custom_components/schulmanager` nach `<config>/custom_components/schulmanager/` kopieren
2. Home Assistant neu starten

## ⚙️ Einrichtung

1. **Integration hinzufügen**
   - Einstellungen → Geräte & Dienste → Integration hinzufügen
   - "Schulmanager Online" auswählen
   - Zugangsdaten (E-Mail + Passwort) eingeben
   - Ist für das Schulmanager-Konto die Zwei-Faktor-Anmeldung aktiv, fragt Home Assistant danach einmal nach dem Code aus der Authenticator-App oder der E-Mail (ab v0.13.0b3, Beta)

2. **Multi-School Accounts**
   - Bei Kindern an mehreren Schulen werden automatisch alle Kinder eingebunden
   - Jede Schule hat bei Schulmanager ein eigenes Konto. Damit alle Kinder erscheinen, brauchen alle Schulkonten dasselbe Passwort. Ist bei einem Schulkonto die Zwei-Faktor-Anmeldung aktiv, wird der Code für diese Schule einzeln abgefragt. Klappt eine Schule nicht, zeigt Home Assistant unter Einstellungen → Reparaturen einen Hinweis an
   - Jeder Schüler erhält einen "Schule"-Sensor zur Identifikation

3. **Konfiguration anpassen**
   - Einstellungen → Geräte & Dienste → Schulmanager Online → **Konfigurieren**

## 🎛️ Konfigurationsparameter

### Datenquellen aktivieren/deaktivieren
| Parameter | Standard | Beschreibung |
|-----------|----------|--------------|
| **Stundenplan abrufen** | ✅ Ein | Stundenplan-Kalender und Stundenplan-Sensoren |
| **Arbeiten abrufen** | ✅ Ein | Kalender für Klausuren/Tests |
| **Hausaufgaben abrufen** | ✅ Ein | To-Do-Listen für Hausaufgaben |
| **Noten abrufen** | ✅ Ein | Noten-Sensoren pro Fach und Gesamtdurchschnitt |
| **Ungelesene Elternbriefe abrufen** | ✅ Ein | Sensor mit Anzahl und Details ungelesener Elternbriefe |
| **Ungelesene Nachrichten abrufen** | ✅ Ein | Sensor mit Anzahl ungelesener Messenger-Nachrichten und betroffenen Unterhaltungen |

### Stundenplan-Einstellungen
| Parameter | Standard | Beschreibung |
|-----------|----------|--------------|
| **Stundenplan Wochen im Voraus** | 2 | Wie viele Wochen im Voraus geladen werden (1-3) |
| **Emoji-Hervorhebung** | ✅ Ein | Markiert Änderungen: ❌ Entfall, 🔁 Vertretung/geänderter Unterricht, 🚪 Raumwechsel, 📝 Prüfung |
| **Ausfälle ausblenden** | ❌ Aus | Versteckt Ausfälle wenn Emoji-Hervorhebung deaktiviert ist |

### Aktualisierung
| Parameter | Standard | Beschreibung |
|-----------|----------|--------------|
| **Abkühlzeit für manuelle Aktualisierung** | 5 Min | Mindestabstand zwischen zwei manuellen Aktualisierungen (5–30 Min) |
| **Tage in der Vergangenheit** | 30 | Zeitraum für rückwirkend abgerufene Daten (z.B. Arbeiten/Schultermine) |
| **Tage in der Zukunft** | 180 | Zeitraum für im Voraus abgerufene Daten (z.B. Arbeiten/Schultermine) |

## 📊 Entitäten

Die Integration legt pro Schüler ein Gerät an, dazu das Gerät „Schulmanager Online“ für den Zugang. Alle Geräte werden dem Bereich „Schule“ zugeordnet.

> **Entity-IDs:** Home Assistant bildet neue Entity-IDs seit Version 2026.8 aus Bereich, Gerät und Name. Neu angelegte Entitäten beginnen deshalb mit `schule_`, z. B. `sensor.schule_max_mustermann_stundenplan_heute`. Entitäten, die schon vorher existierten, behalten ihre ID ohne Präfix – bei länger bestehenden Installationen kann es also beides geben. Die Liste unten zeigt die IDs ohne Präfix für Home Assistant auf Deutsch – die tatsächlichen IDs findest du am einfachsten über das jeweilige Gerät.

### Kalender
- `calendar.<schüler>_stundenplan` – Wöchentlicher Stundenplan mit Änderungen
- `calendar.<schüler>_arbeiten` – Klausuren und Tests
- `calendar.<schüler>_schultermine` – Schulweite Events (z.B. Schulball, BLF)

### Sensoren
- `sensor.<schüler>_aktuelle_stunde` – Aktuelle Unterrichtsstunde (Echtzeit, Minutenaktualisierung)
- `sensor.<schüler>_stundenplan_heute` – Stundenplan heute (Attribute `html`, `plain` und `raw`)
- `sensor.<schüler>_stundenplan_morgen` – Stundenplan morgen
- `sensor.<schüler>_stundenplan_anderungen` – Änderungen für heute/morgen
- `sensor.<schüler>_wochenplan_json` – Wochenplan als JSON (für [Stundenplan Card](https://github.com/fabel-smith/stundenplan-card))
- `sensor.<schüler>_tage_bis_nachste_arbeit` – Tage bis zur nächsten Arbeit
- `sensor.<schüler>_noten_<fachkürzel>` – Noten pro Fach (z. B. `noten_ma`, `noten_de`)
- `sensor.<schüler>_noten_gesamt` – Gesamtdurchschnitt
- `sensor.<schüler>_schule` – Schulname (Diagnose)
- `sensor.<schüler>_schul_id` – Schul-ID (Diagnose)

Im Punktesystem der Oberstufe (0–15) haben die Noten-Sensoren die Einheit „Punkte“, klassische Noten (1–6) haben keine Einheit. Das Attribut `grading_system` nennt das Notensystem mit der Bezeichnung aus Schulmanager („Noten 1 bis 6“ bzw. „Notenpunkte 0 bis 15“).

Pro Zugang am Gerät „Schulmanager Online“:
- **Ungelesene Elternbriefe** – Anzahl ungelesener Elternbriefe; Attribut `letters` mit `title`, `sent`, `deadline`, `students`, `text` (gekürzt) und `attachments`
- **Ungelesene Nachrichten** – Anzahl ungelesener Messenger-Nachrichten; Attribut `threads` mit `subject`, `sender`, `recipients`, `unread` und `last`

Die Entity-IDs lauten z. B. `sensor.schule_schulmanager_online_ungelesene_elternbriefe` (bzw. ohne `schule_`, wenn sie vor Home Assistant 2026.8 angelegt wurden). Hat die Schule das Elternbrief- bzw. Messenger-Modul nicht freigeschaltet, wird der jeweilige Sensor nicht angelegt.

> **Datenschutz/Lesestatus:** Für Elternbriefe wird nur die Liste *ungelesener* Briefe abgefragt (wie das Widget auf der Startseite des Portals) – kein Brief wird geöffnet. Beim Messenger werden nur Zähler und Unterhaltungen geladen, **keine Nachrichtentexte**, damit keine Lesebestätigungen ausgelöst werden. Briefinhalte, Namen und Unterhaltungen werden nicht in der Verlaufsdatenbank von Home Assistant gespeichert.

### To-Do Listen
- `todo.<schüler>_hausaufgaben` – Hausaufgaben mit Status-Verwaltung

### Button
- `button.schulmanager_online_jetzt_aktualisieren` – Manuelle Aktualisierung (am Gerät „Schulmanager Online“)

## 🔔 Ereignisse & Automatisierungen

### Neue Hausaufgaben
```yaml
trigger:
  - platform: event
    event_type: schulmanager_homework_new
action:
  - service: notify.mobile_app
    data:
      message: "Neue Hausaufgabe für {{ trigger.event.data.student_name }}: {{ trigger.event.data.item.subject }} - {{ trigger.event.data.item.homework }}"
```

### Neue Noten
```yaml
trigger:
  - platform: event
    event_type: schulmanager_grade_new
action:
  - service: notify.mobile_app
    data:
      message: "Neue Note für {{ trigger.event.data.student_name }} in {{ trigger.event.data.subject_name }}: {{ trigger.event.data.grade.display_value }}"
```

Beide Ereignisse enthalten `student_id` und `student_name`. `schulmanager_homework_new` liefert die Hausaufgabe unter `item` (u. a. `date`, `subject`, `homework`), `schulmanager_grade_new` zusätzlich `subject_id`, `subject_name` und unter `grade` die Note (u. a. `display_value` wie „2-“ oder „11“, `date`, `topic`).

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
        {{ state_attr('sensor.schueler_beispiel_stundenplan_heute', 'plain') }}
```

Das `plain`-Attribut enthält eine lesbare Version des Stundenplans mit Emoji-Markierung.

## 📅 Stundenplan Card

Mit dem `wochenplan_json`-Sensor lässt sich die [Stundenplan Card](https://github.com/fabel-smith/stundenplan-card) direkt mit Echtzeitdaten aus dem Schulmanager befüllen:

1. Stundenplan Card installieren (HACS → [fabel-smith/stundenplan-card](https://github.com/fabel-smith/stundenplan-card))
2. Karte hinzufügen → Datenquelle: **„Beliebiger Sensor (JSON)“**
3. Sensor auswählen: `sensor.<schüler>_wochenplan_json`, Attribut: `plan`

Jede Zelle enthält mehrzeilig Fach, Lehrkraft und Raum (die Karte muss Zeilenumbrüche darstellen). Änderungen werden direkt an der betroffenen Zeile markiert, der bisherige Wert steht in Klammern: `rei (ber) 🔁` bei Vertretung/Lehrkraftwechsel, `U04 (Ch) 🚪` bei Raumwechsel, `Ma (D) ⚠️` bei geändertem Fach, `E ❌` bei Entfall, `M 📝` bei Prüfung. Sonderstunden und sonstige Änderungen ohne erkennbaren Unterschied erhalten ein `⚠️` am Fach. Fehlt die Lehrkraft- bzw. Raumangabe, steht `🔁` bzw. `🚪` am Fach. Mehrere Stunden in derselben Zelle werden durch eine Leerzeile getrennt. Am Wochenende wird automatisch die nächste Woche angezeigt.

## 🛠️ Aktionen (Dienste)

### `schulmanager.refresh`
Löst eine manuelle Aktualisierung aus (respektiert Cooldown).

```yaml
service: schulmanager.refresh
```

### `schulmanager.clear_cache`
Löscht Sitzungsdaten/Cache der Integration (z.B. bei Login-Problemen).

```yaml
service: schulmanager.clear_cache
```

### `schulmanager.clear_debug`
Löscht alle Debug-Dateien im Integrationsordner, auch solche aus älteren Versionen. Nur für Administratoren.

```yaml
service: schulmanager.clear_debug
```

### `schulmanager.get_schedule` (Beta)
Liefert den Stundenplan aller Kinder strukturiert als Antwort, gedacht für Karten und Integrationen wie die [Stundenplan Suite](https://github.com/fabel-smith/stundenplan-suite). Die Aktion fragt Schulmanager nicht neu ab, sondern gibt die zuletzt abgerufenen Daten zurück. Optional lässt sie sich mit `config_entry_id` auf einen Schulmanager-Eintrag und mit `student_id` auf ein Kind einschränken.

> ⚠️ **Beta:** Das Format kann sich bis zur stabilen Version 0.13.0 noch ändern. Die Aktion ist vorerst nur in Beta-Versionen enthalten. Dafür in HACS für Schulmanager Online Vorabversionen (Pre-Release) zulassen.

```yaml
action: schulmanager.get_schedule
data:
  student_id: "1234567"   # optional
response_variable: stundenplan
```

Pro Kind enthält die Antwort einen `status` (`ok`, `stale` = letzter Abruf fehlgeschlagen, ältere Daten, `unavailable` = noch keine Daten), den abgerufenen Zeitraum, die Stundenzeiten und für jeden Tag die Stunden mit Fach, Kurs bzw. Gruppe, Lehrkräften, Räumen und Änderungen. Liefert die Schule mehrere Kurse in derselben Stunde, erscheint jeder Kurs einzeln.

Sobald sich der Stundenplan eines Kindes ändert, löst die Integration das Ereignis `schulmanager_schedule_updated` aus (mit `config_entry_id` und `student_ids`).

## 📝 Beispiel Lovelace-Karte

```yaml
type: vertical-stack
cards:
  - type: calendar
    entities:
      - calendar.schueler_beispiel_stundenplan
  - type: todo-list
    entity: todo.schueler_beispiel_hausaufgaben
  - type: entities
    entities:
      - sensor.schueler_beispiel_noten_gesamt
      - sensor.schueler_beispiel_tage_bis_nachste_arbeit
```

## ❓ Häufige Fragen

**Q: Warum werden keine Noten angezeigt?**
A: Stelle sicher, dass "Noten abrufen" in den Optionen aktiviert ist. Die API liefert nur Noten, die auch im Schulmanager-Portal sichtbar sind.

**Q: Kann ich beide Schulen meiner Kinder nutzen?**
A: Ja! Ab v0.6.0 werden automatisch alle Schulen eingebunden. Jeder Schüler hat einen Diagnose-Sensor, der die Schulzugehörigkeit zeigt.

**Q: Kann ich mehrere Schulmanager-Accounts verwenden?**
A: Ja! Die Integration kann mehrfach eingerichtet werden. Füge einfach die Integration erneut hinzu und verwende andere Zugangsdaten.

**Q: Was bedeuten die Emojis im Stundenplan?**
A: ❌ = Entfall, 🔁 = Vertretung/Sonderstunde/Lehrerwechsel/geänderter Unterricht, 🚪 = Raumwechsel, 📝 = Prüfung

**Q: Wie oft aktualisiert die Integration?**
A: Automatisch einmal pro Stunde. Zusätzlich lässt sich jederzeit manuell aktualisieren (Button oder Dienst `schulmanager.refresh`), mit einstellbarer Wartezeit zwischen zwei manuellen Abrufen (Standard: 5 Min).

**Q: Werden Noten im Punktesystem der gymnasialen Oberstufe (Sek II) unterstützt?**
A: Ja, ab v0.10.0. Kurse mit dem 0–15-Punkte-System werden automatisch erkannt und korrekt dargestellt – keine Konfiguration nötig. Der Gesamtdurchschnitt wird im Notensystem berechnet, in dem die meisten Fächer benotet sind (beide Systeme werden nie gemischt), und trägt im Punktesystem die Einheit „Punkte“. Er ist ein einfacher Mittelwert der Kurse, keine Abitur-Prognose.

**Q: Funktioniert die Zwei-Faktor-Anmeldung von Schulmanager?**
A: Ja, ab v0.13.0b3 (Beta). Bei der Einrichtung gibst du den Code einmal ein. Schulmanager merkt sich Home Assistant danach wie die Schulmanager-App als Gerät, weitere Anmeldungen brauchen keinen Code. Läuft das Gerät ab oder wird es entfernt, erscheint unter Einstellungen → System → Reparaturen der Hinweis „Zwei-Faktor-Code nötig“. Ein Klick darauf öffnet einen Dialog, in dem du nur den aktuellen Code eingibst. Entfernst du die Integration, wird das Gerät auch aus deinem Schulmanager-Konto gelöscht.

**Q: Was passiert, wenn sich mein Schulmanager-Passwort ändert?**
A: Home Assistant zeigt automatisch eine Reauth-Benachrichtigung an, über die du die neuen Zugangsdaten eingeben kannst, ohne die Integration neu einzurichten.

## 🐛 Fehlersuche

### Debug-Protokollierung
1. Einstellungen → Geräte & Dienste → Schulmanager Online → ⋮ → **Debug-Protokoll aktivieren**
2. Das Problem nachstellen (z. B. über den Button „Jetzt aktualisieren“)
3. Über dasselbe Menü **Debug-Protokoll deaktivieren** – Home Assistant lädt das Log automatisch herunter

Solange die Debug-Protokollierung aktiv ist, speichert die Integration zusätzlich die API-Antworten unter `<config>/custom_components/schulmanager/debug/`. Mit dem Dienst `schulmanager.clear_debug` lassen sie sich wieder löschen.

### Diagnose-Download
Einstellungen → Geräte & Dienste → Schulmanager Online → ⋮ → **Diagnosedaten herunterladen** liefert einen Datenexport für Fehlerberichte.

### Datenschutz bei Fehlerberichten
Logs, Debug-Dateien und Diagnose werden automatisch pseudonymisiert: Namen der Kinder und Eltern, E-Mail-Adresse, Schüler-IDs sowie Name und Adresse der Schule erscheinen als Platzhalter wie `<Kind 1>` oder `<Schule>`. Die Diagnose enthält außerdem keine Freitexte (Elternbriefe, Hausaufgaben, Nachrichten). Debug-Dateien können in Freitexten noch Namen anderer Personen enthalten – bitte vor dem Teilen kurz durchsehen.

## 🤝 Beitragen

Issues und Pull Requests sind willkommen: https://github.com/MrIcemanLE/Schulmanager-homeassistant

## 📄 Lizenz

MIT License – siehe [LICENSE](LICENSE)

---

**Hinweis**: Diese Integration ist nicht offiziell von Schulmanager Online unterstützt.
