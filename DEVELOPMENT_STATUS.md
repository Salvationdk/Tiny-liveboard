# Udviklingsstatus

Udgangspunkt: `38e7d18`, version 0.1.18.

| Pakke | Status | Arbejdsområde |
|---|---|---|
| A – Nyheder og kalender | Delvist implementeret | Nyhedsmotor og arkiv genbrugt. HA-kalendere, læseadgang, månedsnavigation, tidszoner og fælles arkivbudget tilføjet. Live-kilder og installation afventer praktisk test. |
| B – Studio | Delvist implementeret | Layouteditor findes. Fælles livepreview og central temalagring gennemgås næste gang. |
| C – Brugere og skærme | Delvist implementeret | Profiler, skærmplaner og revision findes. Profiladgang og isolering af konfiguration gennemgås. |
| D – Kamera og medier | Delvist implementeret | HA, go2rtc, optagelse og motion er koblet til frontend. Ressourcestyring, adgang og genetablering skal efterprøves. |
| E – Vejr | Delvist implementeret | Vejr, vind og varsler har kode. Radar skal fjernes, og håndtering af forældede data skal kontrolleres. |
| F – Drift og sikkerhed | Delvist implementeret | Beskyttelse og oprydning findes flere steder. Samlet gennemgang udestår. |
| G – Dokumentation | Delvist implementeret | README indeholder forældede oplysninger. Installation og fysisk test skal samles. |

## A – første ændring

- `agenda.py`, `__init__.py`, `frontend/display.js` og `news.py` ændret. Tiny Calendar henter en måned ad gangen fra Home Assistant, og viser heldagsaftaler på hver dato i deres interval. Nyhedsarkivet anvender udgiverens dato, når den findes.
- Installation på Home Assistant, delvis kalenderfejl, brugerrettigheder, sommertid og fysisk vægskærm afventer praktisk test.
- 0.1.19. Syntaks og `git diff --check` gennemført. Eksisterende Python-suite gav 36 beståede og én manglende radarafhængighed (`pyproj`). Profiltest i Node bestod. Vejrtesten fejlede allerede på 0.1.18 og gennemgås i E.

## B – Studio og temaer

- Version 0.1.20. A blev gemt som `10b9a95`.
- `frontend/display.js` bruger dashboardets renderer i Studio og centrerer dashboardet i 16:9. Preview bruger HA-tilstande og senest hentede nyheder. Kamerafelterne bruger navne og formatforhold for at undgå ekstra videoforbindelser under redigering.
- `frontend/themes.js` gemmer genbrugelige temaer i den centrale konfiguration. `__init__.py` validerer biblioteket. Lokale browser-temaer kan importeres ved første Studio-gem.
- Syntaks for de ændrede JavaScript-moduler og profilers/nyheders Python-tests gennemført. Afventer visuel test af drag, resize, gitter og billedskalering på fysisk skærm.
