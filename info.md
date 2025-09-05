# Schulmanager Online Integration

Diese Integration ermöglicht es, Daten aus Schulmanager Online in Home Assistant zu integrieren.

## Funktionen

### 📅 Stundenplan
- Zeigt aktuelle und kommende Unterrichtsstunden an
- Enthält Fach, Lehrer, Raum und Zeit

### 📝 Hausaufgaben  
- Listet anstehende Hausaufgaben auf
- Mit Fälligkeitsdatum und Details

### 📊 Arbeiten/Klausuren
- Übersicht über geplante Prüfungen
- Inkl. Datum, Fach und Beschreibung

### 🎯 Noten
- Aktuelle Noten nach Fächern
- Gesamtdurchschnitt des Schülers
- Deutsche Notenskala (1-6)

## Konfiguration

Die Integration kann vollständig über die Home Assistant UI konfiguriert werden:

1. **Zugangsdaten**: Schulmanager E-Mail und Passwort
2. **Features**: Einzelne Module aktivieren/deaktivieren
3. **Update-Intervall**: 1-6 Stunden automatisch
4. **Zeitbereich**: Vergangene/zukünftige Tage
5. **Cooldown**: Manuelle Aktualisierung 5-30 Minuten

## Entitäten

### Sensoren
- Stundenplan-Sensoren für jeden Schüler
- Hausaufgaben-Übersicht
- Arbeiten/Klausuren
- Noten nach Fächern
- Gesamtdurchschnitt

### To-Do Listen
- Hausaufgaben als erledigbare Aufgaben

### Kalender
- Stundenplan-Events
- Prüfungstermine

### Buttons
- Manuelle Aktualisierung

## Deutsche Lokalisierung

Die Integration ist vollständig auf Deutsch lokalisiert und speziell für deutsche Schulen entwickelt.