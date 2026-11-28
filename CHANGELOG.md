# Changelog

## 0.1.25

- Restored the administrator’s Studio button on the default kiosk dashboard. The toolbar stays within the viewport on narrow screens.
- Added an administrator-only shortcut at `/tiny-liveboard?studio=1`.

## 0.1.24

- Fixed installation on Home Assistant Core with Python 3.14 by allowing the Core-compatible aiomqtt 2.5 series and later compatible 2.x versions.
- Registered the sidebar before starting WIS2. The connector initializes TLS off the event loop, retries broker failures with backoff and leaves MeteoAlarm Atom available independently.

## 0.1.23

- Restored camera signal diagnostics in focused view. Recording status and WebRTC statistics are collected while their controls are visible.

## 0.1.22

- Removed the legacy precipitation overlay and migrated the external weather setting for existing profiles.
- Added public HTML article metadata support, bounded news fetches and corrected weather and warning freshness handling.
- Tightened media, configuration and WebSocket lifecycle management.

## 0.1.21

- Added per-profile Home Assistant access checks and filtered client configuration.
- Moved camera captures into private storage with expiring playback grants. Added direct RTSP support to motion and prebuffer.

## 0.1.20

- Reused the dashboard renderer for Studio live preview and stored themes centrally.
- Centered the 16:9 dashboard in the available viewport.

## 0.1.19

- Added Home Assistant calendar events in Tiny Calendar, bounded archive storage and used publisher publication dates.
