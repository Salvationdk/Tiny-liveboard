# Tiny LiveBoard

Early development build for Home Assistant. Add this repository to HACS as Integration, install, restart, then add Tiny LiveBoard in Settings > Devices & services. Open the sidebar panel and select entities in Studio.

Camera playback uses direct go2rtc WebSocket signaling (experimental). Configure ws://host/api/ws?src=stream or wss:// for HTTPS dashboards. Use a trusted private network; do not expose unauthenticated go2rtc publicly. Camera entity selection is retained but does not yet resolve stream URLs automatically. DR RSS retrieval with five-minute cache and explicit breaking categories is implemented; feed availability and category support are not yet verified. Radar, drag-and-drop and weather intelligence are not implemented. Not yet validated on Home Assistant.

News sources: DR, TV 2, TV2 ØST and Google News search for Kalundborg. Select sources in Studio. Regional and local endpoints need live validation.

## News engine
RSS/Atom, independent five-minute fetch caches, 48-hour article retention, one-hour breaking expiry (explicit categories and valid publication date required), source diagnostics and Studio ticker colors/speed. TV2 ØST and local media use Google News queries; direct feed availability and live integration remain to be verified. Undated articles expire 48 hours after first observation within a running instance.

### Existing go2rtc
Enter the existing server's HTTP(S) base address in Studio, click discovery and select named streams. Browser discovery requires reachable API and CORS permission; HTTPS panels require HTTPS/WSS. Preview each stream before saving. No go2rtc configuration is changed. Manual WebSocket URL remains an alternative. Direct peer connectivity and browser codec support must be tested on the target display.

### Tiny Weather Engine
Native animated weather panel with hourly/daily forecasts via Home Assistant weather.get_forecasts, temperature and precipitation graphs, wind and sun tabs. Missing data are not fabricated. Radar, official alerts, independent moon calculations and weather intelligence remain pending. Provider support varies.
