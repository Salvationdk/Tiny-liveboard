# Changelog

## 1.0.0 — Unreleased

### Added
- Landscape wall display with two camera streams, weather and news ticker.
- Camera focus transitions, stream recovery and diagnostics.
- Weather forecasts, advice, radar, lightning, wind and pollen views.
- DMI observations and experimental ODIM radar decoding; external fallback sources.
- MeteoAlarm Atom and experimental WIS2 warning ingestion.
- Studio layout editing, layers, widgets, Lovelace cards and configuration backups.
- Named profiles, per-screen assignments, weekday schedules and kiosk controls.
- Central browser presence monitoring.
- Local Python and JavaScript regression test runner and synthetic fixtures.

### Changed
- Revision-checked configuration persistence and server-side geometry validation.
- Improved responsive layout, accessibility and offline news handling.

### Release gates
- Run local regression suites and resolve failures.
- Verify supported Home Assistant versions and dependency installation.
- Verify live DMI, WIS2, news and camera endpoints.
- Verify Studio save, restore, undo, profile transitions and kiosk recovery.
- Verify HACS installation and upgrade on a real Home Assistant instance.

The 1.0.0 version is not released until these checks are complete.
