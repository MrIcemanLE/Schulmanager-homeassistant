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

## [0.3.0] - 2025-01-09

### 🏗️ BREAKING CHANGES
- **Device Architecture Redesigned**: Integration now uses service-based device hierarchy
  - Main "Schulmanager Online" service device with student sub-devices
  - **⚠️ Migration required**: Delete old integration, restart HA, reinstall
  - See [MIGRATION_0.3.0.md](MIGRATION_0.3.0.md) for detailed instructions

### Added
- Service-based device hierarchy for better organization
- Migration guide for 0.3.0 upgrade ([MIGRATION_0.3.0.md](MIGRATION_0.3.0.md))
- Enhanced device registry management with proper linking
- Future-proof compliance with Home Assistant Core 2026.9

### Changed
- `manifest.json`: Integration type changed from "hub" to "service"
- Device creation logic updated to create proper parent-child relationships
- Button entity now properly linked to service device
- Improved device registry persistence and cleanup

### Fixed
- Fixed YAML code block formatting in DASHBOARD.md - all code examples now render correctly
- Device registry persistence issues resolved
- Proper device hierarchy now saves correctly to registry
- Service device creation and student linking improved

### Technical
- Compliant with `suggested_area` deprecation guidelines (HA Core 2026.9)
- No musllinux wheels required (pure Python dependencies)
- Enhanced device-entity relationship management

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
[0.3.0]: https://github.com/MrIcemanLE/Schulmanager-homeassistant/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/MrIcemanLE/Schulmanager-homeassistant/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/MrIcemanLE/Schulmanager-homeassistant/releases/tag/v0.1.0