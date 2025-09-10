# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security

## [0.3.0] - 2025-09-10

### Changed
- Manifest: Integrationstyp von "service" auf "hub" geändert; Metadaten konsolidiert
- Button: Geräteinfos für Service-Gerät entfernt; Cooldown-Attribute vereinfacht (direkt aus Koordinator) und letzte manuelle Aktualisierung als ISO-Zeitstempel
- Einrichtung (__init__): Kein separates Service-Gerät mehr; es werden nur noch Geräte pro Schüler angelegt; Entfernt Verknüpfung "via_device"
- Allgemein: Logging und Geräteverwaltung aufgeräumt

### Removed
- Virtuelles Service-Gerät und "via_device"-Link zwischen Service und Schüler-Geräten

## [0.2.0] - 2025-01-06

### Added
- Comprehensive test suite for config flow
- PyRight configuration for enhanced type checking
- Enhanced debugging capabilities with request/response logging

### Changed
- Improved error handling in configuration flow
- Updated GitHub Copilot instructions with debugging paths
- Enhanced code quality and type safety

### Fixed
- Configuration flow stability improvements
- Better error messages for user guidance

## [0.1.0] - 2025-01-05

### Added
- Initial release of Schulmanager Online integration
- Support for student and teacher accounts
- Sensor platform for grades, homework, and general information
- Todo platform for homework and exam management
- Calendar platform for school events and lessons
- Button platform for data refresh functionality
- Multi-language support (German and English)
- Automatic data refresh every 5 minutes
- Error handling and user-friendly configuration flow
- HACS compatibility

### Features
- **Authentication**: Secure login with username/password and school ID
- **Data Collection**: 
  - Student grades by subject
  - Homework assignments with due dates
  - Exam schedules
  - School announcements
  - Lesson schedules
- **Home Assistant Integration**:
  - Native sensor entities for all data types
  - Todo entities for task management
  - Calendar entities for scheduling
  - Configurable via UI (no YAML required)
- **Localization**: German and English translations
- **Reliability**: Automatic retry logic and error recovery

[Unreleased]: https://github.com/MrIcemanLE/Schulmanager-homeassistant/compare/v0.3.0...HEAD
[0.2.0]: https://github.com/MrIcemanLE/Schulmanager-homeassistant/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/MrIcemanLE/Schulmanager-homeassistant/releases/tag/v0.1.0
[0.3.0]: https://github.com/MrIcemanLE/Schulmanager-homeassistant/compare/v0.2.0...v0.3.0
