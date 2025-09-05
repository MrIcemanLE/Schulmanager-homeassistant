# Schulmanager Online Integration für Home Assistant

Eine Home Assistant Integration für Schulmanager Online, um Schulinformationen wie Stundenplan, Hausaufgaben, Arbeiten und Noten abzurufen.

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

- 📅 **Stundenplan**: Aktuelle und kommende Stunden
- 📝 **Hausaufgaben**: Anstehende Aufgaben mit Details
- 📊 **Arbeiten/Klausuren**: Geplante Prüfungen
- 🎯 **Noten**: Aktuelle Noten nach Fächern mit Gesamtdurchschnitt
- 🔄 **Automatische Updates**: Konfigurierbare Update-Intervalle
- 🌍 **Deutsche Lokalisierung**: Vollständig auf Deutsch verfügbar

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