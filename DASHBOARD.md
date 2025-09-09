# 📊 Schulmanager Dashboard Konfiguration

Dieses Dokument zeigt verschiedene Möglichkeiten, wie Sie die Schulmanager-Daten auf Ihrem Home Assistant Dashboard anzeigen können.

## 🎯 Übersicht der Optionen

| Option | Schwierigkeit | Installation | Features |
|--------|--------------|-------------|----------|
| **Standard Markdown** | Einfach ⭐ | Keine | Sofort einsatzbereit |
| **Flex Table Card** | Mittel ⭐⭐ | HACS erforderlich | Erweiterte Anpassungen |
| **Komplettes Dashboard** | Fortgeschritten ⭐⭐⭐ | Keine | Vollständige Schul-Übersicht |

## 📋 Verfügbare Entitäten

Nach der Installation der Integration stehen folgende Entitäten zur Verfügung:

### Stundenplan
- `sensor.SCHUELERNAME_stundenplan_heute` - Heutiger Stundenplan
- `sensor.SCHUELERNAME_stundenplan_morgen` - Stundenplan für morgen
- `sensor.SCHUELERNAME_stundenplan_changes` - Stundenplanänderungen

### Arbeiten & Noten
- `sensor.SCHUELERNAME_tage_bis_naechste_arbeit` - Tage bis zur nächsten Arbeit
- `calendar.SCHUELERNAME_arbeiten` - Kalender mit Arbeiten
- `sensor.SCHUELERNAME_noten_gesamt` - Gesamtdurchschnitt
- `sensor.SCHUELERNAME_noten_FACH` - Noten pro Fach

### Aufgaben
- `todo.SCHUELERNAME_hausaufgaben` - Hausaufgaben-Liste

> **💡 Hinweis:** Ersetzen Sie `SCHUELERNAME` durch den tatsächlichen Namen (kleingeschrieben, Leerzeichen durch Unterstriche ersetzt)

---

## 🌟 Option 1: Standard Markdown Card (Empfohlen)

**✅ Vorteile:** 
- Keine zusätzliche Installation erforderlich
- Sofort einsatzbereit
- Responsive Design
- Nutzt vorgefertigte HTML-Tabellen

**📋 YAML Konfiguration:**

