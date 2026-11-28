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


## 0.1.24 – Python 3.14 og afhængigheder

- Udgangspunktet er `c7a2daa` (0.1.23). Den vedlagte log viser Python 3.14 og fejl i Home Assistants afhængighedsresolver inden konfigurationsdialogen. Loggen angiver ikke Core-patchversionen. Linjerne i traceback matcher den lokalt testede Core 2026.11.3.
- Core 2026.11.3 begrænser aiomqtt til `>=2.5.0`. Den tidligere `==2.4.0` har ingen løsning sammen med den begrænsning. PyPI-pakkens Python-metadata for 2.4.0 tillader i sig selv Python 3.14.
- `manifest.json` bruger nu `aiomqtt>=2.5.0,<3.0`. Core 2026.11.3’s pakkeinstaller afviste den gamle pin med Core-begrænsningerne og installerede de nye krav i en tom pakkemappe med aiomqtt 2.5.1, paho-mqtt 2.1.0 og defusedxml 0.7.1. Aiomqtt accepterer Paho 2.1.0, præcis den version Core selv angiver for MQTT. Den øvrige afhængighed, `defusedxml==0.7.1`, er kompatibel med de kontrollerede Core-begrænsninger og bruges fortsat til sikker XML-læsning.
- `wis2.py` indlæser MQTT og TLS-certifikater i Home Assistants executor. Brokerfejl giver genforsøg med stigende interval, og forbindelsesstatus nulstilles ved afbrydelse og stop. Atom er uafhængig. `__init__.py` registrerer sidepanelet før opstart af WIS2-opgaven.
- Lokalt på Python 3.14.10 og Core 2026.11.3 bestod konfigurationsdialog, opstart, sidepanelregistrering, HTTP-servering af frontendmodulet, en rigtig lokal kalender via WebSocket og genindlæsning. MQTT- og Atom-nedetid blev simuleret i den kørende Core-test. Separat bestod MQTT-forbindelse, WIS2-abonnement, levering og lukning med de faktiske aiomqtt/Paho-biblioteker mod en lokal MQTT-testbroker.
- 37 Python-tests, 7 Node-tests, Python/JavaScript-syntaks, Ruff E9/F, afhængighedskontrol, JSON/YAML, cacheversion og frontend/backend-referencer bestod. `tests/test_wis2.py` dækker genforsøg og stop ved brokerfejl samt opstartsfejl ved TLS-initialisering.
- Installation på brugerens HA-installation, Marketplace/HACS-opdatering og aktive eksterne WIS2-/MeteoAlarm-varsler afventer praktisk test.


## 0.1.25 – adgang til Studio

- Udgangspunkt `376f9e8` (0.1.24). Kiosk skjulte Studio-knappen på standardpanelet, selv for administratorer.
- `frontend/display.js` bruger én regel til synlighed og viser Studio på standardpanelet uden for den beskårede 16:9-flade. Administratorer kan åbne Studio direkte på `/tiny-liveboard?studio=1`. Profilerede kioskskærme skjuler fortsat værktøjslinjen ved almindelig brug.
- Chromium ved 375 × 740 px med simuleret HA-data verificerede Studio-åbning og gemning i kiosktilstand, en almindelig skærmprofil, direkte Studio-adresse og adgangsafvisning for en almindelig bruger. Afventer kontrol på brugerens faktiske Home Assistant.
