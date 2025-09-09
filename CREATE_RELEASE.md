# GitHub Release für HACS-Versionserkennung erstellen

## ⚠️ **WICHTIG: Ohne GitHub Release zeigt HACS nur Commit-Hashes statt Versionen!**

Der Git-Tag `v0.1.0` wurde bereits erstellt und gepusht. Jetzt müssen Sie ein GitHub Release erstellen:

## 📋 **Anleitung: GitHub Release erstellen**

### 1. GitHub Repository öffnen
Gehen Sie zu: https://github.com/MrIcemanLE/Schulmanager-homeassistant

### 2. Release erstellen
1. Klicken Sie auf **"Releases"** (rechte Seite)
2. Klicken Sie auf **"Create a new release"**
3. **Tag version**: `v0.1.0` (sollte bereits verfügbar sein)
4. **Release title**: `Release v0.1.0 (Beta)`

### 3. Release Notes einfügen
```markdown
🎉 **Erste Beta-Version der Schulmanager Online Integration**

## ✨ Features
- 📅 **Stundenplan**: Heute und morgen mit Änderungserkennung
- 📝 **Hausaufgaben**: Todo-Liste Integration  
- 📊 **Arbeiten**: Kalender mit Countdown-Sensor
- 🎯 **Noten**: Nach Fächern mit Gesamtdurchschnitt
- 🔄 **Automatische Updates**: Alle 1-6 Stunden

## 📊 Dashboard-Konfigurationen
- Standard Markdown Cards (sofort einsatzbereit)
- Flex Table Card (erweiterte Features)
- Komplettes Dashboard (alle Funktionen)

## ⚠️ Beta-Hinweis
Diese Version befindet sich noch im Beta-Stadium. Bitte melden Sie Probleme über GitHub Issues.

## 🔧 Installation
1. HACS → Integrationen → Benutzerdefinierte Repositories
2. Repository URL hinzufügen
3. Installation und Neustart von Home Assistant
4. Integration über UI konfigurieren

Ausführliche Anleitung: [README.md](https://github.com/MrIcemanLE/Schulmanager-homeassistant/blob/main/README.md)
Dashboard-Konfiguration: [DASHBOARD.md](https://github.com/MrIcemanLE/Schulmanager-homeassistant/blob/main/DASHBOARD.md)
```

### 4. Release veröffentlichen
1. ✅ **"Set as a pre-release"** (da Beta)
2. Klicken Sie auf **"Publish release"**

## 🎯 **Ergebnis nach dem Release:**

### ✅ **HACS wird dann anzeigen:**
- **Aktuelle Version**: "v0.1.0" (statt Commit-Hash)
- **Update-Benachrichtigung**: Bei neuen Releases
- **Versionsvergleich**: Alte vs. neue Version
- **Release-Notes**: In der HACS-Übersicht

### 📊 **HACS Update-Prozess:**
1. Benutzer sieht: `"Update verfügbar: v0.1.0 → v0.2.0"`
2. Klick auf Update zeigt Release-Notes
3. Installation der neuen Version

## 🚀 **Für zukünftige Updates:**

Mit dem Release-System können Sie das automatische Release-Skript verwenden:

```bash
# Nächstes Update (z.B. Bugfix)
./scripts/release.sh patch "Fixed calendar sync issue"
# Ergebnis: v0.1.1 wird automatisch erstellt und released

# Neue Features  
./scripts/release.sh minor "Added support for exam notifications"  
# Ergebnis: v0.2.0 wird automatisch erstellt und released
```

Das Skript erstellt automatisch:
- ✅ Git-Tag
- ✅ GitHub Release
- ✅ Changelog-Update
- ✅ Versionsnummer-Update

---

**⚡ Sobald Sie das Release erstellt haben, wird HACS korrekte Versionsnummern anzeigen!**