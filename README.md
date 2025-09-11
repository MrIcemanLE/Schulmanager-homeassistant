# Schulmanager Online Integration für Home Assistant

Eine Home Assistant Integration für Schulmanager Online, um Schulinformationen wie Stundenplan, Hausaufgaben, Arbeiten und Noten abzurufen.

> **⚠️ BETA-VERSION**  
> Diese Integration befindet sich noch in einem frühen Beta-Stadium. Es können Fehler auftreten und Funktionen können sich noch ändern. Verwenden Sie die Integration auf eigene Verantwortung und melden Sie Probleme über GitHub Issues.

## Installation über HACS

1. Öffne HACS in Home Assistant
2. Gehe zu "Integrationen"
3. Klicke auf die drei Punkte oben rechts und wähle "Benutzerdefinierte Repositories"
4. Füge diese Repository-URL hinzu: `https://github.com/MrIcemanLE/Schulmanager-homeassistant`
5. Wähle die Kategorie "Integration"
6. Klicke auf "Hinzufügen"
7. Suche nach "Schulmanager" und installiere die Integration
8. Starte Home Assistant neu

## Manuelle Installation

1. Kopiere den `schulmanager` Ordner in dein `custom_components` Verzeichnis
2. Starte Home Assistant neu
3. Füge die Integration über die UI hinzu

## Konfiguration

Nach der Installation kannst du die Integration über die Home Assistant UI konfigurieren:

1. Gehe zu Einstellungen > Geräte & Dienste
2. Klicke auf "Integration hinzufügen"
3. Suche nach "Schulmanager"
4. Gib deine Schulmanager-Zugangsdaten ein

## Features

- 📅 **Stundenplan**: Aktuelle und kommende Stunden mit Änderungserkennung
- 📝 **Hausaufgaben**: Anstehende Aufgaben mit Details und Todo-Integration
- 📊 **Arbeiten/Klausuren**: Geplante Arbeiten mit Countdown-Funktion
- 🎯 **Noten**: Aktuelle Noten nach Fächern mit Gesamtdurchschnitt
- ⏰ **Arbeitsalarm**: Sensor zeigt Tage bis zur nächsten Arbeit
- 🔄 **Automatische Updates**: Konfigurierbare Update-Intervalle
- 🌍 **Deutsche Lokalisierung**: Vollständig auf Deutsch verfügbar

## 📊 Dashboard Integration

Die Integration stellt verschiedene Sensoren und Kalender bereit, die auf dem Home Assistant Dashboard angezeigt werden können. 

**📋 Verfügbare Entitäten:**
- `sensor.SCHUELERNAME_stundenplan_heute` - Heutiger Stundenplan
- `sensor.SCHUELERNAME_stundenplan_morgen` - Stundenplan für morgen  
- `sensor.SCHUELERNAME_tage_bis_naechste_arbeit` - ⭐ **NEU**: Countdown bis zur nächsten Arbeit
- `calendar.SCHUELERNAME_arbeiten` - Kalender mit Arbeiten
- `todo.SCHUELERNAME_hausaufgaben` - Hausaufgaben als Todo-Liste

**🎨 Dashboard-Konfigurationen:**

Wir stellen drei vorgefertigte Dashboard-Konfigurationen bereit:

| Option | Schwierigkeit | Features |
|--------|--------------|----------|
| **Standard Markdown** | ⭐ Einfach | Sofort einsatzbereit, keine zusätzliche Installation |
| **Flex Table Card** | ⭐⭐ Mittel | Erweiterte Tabellenfunktionen, HACS erforderlich |
| **Komplettes Dashboard** | ⭐⭐⭐ Fortgeschritten | Vollständige Schul-Übersicht mit allen Features |

➡️ **[Zur detaillierten Dashboard-Anleitung (DASHBOARD.md)](DASHBOARD.md)**

## Konfigurationsoptionen

- **Automatisches Update-Intervall**: 1-6 Stunden
- **Funktionen aktivieren/deaktivieren**: Stundenplan, Hausaufgaben, Arbeiten, Noten
- **Zeitbereich**: Tage in Vergangenheit/Zukunft
- **Manuelle Aktualisierung**: Abkühlzeit 5-30 Minuten

## Entwicklung & Versioning

Diese Integration folgt [Semantic Versioning](https://semver.org/). Alle Änderungen werden in der [CHANGELOG.md](CHANGELOG.md) dokumentiert.

### Release-Prozess

Für Entwickler, die zur Integration beitragen möchten:

```bash
# Patch-Release (Bugfixes)
./scripts/release.sh patch "Fixed calendar sync issue"

# Minor-Release (Neue Features)
./scripts/release.sh minor "Added support for exam grades"

# Major-Release (Breaking changes)
./scripts/release.sh major "Restructured sensor entities"
```

### Version-History

Siehe [CHANGELOG.md](CHANGELOG.md) für eine detaillierte Liste aller Änderungen.

## Unterstützung

Bei Problemen oder Fragen erstelle bitte ein Issue auf GitHub.

## Lizenz

Dieses Projekt steht unter der MIT Lizenz.