\`\`\`yaml
# =================================================
# SCHULMANAGER STUNDENPLAN - STANDARD KARTEN
# =================================================

- type: vertical-stack
  title: "Schulmanager Stundenplan"
  cards:
    # Heutiger Stundenplan
    - type: markdown
      title: "📅 Stundenplan Heute"
      content: |
        **Status:** {{ states('sensor.SCHUELERNAME_stundenplan_heute') }}
        
        {{ state_attr('sensor.SCHUELERNAME_stundenplan_heute', 'html') }}
      card_mod:
        style: |
          ha-card {
            --ha-card-border-radius: 12px;
            border: 2px solid var(--primary-color);
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
          }
          table {
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
          }
          th, td {
            border: 1px solid var(--divider-color);
            padding: 8px;
            text-align: left;
          }
          th {
            background-color: var(--primary-color);
            color: white;
            font-weight: bold;
          }
          tr:nth-child(even) {
            background-color: var(--card-background-color);
          }
          tr:hover {
            background-color: var(--secondary-background-color);
          }
    
    # Morgiger Stundenplan
    - type: markdown
      title: "🔮 Stundenplan Morgen"
      content: |
        **Status:** {{ states('sensor.SCHUELERNAME_stundenplan_morgen') }}
        
        {{ state_attr('sensor.SCHUELERNAME_stundenplan_morgen', 'html') }}
      card_mod:
        style: |
          ha-card {
            --ha-card-border-radius: 12px;
            border: 2px solid var(--accent-color);
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
          }
          table {
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
          }
          th, td {
            border: 1px solid var(--divider-color);
            padding: 8px;
            text-align: left;
          }
          th {
            background-color: var(--accent-color);
            color: white;
            font-weight: bold;
          }
          tr:nth-child(even) {
            background-color: var(--card-background-color);
          }
          tr:hover {
            background-color: var(--secondary-background-color);
          }

    # Schnellübersicht
    - type: horizontal-stack
      cards:
        - type: entity
          entity: sensor.SCHUELERNAME_tage_bis_naechste_arbeit
          name: "Nächste Arbeit"
          icon: mdi:calendar-clock
        - type: entity
          entity: sensor.SCHUELERNAME_stundenplan_changes
          name: "Planänderungen"
          icon: mdi:calendar-alert

# WICHTIG: Ersetzen Sie "SCHUELERNAME" durch den echten Schülernamen
# Beispiel: Bei "Max Mustermann" verwenden Sie "max_mustermann"
\`\`\`

---

## 🚀 Option 2: Flex Table Card (Erweitert)

**✅ Vorteile:**
- Hochgradig anpassbar
- Professionelle Tabellendarstellung
- Erweiterte Sortier- und Filterfunktionen

**📦 Installation:**
1. HACS → Frontend → "Flex Table Card" suchen und installieren
2. Home Assistant neu starten

**📋 YAML Konfiguration:**

\`\`\`yaml
# =======================================================
# SCHULMANAGER STUNDENPLAN - FLEX TABLE CARD
# =======================================================
# Voraussetzung: Flex Table Card aus HACS

- type: vertical-stack
  title: "📚 Schulmanager Dashboard"
  cards:
    # Status-Übersicht
    - type: horizontal-stack
      cards:
        - type: entity
          entity: sensor.SCHUELERNAME_stundenplan_heute
          name: "Heute"
          icon: mdi:calendar-today
        - type: entity
          entity: sensor.SCHUELERNAME_stundenplan_morgen
          name: "Morgen"
          icon: mdi:calendar-tomorrow
        - type: entity
          entity: sensor.SCHUELERNAME_tage_bis_naechste_arbeit
          name: "Tage bis Arbeit"
          icon: mdi:calendar-clock

    # Heutiger Stundenplan - Flex Table
    - type: custom:flex-table-card
      title: "📅 Stundenplan Heute"
      entities:
        include: sensor.SCHUELERNAME_stundenplan_heute
      columns:
        - name: "Stunde"
          data: raw.lessons
          modify: x.hour + ". Std"
          align: center
        - name: "Fach"
          data: raw.lessons
          modify: x.subject || "---"
          align: center
        - name: "Raum"
          data: raw.lessons
          modify: x.room || "---"
          align: center
        - name: "Lehrer"
          data: raw.lessons
          modify: x.teacher || "---"
          align: center
        - name: "Info"
          data: raw.lessons
          modify: |
            if(x.type !== 'regularLesson') 
              return '⚠️ ' + x.type;
            return '✓';
          align: center
      css:
        table+: "border-collapse: collapse; width: 100%;"
        tbody tr+: "border-bottom: 1px solid var(--divider-color);"
        tbody tr td+: "padding: 8px; border-right: 1px solid var(--divider-color);"
        thead th+: "background-color: var(--primary-color); color: white; padding: 10px; border: 1px solid var(--divider-color);"
      strict: false

    # Morgiger Stundenplan - Flex Table
    - type: custom:flex-table-card
      title: "🔮 Stundenplan Morgen"
      entities:
        include: sensor.SCHUELERNAME_stundenplan_morgen
      columns:
        - name: "Stunde"
          data: raw.lessons
          modify: x.hour + ". Std"
          align: center
        - name: "Fach"
          data: raw.lessons
          modify: x.subject || "---"
          align: center
        - name: "Raum"
          data: raw.lessons
          modify: x.room || "---"
          align: center
        - name: "Lehrer"
          data: raw.lessons
          modify: x.teacher || "---"
          align: center
        - name: "Info"
          data: raw.lessons
          modify: |
            if(x.type !== 'regularLesson') 
              return '⚠️ ' + x.type;
            return '✓';
          align: center
      css:
        table+: "border-collapse: collapse; width: 100%;"
        tbody tr+: "border-bottom: 1px solid var(--divider-color);"
        tbody tr td+: "padding: 8px; border-right: 1px solid var(--divider-color);"
        thead th+: "background-color: var(--accent-color); color: white; padding: 10px; border: 1px solid var(--divider-color);"
      strict: false

    # Stundenplanänderungen-Alarm
    - type: conditional
      conditions:
        - entity: sensor.SCHUELERNAME_stundenplan_changes
          state_not: "0"
      card:
        type: markdown
        title: "⚠️ Stundenplanänderungen"
        content: |
          **{{ states('sensor.SCHUELERNAME_stundenplan_changes') }}** Änderungen erkannt
          
          {% for change in state_attr('sensor.SCHUELERNAME_stundenplan_changes', 'llm_structured_data').detailed_changes[:3] %}
          - **{{ change.day | title }}** {{ change.hour }}. Stunde: {{ change.subject }} ({{ change.change_type }})
          {% endfor %}
        card_mod:
          style: |
            ha-card {
              border: 2px solid orange;
              background-color: rgba(255, 165, 0, 0.1);
            }
\`\`\`

---

## 🌟 Option 3: Komplettes Dashboard

**✅ Vorteile:**
- Vollständige Schul-Management-Oberfläche
- Stundenplan, Prüfungen, Noten und Aufgaben
- Mobile-optimiert
- Bedingte Warnungen für Planänderungen

**📋 YAML Konfiguration:**

\`\`\`yaml
# =======================================================
# KOMPLETTES SCHULMANAGER DASHBOARD
# =======================================================
# Features: Stundenplan, Prüfungen, Noten, Änderungen, Aufgaben

view:
  title: Schulmanager
  path: schulmanager
  icon: mdi:school
  badges: []
  cards:
    # Header mit Schnellstatistiken
    - type: horizontal-stack
      cards:
        - type: entity
          entity: sensor.SCHUELERNAME_stundenplan_heute
          name: "Status Heute"
          icon: mdi:calendar-today
        - type: entity
          entity: sensor.SCHUELERNAME_tage_bis_naechste_arbeit
          name: "Tage bis Arbeit"
          icon: mdi:calendar-clock
        - type: entity
          entity: sensor.SCHUELERNAME_noten_gesamt
          name: "Gesamtnote"
          icon: mdi:school
        - type: entity
          entity: sensor.SCHUELERNAME_stundenplan_changes
          name: "Änderungen"
          icon: mdi:calendar-alert

    # Hauptstundenplan-Bereich
    - type: vertical-stack
      cards:
        # Heutiger Stundenplan
        - type: markdown
          title: "📅 Heute ({{ now().strftime('%d.%m.%Y') }})"
          content: |
            {% set entity = 'sensor.SCHUELERNAME_stundenplan_heute' %}
            {% set status = states(entity) %}
            {% set lessons = state_attr(entity, 'raw').lessons if state_attr(entity, 'raw') else [] %}
            
            **Status: {{ status }}** | **{{ lessons|length }} Stunden**
            
            {% if status in ['Schulfrei', 'Wochenende'] %}
            🎉 **{{ status }}** - Keine Schule heute!
            {% else %}
            <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse; margin: 10px 0;">
            <thead>
            <tr style="background-color: var(--primary-color); color: white;">
            <th style="padding: 8px; border: 1px solid var(--divider-color);">Stunde</th>
            <th style="padding: 8px; border: 1px solid var(--divider-color);">Fach</th>
            <th style="padding: 8px; border: 1px solid var(--divider-color);">Raum</th>
            <th style="padding: 8px; border: 1px solid var(--divider-color);">Lehrer</th>
            <th style="padding: 8px; border: 1px solid var(--divider-color);">Status</th>
            </tr>
            </thead>
            <tbody>
            {% for lesson in lessons %}
            <tr style="border-bottom: 1px solid var(--divider-color);">
            <td style="padding: 6px; text-align: center;">{{ lesson.hour }}.</td>
            <td style="padding: 6px; font-weight: bold;">{{ lesson.subject or '---' }}</td>
            <td style="padding: 6px;">{{ lesson.room or '---' }}</td>
            <td style="padding: 6px;">{{ lesson.teacher or '---' }}</td>
            <td style="padding: 6px; text-align: center;">
            {% if lesson.type != 'regularLesson' %}⚠️{% else %}✓{% endif %}
            </td>
            </tr>
            {% endfor %}
            </tbody>
            </table>
            </div>
            {% endif %}

        # Morgiger Stundenplan
        - type: markdown
          title: "🔮 Morgen ({{ (now() + timedelta(days=1)).strftime('%d.%m.%Y') }})"
          content: |
            {% set entity = 'sensor.SCHUELERNAME_stundenplan_morgen' %}
            {% set status = states(entity) %}
            {% set lessons = state_attr(entity, 'raw').lessons if state_attr(entity, 'raw') else [] %}
            
            **Status: {{ status }}** | **{{ lessons|length }} Stunden**
            
            {% if status in ['Schulfrei', 'Wochenende'] %}
            🎉 **{{ status }}** - Keine Schule morgen!
            {% else %}
            <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse; margin: 10px 0;">
            <thead>
            <tr style="background-color: var(--accent-color); color: white;">
            <th style="padding: 8px; border: 1px solid var(--divider-color);">Stunde</th>
            <th style="padding: 8px; border: 1px solid var(--divider-color);">Fach</th>
            <th style="padding: 8px; border: 1px solid var(--divider-color);">Raum</th>
            <th style="padding: 8px; border: 1px solid var(--divider-color);">Lehrer</th>
            <th style="padding: 8px; border: 1px solid var(--divider-color);">Status</th>
            </tr>
            </thead>
            <tbody>
            {% for lesson in lessons %}
            <tr style="border-bottom: 1px solid var(--divider-color);">
            <td style="padding: 6px; text-align: center;">{{ lesson.hour }}.</td>
            <td style="padding: 6px; font-weight: bold;">{{ lesson.subject or '---' }}</td>
            <td style="padding: 6px;">{{ lesson.room or '---' }}</td>
            <td style="padding: 6px;">{{ lesson.teacher or '---' }}</td>
            <td style="padding: 6px; text-align: center;">
            {% if lesson.type != 'regularLesson' %}⚠️{% else %}✓{% endif %}
            </td>
            </tr>
            {% endfor %}
            </tbody>
            </table>
            </div>
            {% endif %}

    # Stundenplanänderungen-Alarm
    - type: conditional
      conditions:
        - entity: sensor.SCHUELERNAME_stundenplan_changes
          state_not: "0"
      card:
        type: markdown
        title: "⚠️ Stundenplanänderungen"
        content: |
          {% set changes = state_attr('sensor.SCHUELERNAME_stundenplan_changes', 'llm_structured_data') %}
          {% if changes and changes.has_changes %}
          **{{ changes.total_changes }} Änderungen erkannt:**
          
          {% for change in changes.detailed_changes[:5] %}
          - **{{ change.day | title }}**, {{ change.hour }}. Stunde: 
            {{ change.subject }} {% if change.type %}({{ change.type }}){% endif %}
            {% if change.room %}in {{ change.room }}{% endif %}
          {% endfor %}
          
          {{ changes.natural_language_summary }}
          {% else %}
          Keine Stundenplanänderungen
          {% endif %}
        card_mod:
          style: |
            ha-card {
              border-left: 4px solid orange;
              background-color: rgba(255, 165, 0, 0.05);
            }

    # Kommende Arbeiten
    - type: entities
      title: "📝 Kommende Arbeiten"
      entities:
        - entity: sensor.SCHUELERNAME_tage_bis_naechste_arbeit
          secondary_info: |
            {% set next_exam = state_attr('sensor.SCHUELERNAME_tage_bis_naechste_arbeit', 'next_exam') %}
            {% if next_exam %}
            {{ next_exam.subject }} ({{ next_exam.type }}) - {{ next_exam.date }}
            {% else %}
            Keine anstehenden Arbeiten
            {% endif %}
        - type: divider
        - entity: calendar.SCHUELERNAME_arbeiten
          name: "Prüfungskalender"

    # Aufgaben (falls verfügbar)
    - type: todo-list
      entity: todo.SCHUELERNAME_hausaufgaben
      title: "📚 Hausaufgaben"
\`\`\`

---

## 🛠️ Einrichtungsanleitung

### 1. Entitätsnamen ermitteln
1. Gehen Sie zu **Entwicklertools** → **Zustände**
2. Suchen Sie nach Entitäten, die mit `sensor.` und Ihrem Schülernamen beginnen
3. Notieren Sie sich die exakten Namen

### 2. YAML einfügen
1. Gehen Sie zu Ihrem Dashboard
2. Klicken Sie auf **Bearbeiten** → **Raw-Konfigurationseditor**
3. Fügen Sie die gewünschte YAML-Konfiguration ein
4. Ersetzen Sie `SCHUELERNAME` durch die tatsächlichen Entitätsnamen

### 3. Mehrere Schüler
Für mehrere Schüler duplizieren Sie die Abschnitte und ändern die Namen entsprechend:

\`\`\`yaml
# Schüler 1
- type: markdown
  title: "📅 Max - Stundenplan Heute"
  content: |
    {{ state_attr('sensor.max_mustermann_stundenplan_heute', 'html') }}

# Schüler 2  
- type: markdown
  title: "📅 Anna - Stundenplan Heute"
  content: |
    {{ state_attr('sensor.anna_mustermann_stundenplan_heute', 'html') }}
\`\`\`

---

## 🎨 Anpassungsmöglichkeiten

### Farben ändern
Passen Sie die Farben an Ihr Theme an:
\`\`\`yaml
# Primärfarbe für Heute
background-color: var(--primary-color);
# Akzentfarbe für Morgen  
background-color: var(--accent-color);
# Eigene Farben
background-color: #1976d2;  # Blau
background-color: #388e3c;  # Grün
\`\`\`

### Icons ändern
Verwenden Sie verschiedene Material Design Icons:
\`\`\`yaml
icon: mdi:school-outline        # Schule
icon: mdi:calendar-today        # Kalender
icon: mdi:clock-outline         # Uhr
icon: mdi:book-education        # Buch
icon: mdi:calendar-alert        # Warnung
\`\`\`

### Mobile Optimierung
Die Tabellen sind bereits responsive. Für bessere mobile Darstellung können Sie die Spaltenbreiten anpassen:
\`\`\`css
th:nth-child(1) { width: 15%; } /* Stunde */
th:nth-child(2) { width: 25%; } /* Fach */
th:nth-child(3) { width: 20%; } /* Raum */
th:nth-child(4) { width: 25%; } /* Lehrer */
th:nth-child(5) { width: 15%; } /* Status */
\`\`\`

---

## 🔧 Fehlerbehebung

### Entitäten nicht gefunden
- Prüfen Sie in **Entwicklertools** → **Zustände**
- Stellen Sie sicher, dass die Integration korrekt installiert ist
- Überprüfen Sie die Schreibweise der Entitätsnamen

### Tabellen werden nicht angezeigt
- Überprüfen Sie, ob Daten in den Sensor-Attributen vorhanden sind
- Prüfen Sie das `html`-Attribut der Stundenplan-Sensoren
- Stellen Sie sicher, dass die Integration erfolgreich Daten abruft

### Card Mod funktioniert nicht
- Installieren Sie [Card Mod](https://github.com/thomasloven/lovelace-card-mod) aus HACS
- Starten Sie Home Assistant nach der Installation neu

### Flex Table Card Fehler
- Stellen Sie sicher, dass Flex Table Card aus HACS installiert ist
- Überprüfen Sie die JavaScript-Konsole auf Fehlermeldungen
- Versuchen Sie, den Browser-Cache zu leeren

---

## 📱 Screenshots

### Standard Markdown Card
![Standard Dashboard](https://via.placeholder.com/800x400/1976d2/FFFFFF?text=Standard+Markdown+Card)
*Einfache, aber funktionale Darstellung mit HTML-Tabellen*

### Flex Table Card
![Flex Table Dashboard](https://via.placeholder.com/800x400/388e3c/FFFFFF?text=Flex+Table+Card)
*Professionelle Tabellendarstellung mit erweiterten Features*

### Komplettes Dashboard
![Komplettes Dashboard](https://via.placeholder.com/800x600/673ab7/FFFFFF?text=Komplettes+Dashboard)
*Vollständige Schul-Management-Oberfläche*

---

## 📞 Support

Bei Problemen oder Fragen:
1. Überprüfen Sie die [Issues](https://github.com/MrIcemanLE/Schulmanager-homeassistant/issues) auf GitHub
2. Erstellen Sie ein neues Issue mit:
   - Ihrer Home Assistant Version
   - Der verwendeten Dashboard-Konfiguration
   - Screenshots des Problems
   - Log-Einträge falls vorhanden

---

**Viel Spaß mit Ihrem Schulmanager Dashboard! 🎓**