# Schulmanager Integration – Changelog

## 0.9.0 (2026-03-24)

### ✨ Neues

- **Sensor „Aktuelle Stunde"**
  - Neuer Sensor pro Schüler: `sensor.<schüler>_aktuelle_stunde`
  - Zeigt in Echtzeit an, was gerade in der Schule passiert
  - Mögliche Zustände: aktuelles Fach (z.B. „Mathematik – 3. Stunde"), Pause mit Endzeit, nächste Stunde mit Startzeit, Unterricht beendet, Schulfrei oder Wochenende
  - Aktualisiert sich automatisch jede Minute – kein manueller Refresh nötig
  - Attribute: aktuelles Fach, Lehrer, Raum, Ende der Stunde, nächstes Fach, nächste Startzeit
  - Beispielautomatisierung: Dashboard-Karte die immer die aktuelle Unterrichtsstunde anzeigt

- **Echte Schulzeiten direkt vom Server (Issue #6)**
  - Stundenzeiten (z.B. wann Stunde 3 beginnt und endet) werden jetzt direkt von deiner Schule abgerufen statt hardcodiert zu sein
  - Unterstützt automatisch unterschiedliche Zeiten je Wochentag (z.B. kürzere Stunden am Mittwoch)
  - Kein Konfigurationsaufwand – funktioniert für jede Schule automatisch

### 🐛 Bugfixes

- **Kritischer Fehler im Log alle 60 Sekunden behoben**
  - Jede Minute erschien ein `RuntimeError` im Home-Assistant-Log bezüglich `async_write_ha_state`
  - Betraf den neuen „Aktuelle Stunde"-Sensor
  - Behoben: Callback korrekt als event-loop-sicher markiert

---

## 0.8.2 (2026-03-12)

### 🐛 Bugfixes
- **Stundenplan-Sensoren zeigten nach ca. 1 Stunde „Schulfrei" (Issue #5)**
  - Problem: Nach einem Neustart funktionierten alle Sensoren korrekt. Nach genau einer Stunde zeigten Stundenplan Heute, Morgen und Änderungen fälschlicherweise leere Werte – ein weiterer Neustart stellte die Daten wieder her
  - Ursache: Der Schulmanager-Server gibt JWT-Tokens aus, die nach ~1 Stunde ablaufen. Die Integration erneuerte das Token nur beim ersten Login, nicht bei jedem stündlichen Datenabruf. Der abgelaufene Token führte intern zu einem HTTP-401-Fehler, der still geschluckt wurde und leere Daten hinterließ
  - Lösung: Die Integration erneuert das Authentifizierungs-Token jetzt bei jedem automatischen Datenabruf
  - Betrifft auch: Der „Jetzt aktualisieren"-Button war aus demselben Grund wirkungslos

---

## 0.8.1 (2026-03-11)

### 🐛 Bugfixes
- **Stundenplan-Sensor zeigte fälschlicherweise „Schulfrei" bei Sonderstunden**
  - Problem: Wenn für einen Schultag Sonderstunden ohne Raumangabe im Stundenplan hinterlegt waren (z.B. Exkursionen, Soziales Lernen), schlug der Datenabruf intern fehl
  - Folge: Sowohl der heutige als auch der morgige Stundenplan-Sensor zeigten „Schulfrei", obwohl tatsächlich Unterricht oder Aktivitäten stattfanden
  - Ursache: Ein JSON-`null`-Wert im Raumfeld (`"room": null`) wurde als Python-`None` übergeben, worauf dann `.get()` aufgerufen wurde → Absturz
  - Lösung: Alle betroffenen Stellen nun null-sicher; `"room": null` wird korrekt als „kein Raum" behandelt

---

## 0.8.0 (2026-03-03)

### 🐛 Bugfixes
- **Irreführende Warnung im Log behoben**
  - Single-School-Nutzer sahen fälschlicherweise die Meldung: *"Using deprecated get_students(); please migrate client to get_all_students()"*
  - Diese Warnung war falsch – `get_students()` ist für Single-School-Accounts die korrekte Methode
  - Behoben in: `calendar.py`, `todo.py`

- **Stiller Datenverlust nach HA-Neustart behoben**
  - Problem: Nach einem Neustart von Home Assistant konnten in bestimmten Konstellationen alle Entitäten leer bleiben, ohne dass ein Fehler angezeigt wurde
  - Ursache: Fehlgeschlagene Logins wurden intern still geschluckt; der Coordinator meldete fälschlicherweise „Erfolg" mit leeren Daten
  - Lösung: Fehlgeschlagene Logins lösen jetzt sichtbare Fehler aus – Entitäten zeigen „Nicht verfügbar" statt falscher leerer Daten
  - Behoben in: `api_client.py`, `coordinator.py`

### 🔧 Verbesserungen (intern)
- **Vereinheitlichte Client-Architektur**
  - Single-School- und Multi-School-Login werden jetzt von einer einzigen Klasse verwaltet
  - Keine sichtbare Verhaltensänderung – alle Entitäten und Funktionen bleiben identisch
  - Verbessert die langfristige Wartbarkeit der Integration

---

## 0.7.0 (2026-02-24)

### ✨ Verbesserungen
- **Multi‑School Login zuverlässiger**
  - Stabilere Anmeldung bei Konten mit mehreren Schulen

- **„Tage bis zur nächsten Arbeit“ genauer**
  - Schulweite Termine werden nicht mehr mitgezählt

### 📝 Hinweise
- Keine

---

## 0.6.1 (2026-02-24)

### ✨ Features
- **Schulweite Events in eigenem Kalender**
  - Neuer Kalender `calendar.<schüler>_schultermine` für schulweite Events (z.B. Schulball, BLF, Projektwochen)
  - Der Arbeiten‑Kalender enthält jetzt nur noch reguläre Klassenarbeiten/Klausuren

### 🐛 Bugfixes
- **API wieder funktionsfähig trotz Website‑Änderung**
  - Fallback für `bundleVersion`, damit die API‑Calls wieder zuverlässig funktionieren

### ⚠️ Hinweise
- Nach dem Update Home Assistant neu starten, damit die neuen Kalender‑Entitäten angelegt werden

---

## 0.6.0 (2025-10-29)

### 🎯 Wichtige Verbesserungen

**Multi-School Support komplett überarbeitet**
- **Automatische Verwaltung aller Schulen**: Bei Accounts mit Kindern an mehreren Schulen werden jetzt automatisch alle Kinder eingebunden – ohne manuelle Schulauswahl
- **Neuer Diagnose-Sensor**: Jeder Schüler erhält einen "Schule"-Sensor, der anzeigt, zu welcher Schule er gehört
- **Behebt Login-Problem aus v0.5.3**: Der manuelle Schulauswahl-Dialog von v0.5.3 führte bei einigen Nutzern zu Anmeldefehlern (Status 401). Diese Probleme sind jetzt behoben – die Integration loggt sich parallel zu allen Schulen ein
- **Automatische Migration**: Bestehende Installationen werden beim Update automatisch migriert, keine Neueinrichtung nötig

**Noten werden jetzt korrekt angezeigt**
- Noten mit Tendenz (z.B. 3+, 2-, 4+) werden nun sauber dargestellt
- Die API liefert manchmal das Format "0~3+" – die Integration zeigt jetzt einfach "3+" an
- Die Durchschnittsberechnung behandelt 3+, 3 und 3- alle gleich als 3.0
- Betroffene Sensoren: Alle Noten-Sensoren pro Fach und Gesamtdurchschnitt

**Neues "plain" Attribut für Benachrichtigungen**
- Stundenplan-Sensoren (heute/morgen) haben jetzt ein zusätzliches `plain`-Attribut
- Perfekt für Benachrichtigungen und Sprachausgabe
- Verwendet die gleiche Emoji-Logik wie der Kalender (❌ Entfall, 🔁 Vertretung, 🚪 Raumwechsel, 📝 Prüfung)
- Beispiel: `"1. Std: 🔁 Mathematik – Raum 204 (Vertretung, Hr. Müller)"`

### 🐛 Fehlerbehebungen
- Verwaiste Übersetzungen für den entfernten Schulauswahl-Dialog entfernt
- Schule-Sensor hatte fehlende Entitäts-Attribute

### ⚠️ Wichtige Hinweise
- Falls Sie v0.5.3 nutzen und Multi-School-Probleme hatten: Nach dem Update auf v0.6.0 sollten alle Kinder automatisch sichtbar sein
- Die automatische Migration kann ein paar Sekunden dauern beim ersten Start nach dem Update

---

## 0.5.3 (2025-10-27)

### Funktionen
- **Mehrschul-Auswahl** (Issue #2): Vollständige Unterstützung für Multi-School-Accounts
  - Bei Accounts mit Kindern an mehreren Schulen erscheint nun ein Auswahl-Dialog im Config Flow
  - Die API gibt bei solchen Accounts ein `multipleAccounts`-Array zurück statt eines JWT-Tokens
  - Nach der Schulauswahl erfolgt ein zweiter Login mit der gewählten `institutionId`
  - Der Re-Authentication-Flow behält die gespeicherte `institutionId` bei
  - Neue Übersetzungen für den Schulauswahl-Schritt in `strings.json`

### Fehlerbehebungen
- **Multi-School-Login**: Der bisherige Ansatz (v0.5.2) versuchte, die `institutionId` aus der Login-Response zu extrahieren, aber bei Multi-School-Accounts fehlt das `user`-Objekt komplett. Jetzt wird stattdessen eine explizite Schulauswahl durch den Nutzer ermöglicht.

**Hinweis**: v0.5.3 hatte bei einigen Nutzern Login-Probleme (Status 401). Bitte auf v0.6.0 updaten.

## 0.5.2 (2025-10-20)

### Funktionen
- **Mehrschul-Unterstützung** (Issue #2): Konten mit Kindern an mehreren Schulen werden zuverlässig verarbeitet
  - `institutionId` wird nach erfolgreichem Login automatisch extrahiert und gespeichert
  - Bei Re-Authentication kommt die gespeicherte `institutionId` erneut zum Einsatz
  - Der Config Flow aktiviert nach erfolgreichem Login automatisch Debug-Dumps

## 0.5.1 (2025-10-20)

### Fehlerbehebungen
- **Schedule-Sensor Tabellen-Sortierung**: Stunden werden nun chronologisch nach Stundennummer angezeigt
- **Nächtliche Validierung entfernt**: Workflow gestrichen, um Fehlermeldungen während der Beta-Phase zu vermeiden

## 0.5.0

- Pro Schüler eigene Kalender (Stundenplan & Arbeiten)
- Emoji-Hervorhebung für Stundenplanänderungen (optional)
- Konfigurierbare Wochenvorschau (1–3 Wochen)
- Manuelle Aktualisierung mit Cooldown
- Ereignisse für neue Hausaufgaben und Noten

## 0.4.0 und älter

- Initiale Versionen mit Hausaufgaben, Stundenplan, Prüfungen und Noten-Sensoren
- Diagnostik-Unterstützung
- TypedDicts und verbesserte Typisierung
