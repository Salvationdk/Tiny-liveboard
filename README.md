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

Weather extensions: approximate lunar phase, forecast-based everyday advice, rain/snow scenes and themes, selectable HA camera entities for radar/wind imagery and sensor entities for warnings/pollen. These are adapters, not independent radar or official warning providers; animated radar timelines and geographic wind maps require a suitable provider. Advice is not a safety guarantee.

Weather visual polish: scalable SVG weather artwork, translucent forecast surfaces, compact screen rules, and opt-in RainViewer historical radar tile playback. Radar is a regional tile without a geographic basemap; external availability, terms and browser CORS must be verified. No coordinates are sent unless external radar is enabled and opened. Official DMI warnings still require a configured HA sensor.

Weather completion increment: opt-in OSM raster basemap with home marker and RainViewer overlay; local forecast wind direction timeline; approximate NOAA-style solar calculations; experimental DMI RSS adapter (endpoint not verified, no claim of warning coverage). Geographic wind field still requires a camera provider. External map services receive tile coordinates only when enabled. Verify provider terms before production deployment.

Animated SVG weather artwork is shared by current, hourly and daily forecasts; reduced-motion preferences disable icon animation. DMI official warnings remain unverified; consult https://www.dmi.dk/varsler directly.

Forecast refresh tracks hourly and daily successes independently. Failed requests retry after one minute; cached data is explicitly labelled stale after a failure or fifteen minutes without a successful refresh.

### Weather warnings
Optional Danish MeteoAlarm Atom feed: https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-denmark (EUMETNET / national meteorological service). Updates are cached for five minutes. Polygon geometry is filtered against Home Assistant coordinates when supplied; area-name-only warnings remain geographically unverified. Always consult https://www.dmi.dk/varsler for official guidance. See https://meteoalarm.org/en/live/page/terms-and-conditions for reuse terms. The feed is not a safety-critical notification service.


## Lovelace dashboard card

With the integration installed and loaded, add a dashboard resource of type JavaScript module: `/tiny_liveboard/display.js`. Then add a manual card:

```yaml
type: custom:tiny-liveboard-card
height: 480
```

Height is in pixels (240–2400). The card shares the integration's saved Studio configuration with the sidebar panel. Admin users can edit that shared configuration. Each mounted card opens its own camera streams; avoid unnecessary duplicate cards. Browser reload may be needed after adding the resource.


## Central screen management

Open the Tiny LiveBoard sidebar panel as an administrator to configure Studio.
Create named profiles, then assign screen IDs in the screen assignment field,
for example `{"kitchen":"Day","livingroom":"Evening"}`.
Open `/tiny-liveboard?screen=kitchen` on the corresponding display.
Use the visual schedule editor to select a profile, weekdays and start/end
times. Overnight intervals are supported; the first matching rule wins.
The default assigned profile is restored outside scheduled intervals.
Explicit `?profile=NAME` overrides screen schedules.

Kiosk mode hides LiveBoard's own toolbar, not the Home Assistant shell or
operating-system controls. Use the unprofiled sidebar panel for administration.
Screen presence is reported every 30 seconds; a 90-second timeout marks a
screen offline. This measures browser connectivity, not hardware power.
Presence records are reset on integration restart.

## Weather data sources

External weather maps are opt-in. The regional wind map prefers recent DMI
station observations with matching station IDs and observation times.
Missing points use Open-Meteo model data when available. These are different
data types, not interchangeable measurements. Wind arrows indicate movement.
Radar attempts DMI ODIM decoding and falls back to RainViewer when unavailable.
MeteoAlarm Atom and WIS2 provide warning information. A missing feed or missing
geometry must not be interpreted as an official all-clear.
External map services receive regional location information.

## Local development and verification

Install Python and Node.js, then install the Python dependencies required by
the integration manifest and its tests (including numpy, Pillow and defusedxml).
From the repository root run:

```sh
python scripts/test-local.py
```

This runner performs local syntax checks and regression tests without dispatching
GitHub Actions. Synthetic radar and CAP fixtures do not verify live service
availability or compatibility with actual DMI files. Before a production release,
verify installation on the target Home Assistant version, real camera streams,
DMI radar and wind data, WIS2 connectivity, news feeds, profile transitions,
Studio persistence and the physical display layout. No external MQTT broker or
additional hardware is required for the intended architecture.


## Opsætning af anden bruger, tablet eller vægpanel (dansk)

1. Opret en almindelig Home Assistant-bruger under Indstillinger → Personer → Brugere. Undgå administratorlogin på delte skærme.
2. Åbn Tiny LiveBoard fra sidebjælken som administrator, uden skærmparameter. Konfigurér kameraer, vejr, layout og design i Studio.
3. Under **Medier og adgang** vælges brugerens ID (brugervælger eller manuel indtastning), relevante kameraers capture-indstilling og de nødvendige tilladelser: snapshot, optagelse, galleri, afspilning, sletning og låsning. Giv mindst mulige rettigheder.
4. Under **Skærmprofiler** oprettes et profilnavn, fx Køkken. Tryk Gem profil. Tildel skærm-ID i feltet Skærm-ID → profil, fx `{"kitchen":"Køkken"}`. Tryk derefter Gem nederst i Studio.
5. Log ind som den almindelige bruger på tabletten og åbn `https://DIN-HA-ADRESSE/tiny-liveboard?screen=kitchen` (brug din faktiske HA-adresse og port). Studio har en adressegenerator.
6. Aktivér eventuelt kiosk i profilen. Kiosk skjuler Tiny LiveBoards værktøjer, ikke nødvendigvis HA-menuen. Brug Diagnostik til at kontrollere skærmstatus.
7. Maksimér kameraet for at se de tilladte optageknapper. Kontrollér adgang med den almindelige brugers login. Skærm-ID er ikke et adgangskodebeskyttet sikkerhedstoken. Profil- og medieadgang skal verificeres på den konkrete installation.

Flere skærme kan have samme profil eller forskellige profiler. Eksempel: `{"kitchen":"Køkken","hall":"Entré"}`. Brug den almindelige HA-adresse uden parametre til administration. Skærmopsætningen er endnu ikke verificeret på alle HA-versioner.
