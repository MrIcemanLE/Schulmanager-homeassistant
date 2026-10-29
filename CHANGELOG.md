# Schulmanager Integration – Changelog

## 0.12.2 (2026-10-29)

**Kurz gesagt:** Doppelt eingetragene Hausaufgaben lassen sich wieder abhaken, und Stundenplanänderungen erscheinen in der Reihenfolge der Schulstunden.

### 🐛 Bugfixes

- **Doppelte Hausaufgaben (Danke an @micbuh, PR #18):** Wurde eine Aufgabe zweimal mit demselben Text eingetragen, ließ sich keine der beiden abhaken. Jetzt bekommt jeder Eintrag eine eigene Kennung. Bereits gesetzte Häkchen bleiben erhalten. Nur bei Hausaufgaben, deren Text am Anfang oder Ende ein Leerzeichen hat, muss das Häkchen nach dem Update einmal neu gesetzt werden.
- **Stundenplanänderungen nach Stunde sortiert (Danke an @KoenigMjr, PR #17):** Die Änderungen für heute und morgen kamen bisher in der Reihenfolge, in der Schulmanager sie liefert, etwa 5., 2., 1. Stunde. Jetzt sind sie nach Stunde sortiert, auch in der Zusammenfassung.

---

## 0.12.1 (2026-10-28)

**Kurz gesagt:** Bei Kindern an mehreren Schulen fehlt kein Kind mehr stillschweigend. Kann sich die Integration bei einer Schule nicht anmelden, zeigt Home Assistant unter Einstellungen → Reparaturen einen Hinweis mit der Schule und dem Grund an, etwa eine aktive Zwei-Faktor-Anmeldung.

### 🐛 Bugfixes

- **Kinder an mehreren Schulen (Danke an @apfelbasti, Issue #16)**
  - Bei Schulmanager hat jede Schule ein eigenes Konto, auch bei gleicher E-Mail-Adresse. Passwort und Zwei-Faktor-Anmeldung gelten pro Konto.
  - Ist für das Konto einer Schule die Zwei-Faktor-Anmeldung aktiv, erscheint jetzt ein Reparaturhinweis. Die Integration unterstützt die Zwei-Faktor-Anmeldung noch nicht. Schalte sie für das Konto dieser Schule aus, damit die Kinder erscheinen.
  - Lehnt eine Schule das Passwort ab, erscheint ebenfalls ein Reparaturhinweis.
  - Die Anmeldung bei mehreren Schulen läuft jetzt genau wie in der Schulmanager-Weboberfläche. Die Integration macht keine überflüssigen Fehlversuche mehr.
- **Klarere Fehler bei der Einrichtung:** Ein falsches Passwort meldet jetzt „Anmeldung fehlgeschlagen“ statt „Verbindung fehlgeschlagen“. Für Konten mit aktiver Zwei-Faktor-Anmeldung gibt es eine eigene Meldung.

---

## 0.12.0 (2026-10-14)

**Kurz gesagt:** Der Wochenplan für die Stundenplan Card zeigt jetzt Fach, Lehrkraft und Raum untereinander und markiert Änderungen genau dort, wo sie passieren – mit dem bisherigen Wert in Klammern. Die Markierungen sind dieselben Emojis wie im Kalender.

### ✨ Verbesserungen

- **Ausführlicherer Wochenplan (Sensor „Wochenplan JSON“, Danke an @KoenigMjr, PR #15)**
  - Jede Zelle enthält mehrzeilig Fach, Lehrkraft und Raum statt nur des Fachkürzels
  - Änderungen werden an der betroffenen Zeile markiert, der bisherige Wert steht in Klammern: `rei (ber) 🔁` bei Vertretung/Lehrkraftwechsel, `U04 (Ch) 🚪` bei Raumwechsel, `Ma (D) ⚠️` bei geändertem Fach, `E ❌` bei Entfall (mit Lehrkraft und Raum der entfallenen Stunde), `M 📝` bei Prüfung
  - Sonderstunden und sonstige Änderungen ohne erkennbaren Unterschied erhalten weiterhin ein `⚠️` am Fach; fehlt die Angabe zu Lehrkraft oder Raum, steht `🔁` bzw. `🚪` direkt am Fach
  - Mehrere Stunden in derselben Zelle werden durch eine Leerzeile getrennt, Entfälle stehen zuerst

### ⚠️ Geändertes Format

- Die Markierungen im Wochenplan ändern sich von `✗` / `↔` / `⚠` zu `❌` / `🔁` / `🚪` / `📝` / `⚠️`, mehrere Stunden pro Zelle werden nicht mehr mit ` → ` verbunden. Wer eigene Vorlagen oder Styles auf die alten Zeichen gebaut hat, muss sie anpassen.
- Die Stundenplan Card stellt die mehrzeiligen Zellen in der aktuellen Version korrekt dar. Entity-ID und Attribut `plan` bleiben unverändert.

---

## 0.11.1 (2026-10-14)

**Kurz gesagt:** Namen und Kontaktdaten werden in Logs und Diagnose-Dateien automatisch durch Platzhalter ersetzt – Fehlerberichte lassen sich so deutlich unbedenklicher teilen. Debug-Dateien entstehen nur noch bei aktivierter Debug-Protokollierung. Außerdem behoben: Änderungen in den Optionen werden wieder zuverlässig übernommen, und Noten im Punktesystem tragen die Einheit „Punkte“.

### 🔒 Datenschutz

- **Namen und Kontaktdaten werden aus Logs und Diagnose entfernt**
  - Namen der Kinder und Eltern, E-Mail-Adresse, Schüler-IDs sowie Name und Adresse der Schule werden in Logs, Debug-Dateien und im Diagnose-Download automatisch durch Platzhalter wie `<Kind 1>` oder `<Schule>` ersetzt
  - Die Zuordnung bleibt erhalten (Kind 1 bleibt Kind 1), damit Fehlermeldungen weiterhin nachvollziehbar sind
  - Der Diagnose-Download lässt zusätzlich Freitexte weg (Elternbriefe, Hausaufgaben, Nachrichten)
  - In Home Assistant selbst ändert sich nichts – Geräte und Sensoren zeigen weiterhin die echten Namen

- **Debug-Dateien nur noch bei aktivierter Debug-Protokollierung**
  - Die Option „Debug-Dumps schreiben“ entfällt; sie war bisher standardmäßig eingeschaltet, und beim Einrichten wurden immer Debug-Dateien geschrieben
  - Debug-Dateien entstehen jetzt nur, solange unter *Einstellungen → Geräte & Dienste → Schulmanager Online → ⋮ → Debug-Protokoll aktivieren* eingeschaltet ist
  - Ältere Debug-Dateien bleiben bestehen und können mit dem Dienst „Debug-Ordner leeren“ gelöscht werden; dieser Dienst steht jetzt nur Administratoren zur Verfügung

### ✨ Verbesserungen

- **Noten im Punktesystem mit Einheit**
  - Fach- und Gesamtdurchschnitte im Punktesystem der Oberstufe (0–15) haben jetzt die Einheit „Punkte“, klassische Noten bleiben ohne Einheit
  - Neues Attribut `grading_system` mit der Bezeichnung aus Schulmanager („Noten 1 bis 6“ bzw. „Notenpunkte 0 bis 15“)

### 🐛 Bugfixes

- **Änderungen in den Optionen wurden teilweise nicht übernommen**
  - Problem: Wurde eine vorher ausgeschaltete Funktion (z. B. Hausaufgaben) eingeschaltet, schlug das Neuladen der Integration fehl; ausgeschaltete Funktionen blieben bis zum Neustart sichtbar
  - Lösung: Optionen werden jetzt zuverlässig übernommen, ohne Neustart

- **Doppelter Punkt bei der Stundennummer („5.. Std“, aus Issue #10)**
  - Problem: Bei Schulen, die die Stundennummer als „5.“ liefern, stand im Stundenplan „5.. Std“; auch die Zuordnung der Uhrzeit im Kalender konnte fehlschlagen
  - Lösung: Die Stundennummer wird überall einheitlich ohne Punkt verwendet

---

## 0.11.0 (2026-10-14)

**Kurz gesagt:** Neue Sensoren zeigen ungelesene Elternbriefe und Messenger-Nachrichten an, ohne etwas als gelesen zu markieren. Geänderte Stunden sind im Wochenplan jetzt mit ⚠ markiert, und Home Assistant wird beim Abruf nicht mehr ausgebremst.

### ✨ Neues

- **Ungelesene Elternbriefe (PR #13, danke an @sbiela)**
  - Neuer Sensor „Ungelesene Elternbriefe“ am Gerät „Schulmanager Online“: Anzahl ungelesener Briefe, dazu Titel, Versanddatum, Rückmeldefrist, betroffene Kinder, Textauszug und Anzahl der Anhänge
  - Briefe werden dabei nicht geöffnet und bleiben in App und Portal ungelesen
  - In den Optionen abschaltbar („Ungelesene Elternbriefe abrufen“)

- **Ungelesene Messenger-Nachrichten (PR #13, danke an @sbiela)**
  - Neuer Sensor „Ungelesene Nachrichten“ mit Anzahl und den betroffenen Unterhaltungen (Betreff, Absender, Empfänger, Anzahl, Zeitpunkt)
  - Nachrichtentexte werden bewusst nicht geladen, damit keine Lesebestätigungen ausgelöst werden
  - In den Optionen abschaltbar („Ungelesene Nachrichten abrufen“)

- **Hinweise zu beiden Sensoren**
  - Hat die Schule das Elternbrief- oder Messenger-Modul nicht freigeschaltet, wird der jeweilige Sensor gar nicht erst angelegt
  - Briefinhalte, Namen und Unterhaltungen werden nicht in der Verlaufsdatenbank von Home Assistant gespeichert, nur die Anzahl
  - Die Werte werden wie alle anderen Daten stündlich aktualisiert (oder sofort über den Button „Jetzt aktualisieren“)

- **Diagnose-Sensor „Schule“ zeigt den echten Schulnamen**
  - Bisher stand dort nur ein Platzhalter wie „School 12345“

- **Neuer Diagnose-Sensor „Schul-ID“ pro Schüler:in**

- **Eigenes Icon für die Integration**
  - Neu gestaltetes Icon (Doktorhut über aufgeschlagenem Buch), das ab Home Assistant 2026.3 direkt in der Integrationsübersicht angezeigt wird

### 🐛 Bugfixes

- **Geänderte Stunden im Wochenplan nicht markiert (Issue #12)**
  - Problem: Im Sensor „Wochenplan JSON“ (für die Stundenplan Card) waren nur Ausfälle (`✗`) und Vertretungen (`↔`) erkennbar – geänderter Unterricht, Raumwechsel und Sonderstunden sahen aus wie normale Stunden
  - Lösung: Diese Stunden erscheinen jetzt als `Fach ⚠`

- **Originaldaten fehlten im Sensor „Stundenplan Änderungen“ (Issue #12)**
  - Problem: Ursprüngliches Fach, Lehrkraft und Raum wurden nur bei Ausfällen angezeigt, bei allen anderen Änderungen blieben sie leer
  - Lösung: Die Originaldaten werden jetzt für alle Änderungsarten befüllt, genau wie im Sensor „Stundenplan heute“

- **Geänderter Unterricht ohne Hervorhebung**
  - Im Stundenplan-Kalender und im Text des Sensors „Stundenplan heute“ fehlte bei geändertem Unterricht das 🔁

- **Home Assistant hing bei jeder Aktualisierung kurz**
  - Problem: Die Anmeldung bei Schulmanager blockierte Home Assistant bei jedem Abruf für etwa eine halbe Sekunde
  - Lösung: Die Anmeldung läuft jetzt im Hintergrund, ohne Home Assistant auszubremsen

- **Kompatibilität mit kommenden Home-Assistant-Versionen**
  - Eine Warnung im Log zu einer veralteten Geräteverknüpfung ist behoben (wäre ab Home Assistant 2027.8 ein Fehler geworden)

---

## 0.10.2 (2026-09-20)

### 🐛 Bugfixes

- **Ganztägige Schultermine zeigten 02:00 Uhr statt "ganztägig" (Folgefehler von v0.10.1)**
  - Problem: Nach dem Zeitzonen-Fix in v0.10.1 wurden ganztägige Termine (z.B. bewegliche Ferientage, mehrtägige Events) im Kalender mit einer Uhrzeit wie "02:00" statt als ganztägiger Eintrag angezeigt
  - Lösung: Ganztägige Termine werden jetzt korrekt erkannt und wieder ohne Uhrzeit dargestellt – normale Termine mit Uhrzeit sind vom v0.10.1-Fix weiterhin unberührt

- **Kein Gesamtdurchschnitt für Schüler:innen im Punktesystem der gymnasialen Oberstufe**
  - Problem: Schüler:innen, die ausschließlich im 0–15-Punktesystem benotet werden, hatten nie einen Gesamtdurchschnitt – das Feld blieb leer
  - Lösung: Der Gesamtdurchschnitt wird jetzt auch für das Punktesystem korrekt berechnet

---

## 0.10.1 (2026-09-20)

### 🐛 Bugfixes

- **Schulweite Termine bis zu 2 Stunden zu früh im Kalender (Issue #11)**
  - Problem: Bei manchen Schulmanager-Konten wurden Uhrzeiten von schulweiten Terminen (z.B. Elternabende, Veranstaltungen) im Kalender bis zu 2 Stunden zu früh angezeigt
  - Lösung: Die Zeitzonen-Behandlung für diese Termine wurde robuster gemacht – betrifft nur Termine, keine regulären Unterrichtsstunden

---

## 0.10.0 (2026-09-20)

### ✨ Neues

- **Unterstützung für das Punktesystem der gymnasialen Oberstufe**
  - Endnoten werden jetzt auch für Kurse mit dem 0–15-Punkte-System (Sek II) korrekt dargestellt, nicht nur für die klassische 1–6-Notenskala
  - Funktioniert automatisch für alle entsprechend eingestellten Kurse – keine Konfiguration nötig

### 🐛 Bugfixes

- **Noten teilweise für falsches Schuljahr abgerufen**
  - Problem: Ein interner, veralteter Kennwert führte in seltenen Fällen dazu, dass Noten aus einem vergangenen statt dem aktuellen Schuljahr geladen wurden
  - Lösung: Das aktuelle Schuljahr wird jetzt automatisch korrekt ermittelt

- **Updates an bestehenden Installationen liefen teilweise nicht durch**
  - Problem: Ein interner Fehler verhinderte, dass fällige Aktualisierungsschritte bei bestehenden Installationen ausgeführt wurden
  - Lösung: Wird beim nächsten Update automatisch nachgeholt, keine Aktion nötig

- **Sensoren/Kalender konnten bei mehreren Zugängen zum selben Schüler verschwinden**
  - Problem: War derselbe Schüler über mehr als einen Zugang eingebunden, konnten Sensoren und Kalender des zusätzlichen Zugangs kommentarlos verschwinden
  - Lösung: Behoben – bestehende Dashboards und Automatisierungen bleiben unverändert erhalten

---

## 0.9.1 (2026-05-13)

### ✨ Neues

- **Sensor „Wochenplan JSON" – Kompatibel mit der [Stundenplan Card](https://github.com/fabel-smith/stundenplan-card) (Issue #7)**
  - Neuer Sensor pro Schüler: `sensor.<schüler>_wochenplan_json`
  - Liefert den aktuellen Wochenplan als JSON – direkt nutzbar mit der beliebten [Stundenplan Card](https://github.com/fabel-smith/stundenplan-card) von fabel-smith
  - Einrichtung in der Stundenplan Card: Datenquelle → „Beliebiger Sensor (JSON)" → diesen Sensor auswählen
  - Ausfälle und Vertretungen werden automatisch markiert (Ausfall: `Fach ✗`, Vertretung: `Fach ↔`)
  - Am Wochenende wird automatisch der Plan für die nächste Woche angezeigt
  - Sensor-Zustand zeigt die aktuelle Kalenderwoche und das Montag-Datum (z.B. `KW 19 (2026-05-04)`)
  - Danke an @8R3N38 für die Idee und den Tipp zur Stundenplan Card! 🙏

### 🐛 Bugfixes

- **Erledigte Hausaufgaben nach Neustart zurückgesetzt**
  - Problem: Hausaufgaben, die als „erledigt" markiert waren, wurden nach jedem Neustart von Home Assistant wieder auf „offen" gesetzt
  - Ursache: Der Status war nur im Arbeitsspeicher gespeichert und ging beim Neustart verloren
  - Lösung: Der Erledigt-Status wird jetzt dauerhaft im HA-Storage gespeichert und überlebt Neustarts, Integrations-Updates und HA-Updates

---

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
