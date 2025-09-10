# 🔄 Migration zu Version 0.3.0

## ⚠️ Wichtiger Hinweis zur Gerätestruktur

**Version 0.3.0 führt eine neue Geräte-Hierarchie ein, die eine Neuinstallation der Integration erfordert.**

## 📋 Was ist neu?

### Service-basierte Gerätestruktur
- **Hauptgerät**: "Schulmanager Online" (Service-Gerät)
- **Untergeräte**: Einzelne Schüler als Untergeräte
- Bessere Organisation und Übersichtlichkeit im Home Assistant

### Technische Verbesserungen
- Integration von `"hub"` zu `"service"` Typ geändert
- Proper Device-Registry Hierarchie implementiert
- Compliance mit Home Assistant 2026.9 (suggested_area Deprecation)

## 🔧 Migrationschritte

### Schritt 1: Alte Integration entfernen
1. Gehen Sie zu **Einstellungen** → **Geräte & Services**
2. Suchen Sie "Schulmanager Online" 
3. Klicken Sie auf die Integration
4. Klicken Sie **LÖSCHEN**
5. Bestätigen Sie die Löschung

### Schritt 2: Home Assistant neu starten
**⚠️ Wichtig:** Starten Sie Home Assistant nach dem Löschen neu, um alle alten Entitäten zuverlässig zu entfernen.

```bash
# Über die UI: Entwicklertools → Neu starten
# Oder über die CLI:
ha core restart
```

### Schritt 3: Integration neu installieren
1. Gehen Sie zu **Einstellungen** → **Geräte & Services**
2. Klicken Sie **+ INTEGRATION HINZUFÜGEN**
3. Suchen Sie "Schulmanager Online"
4. Folgen Sie dem Konfigurationsassistenten

### Schritt 4: Dashboard aktualisieren (falls nötig)
- Die Entitätsnamen bleiben gleich
- Ihre Dashboard-Konfigurationen funktionieren weiterhin
- Die neue Gerätestruktur ist im Geräte-Dashboard sichtbar

## 🔍 Neue Gerätestruktur

### Vorher (< 0.3.0):
```
📱 Schueler A (Standalone-Gerät)
📱 Schueler B (Standalone-Gerät)
```

### Nachher (>= 0.3.0):
```
🏢 Schulmanager Online (Service-Gerät)
├── 👤 Schueler A (Schüler-Gerät)
├── 👤 Schueler B (Schüler-Gerät)
└── 🔄 Refresh Button
```

## ✅ Was bleibt gleich?

- **Entitätsnamen**: Keine Änderung
- **Dashboard-Konfigurationen**: Funktionieren weiterhin
- **Automatisierungen**: Keine Anpassung nötig
- **Funktionalität**: Alle Features bleiben erhalten

## 🚨 Fehlerbehebung

### Problem: Alte Entitäten sind noch sichtbar
**Lösung:** Home Assistant erneut neu starten

### Problem: Integration kann nicht neu hinzugefügt werden
**Lösung:** 
1. Cache leeren (Strg+F5 im Browser)
2. Home Assistant neu starten
3. HACS neu starten falls nötig

### Problem: Geräte werden nicht korrekt angezeigt
**Lösung:**
1. Prüfen Sie **Einstellungen** → **Geräte & Services** → **Geräte**
2. Suchen Sie nach "Schulmanager Online"
3. Die neue Hierarchie sollte sichtbar sein

## 📞 Support

Bei Problemen während der Migration:
1. [GitHub Issues](https://github.com/MrIcemanLE/Schulmanager-homeassistant/issues)
2. Fügen Sie folgende Informationen hinzu:
   - Home Assistant Version
   - Ihre vorherige Schulmanager-Version
   - Screenshots der Gerätestruktur
   - Log-Dateien bei Fehlern

---

**Die Migration ist notwendig, um die neuen Device-Hierarchie-Features zu nutzen und future-proof zu bleiben! 🚀**