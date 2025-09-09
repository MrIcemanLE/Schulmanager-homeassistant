# GitHub Topics Setup

To fix the HACS validation error, you need to add the following topics to your GitHub repository:

## Required Topics for HACS:

1. Go to your repository: https://github.com/MrIcemanLE/Schulmanager-homeassistant
2. Click on the ⚙️ **Settings** tab (repository settings, not account settings)
3. Scroll down to the **Topics** section
4. Add the following topics (click "Add a topic" for each):

### Recommended Topics:
```
home-assistant
hacs
integration
schulmanager
school
timetable
home-automation
custom-component
python
germany
```

### Minimum Required Topics:
```
home-assistant
hacs
integration
```

## Alternative: Using GitHub CLI

If you have GitHub CLI installed, you can run:

```bash
gh repo edit MrIcemanLE/Schulmanager-homeassistant --add-topic "home-assistant,hacs,integration,schulmanager,school,timetable,home-automation,custom-component,python,germany"
```

## Why These Topics Are Important:

- **home-assistant**: Required for Home Assistant integrations
- **hacs**: Required for HACS discovery and validation
- **integration**: Identifies this as a Home Assistant integration
- **schulmanager**: Makes it discoverable for German school users
- **school**: Broader category for educational tools
- **timetable**: Specific functionality description
- **home-automation**: General category
- **custom-component**: Technical classification
- **python**: Programming language
- **germany**: Geographic/language targeting

After adding these topics, the HACS validation should pass!