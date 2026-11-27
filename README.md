# Tiny LiveBoard

Early development build for Home Assistant. Add this repository to HACS as Integration, install, restart, then add Tiny LiveBoard in Settings > Devices & services. Open the sidebar panel and select entities in Studio.

Camera playback uses direct go2rtc WebSocket signaling (experimental). Configure ws://host/api/ws?src=stream or wss:// for HTTPS dashboards. Use a trusted private network; do not expose unauthenticated go2rtc publicly. Camera entity selection is retained but does not yet resolve stream URLs automatically. DR RSS retrieval with five-minute cache and explicit breaking categories is implemented; feed availability and category support are not yet verified. Radar, drag-and-drop and weather intelligence are not implemented. Not yet validated on Home Assistant.

News sources: DR, TV 2, TV2 ØST and Google News search for Kalundborg. Select sources in Studio. Regional and local endpoints need live validation.
