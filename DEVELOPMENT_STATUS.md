# Udviklingsstatus

Udgangspunkt: `38e7d18`, version 0.1.18.

## A – første ændring

- `agenda.py`, `__init__.py`, `frontend/display.js` og `news.py` ændret. Tiny Calendar henter en måned ad gangen fra Home Assistant, og viser heldagsaftaler på hver dato i deres interval. Nyhedsarkivet anvender udgiverens dato, når den findes.
- Installation på Home Assistant, delvis kalenderfejl, brugerrettigheder, sommertid og fysisk vægskærm afventer praktisk test.
- 0.1.19. Syntaks og `git diff --check` gennemført. Eksisterende Python-suite gav 36 beståede og én manglende radarafhængighed (`pyproj`). Profiltest i Node bestod. Vejrtesten fejlede allerede på 0.1.18 og gennemgås i E.

## B – Studio og temaer

- Version 0.1.20. A blev gemt som `10b9a95`.
- `frontend/display.js` bruger dashboardets renderer i Studio og centrerer dashboardet i 16:9. Preview bruger HA-tilstande og senest hentede nyheder. Kamerafelterne bruger navne og formatforhold for at undgå ekstra videoforbindelser under redigering.
- `frontend/themes.js` gemmer genbrugelige temaer i den centrale konfiguration. `__init__.py` validerer biblioteket. Lokale browser-temaer kan importeres ved første Studio-gem.
- Syntaks for de ændrede JavaScript-moduler og profilers/nyheders Python-tests gennemført. Afventer visuel test af drag, resize, gitter og billedskalering på fysisk skærm.

## C og D – adgang, skærme og medier

- Version 0.1.21. B blev gemt som `c5fd715`.
- `__init__.py` kontrollerer profiladgang på serveren. Almindelige brugere får kun tilladte profiler, skærmtildelinger og HA-kameraer. Direkte streamadresser og andre brugeres ID'er filtreres fra. Studio kan sætte bruger-ID'er pr. profil. Dashboardet prøver igen ved opstartsfejl.
- `media.py`, `motion.py` og `__init__.py` anvender privat lagring og afspilningslinks med tidsbegrænset, filspecifik adgang. Gamle optagelser flyttes ved opstart. Direkte RTSP kan bruges til motion og prebuffer. Optagelser og snapshots har samtidighedsgrænser, og skjulte kamerafelter starter ikke videoforbindelser.
- Dashboardets direkte go2rtc bruges af administratorer. Almindelige vægskærmsbrugere skal have adgang til en Home Assistant-kameraentitet. Praktisk kontrol af eksisterende mediefiler, optagelse, linkudløb, tvungen afbrydelse og FFmpeg mangler.
- Python 35 test bestået med den udgående radarsuite udeladt. Kamera- og profiltest i Node bestod.

## E, F og G – vejr, drift og dokumentation

- Version 0.1.22. C og D blev gemt som `4b6fdfc`.
- Fjernet vejrkomponent, endpoints, dekoder og de tilhørende tests for nedbørradaren. Den gamle eksterne vejrindstilling migreres til `externalWeather`, også i gemte profiler. Visningen markerer fejl og forældede prognoser og ignorerer varsler med ugyldige tidsstempler.
- `agenda.py` bruger HA-kalenderentitetens læsemetode efter serverkontrol af HA-læseadgang. `news.py` læser også offentlige HTML-artikler og strukturerede artikellister, begrænser samtidige hentninger og validerer offentlige adresser og omdirigeringer. Tickerens hastighed begrænses for lange lister.
- `__init__.py` afviser WebSocket-kald under genindlæsning og frigiver aktive kald, streams og varslingsforbindelse. `media.py` begrænser samtidige miniatureprocesser og begrænser den samlede tid for fastlåste optagelser. Deklarerede pakker kontrolleret i lokalt HA-miljø.
- README, ændringslog og eksisterende lokal runner opdateret. Runneren bruger nu pytest til både funktions- og unittest-tests. Ingen workflows blev kørt. Ingen HACS-release blev oprettet.

## Aktuel status pr. arbejdspakke

| Pakke | Kode og lokal verifikation | Afventer praktisk test |
|---|---|---|
| A | RSS, Atom, struktureret HTML, Breaking og personligt arkiv implementeret. Kalender og HA-adgang verificeret med en lokal kalender på HA Core 2025.6. | Eksterne kilder, datoer ved sommertid og genstart med eksisterende personligt arkiv. |
| B | Fælles renderer, central temalagring og 16:9. Studio åbning, preview og gem verificeret i headless Chromium med HA-testdata. | Træk, størrelsesændring, lag og billedforhold med de fysiske skærmes input og opløsninger. |
| C | Adgangsregler, konfigurationsfiltrering, plan, kiosk og import/eksport. Administrator og almindelig bruger kontrolleret på HA Core 2025.6. | Faktiske skærmprofiler, browserfuldskærm og afbrydelser på brugerens enheder. |
| D | HA-kamera, eksisterende go2rtc, direkte RTSP til server, motion, prebuffer, arkiv og privat afspilning. Kameraets lokale JavaScript-suite bestået. | Faktiske RTSP-, go2rtc- og HA-streams, FFmpeg-output, afspilning, migrering og 24-timers drift. |
| E | HA-vejret, vindkort, MeteoAlarm og WIS2 bevaret. Vejr- og varselsparseres eksisterende tests bestået. | Sammenhold en aktiv dansk varselshændelse med DMI og verificér eksterne kilder fra installationen. |
| F | WebSocket-adgang, private medier, tidsgrænser og oprydning gransket. Genindlæsning verificeret på HA Core 2025.6. | Døgnmåling af CPU, disk, net og videoforbindelser på den fysiske installation. |
| G | Dokumentation og accepttest opdateret. 35 Python-test, 7 Node-test, Python-/JS-syntaks, Ruff E9/F, JSON, YAML, cacheversion og 12 WebSocket-referencer gennemført. | Kør README's accepttest på den installation, der skal anvendes. |

Home Assistant Core 2025.6-smoketesten brugte rigtig runtime, WebSocket og lokal kalender. Miljøets netværksadapteropslag blev erstattet med loopback til testen. HACS-installation og eksterne tjenester afventer den praktiske test.

Næste opgave: kør accepttesten i README på den faktiske vægskærm og med dens kamera- og vejrkilder.

## 0.1.23 – kameradiagnostik og udvidet lokal kontrol

- E, F og G blev gemt som `2acfbf5`.
- `frontend/display.js` gør kameradiagnostik tilgængelig i kamerafokus. Optagestatus hentes kun, når knapperne vises. `frontend/camera.js` måler WebRTC-statistik, når signalpanelet er åbent.
- Headless Chromium verificerede også træk og fortryd i Studio. Lokal HA Core 2025.6 verificerede nægtet medieadgang for en almindelig bruger samt beskyttet afspilning og HTTP Range med en FFmpeg-genereret testfil.
- Afventer stadig målinger med faktiske kamerastreams, aktive varsler og den fysiske skærm.
