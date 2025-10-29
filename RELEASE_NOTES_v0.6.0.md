## Multi-School Support komplett überarbeitet

**Automatische Verwaltung aller Schulen** – Bei Accounts mit Kindern an mehreren Schulen werden jetzt automatisch alle Kinder eingebunden, ohne manuelle Schulauswahl.

**Behebt Login-Problem aus v0.5.3** – Der Schulauswahl-Dialog führte bei einigen Nutzern zu Anmeldefehlern (Status 401). Diese Probleme sind behoben.

**Neuer Diagnose-Sensor** – Jeder Schüler erhält einen "Schule"-Sensor, der die Schulzugehörigkeit anzeigt.

**Automatische Migration** – Bestehende Installationen werden beim Update automatisch migriert, keine Neueinrichtung nötig.

## Noten werden jetzt korrekt angezeigt

Noten mit Tendenz (z.B. 3+, 2-, 4+) werden nun sauber dargestellt. Die API liefert manchmal das Format "0~3+" – die Integration zeigt jetzt einfach "3+" an.

Die Durchschnittsberechnung behandelt 3+, 3 und 3- alle gleich als 3.0.

## Neues "plain" Attribut für Benachrichtigungen

Stundenplan-Sensoren (heute/morgen) haben jetzt ein zusätzliches `plain`-Attribut, perfekt für Benachrichtigungen und Sprachausgabe.

Verwendet die gleiche Emoji-Logik wie der Kalender: ❌ Entfall, 🔁 Vertretung, 🚪 Raumwechsel, 📝 Prüfung

**Beispiel:**
```
1. Std: Mathematik – Raum 204
2. Std: 🔁 Deutsch – Raum 101 (Vertretung)
3. Std: ❌ Englisch (Entfall)
```

---

**Wichtig:** Falls Sie v0.5.3 nutzen und Multi-School-Probleme hatten, sollten nach dem Update auf v0.6.0 alle Kinder automatisch sichtbar sein. Die Migration kann beim ersten Start ein paar Sekunden dauern.

Details siehe [CHANGELOG.md](https://github.com/MrIcemanLE/Schulmanager-homeassistant/blob/main/CHANGELOG.md)
