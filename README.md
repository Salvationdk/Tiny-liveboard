# Tiny LiveBoard

Tiny LiveBoard is a Home Assistant integration for a 16:9 wall display. The sidebar panel and optional Lovelace card use the same saved configuration and renderer. Studio is available to administrators from the unprofiled sidebar panel.

## Installation og opdatering

1. Tilføj dette repository i HACS som en brugerdefineret integration, og installér den ønskede version. Ved manuel installation kopieres hele `custom_components/tiny_liveboard` til Home Assistants `config/custom_components`.
2. Genstart Home Assistant. Gå til **Indstillinger → Enheder og tjenester → Tilføj integration → Tiny LiveBoard**. Vælg eksisterende kamera- og vejrentiteter, hvis de skal konfigureres med det samme.
3. Åbn **Tiny LiveBoard** i sidebjælken med en administratorbruger. Tryk **Studio**. Brug **Gem** nederst i Studio efter ændringer.
4. Efter opdatering af en manuel installation, genstart Home Assistant og genindlæs vægskærmens browser. Ved opdatering fra en tidligere version flyttes registreringer i den tidligere delte mediemappe til privat lagring, når filsystemet tillader det. Hvis en fil ikke flyttes, viser Home Assistant en advarsel i loggen.

HACS-konfigurationen angiver Home Assistant 2025.6 som minimum. FFmpeg skal være installeret i samme miljø som Home Assistant for direkte RTSP, optagelse, bevægelsesanalyse og videominiaturer.

### Lovelace

Tilføj JavaScript-modulressourcen `/tiny_liveboard/display.js?v=0.1.24`. Opret derefter et manuelt kort.

```yaml
type: custom:tiny-liveboard-card
height: 480
profile: Køkken
```

Højde angives i pixels fra 240 til 2400. `profile` er valgfri. Brug én aktiv visning af samme kamera pr. skærm, når videoforbruget skal holdes nede.

## Studio og skærmprofiler

- **Layout** har flytning, størrelsesændring, lag, synlighed, fortryd og gentag. Hold Shift for et grovere gitter. Forhåndsvisningen bruger dashboardets renderer og viser de aktuelle entitetstilstande. Kamerafelter repræsenteres af navn og billedformat. Brug **Forhåndsvis** under kameraopsætningen til en rigtig kameratest.
- **Design** indeholder temaer, farver og vejrikoner. Gem et tema i det centrale bibliotek og indlæs det i et andet layout eller en anden profil. Tryk **Gem** nederst for at gemme biblioteket på serveren.
- **Skærmprofiler** gemmer layout og indstillinger under et navn. Tildel et skærm-ID, fx `kitchen`, og åbn `/tiny-liveboard?screen=kitchen` på skærmen. Tidsplaner bruger Home Assistants tidszone, understøtter intervaller over midnat og vælger den første regel, der passer. En tilladt eksplicit profil kan vælges med `?profile=Køkken`.
- Angiv de tilladte Home Assistant-bruger-ID’er på hver profil, som skal have begrænset adgang. Et tomt felt tillader alle aktive HA-brugere. Sidebjælkens standardkonfiguration kan tildeles på samme måde. Brug en almindelig Home Assistant-bruger på vægskærmen.
- **Kiosk** skjuler LiveBoards værktøjslinje på skærmen. Fuldskærm styres af browseren og kræver normalt et tryk. Home Assistant-menuen og enhedens strømstyring håndteres via klienten eller operativsystemet.
- **Diagnostik** viser skærmenes seneste livstegn. En skærm markeres offline efter 90 sekunder. Studio kan eksportere og importere konfigurationsbackup. Backup fra en administrator kan indeholde private adresser og legitimationsoplysninger og skal opbevares privat.

## Nyheder og Tiny Calendar

Under **Studio → Nyheder** kan du vælge danske kilder og tilføje egne med `Navn | https://eksempel.dk/feed` pr. linje. RSS, Atom og offentlige HTML-sider med struktureret artikelmetadata understøttes. Google News-kilder kan levere links uden synlig udgiveradresse. Artikler åbnes fra tickeren. Den tilgængelige beskrivelse og udgiverens link bruges, hvis siden kræver abonnement eller mangler åbne artikeldata. Breaking kræver en eksplicit kategori i feedet og en gyldig, aktuel udgivelsesdato.

Gem en artikel i læseren og åbn kalenderikonet i tickeren. Arkivet er personligt. Det bruger udgivelsesdatoen eller en markeret gemmedato. Arkivet har højst 500 gemte artikler pr. bruger og et fælles lagringsbudget på ca. 32 MiB. Ved overskridelse fjernes de ældste gemninger først. Du kan også fjerne artikler manuelt.

Vælg op til otte HA-kalenderentiteter i Studio. Tiny Calendar viser en måned ad gangen i Home Assistants tidszone. Vælg en dag eller blad mellem måneder. Heldagsaftaler vises på alle de dage, aftalen dækker, og slutter ved den eksklusive slutdato. De valgte kalendere kræver HA-læseadgang. En kalenderfejl vises særskilt fra en tom kalender.

## Kameraer, bevægelse og medier

HA-kameraentiteter er den anbefalede afspilningsvej for vægskærme. Ved eksisterende go2rtc kan administratoren angive serveren og vælge en stream. Til HTTPS skal go2rtc være tilgængelig via HTTPS/WSS. Discovery kræver browseradgang og CORS. go2rtc's egen adgang skal konfigureres hos udbyderen.

RTSP(S) bruges på serveren til optagelse og bevægelsesanalyse. Brug en HA-kameraentitet eller go2rtc til at vise selve streamen i browseren. Bevægelse kan komme fra billedanalyse eller en HA-binærsensor. Prebuffer på op til 30 sekunder bruger FFmpeg og kræver en fungerende stream. Arkivet gemmer snapshot- og optagelsesfilernes tid, størrelse og låsestatus. Låste filer er undtaget oprydning. Standardoprydning kører hver time med 30 dages opbevaring og 5 GiB kvote.

Galleriet kontrollerer profilens tilladelser og HA-kameraadgang. Afspilningslinks er tidsbegrænsede og filspecifikke. Del dem kun med brugere, der må se optagelsen.

## Vejr og varsler

Home Assistant leverer aktuelle vejrforhold og de time- og døgnprognoser, som den valgte vejrplatform tilbyder. I Studio kan du desuden aktivere eksterne vejrdata og kort. DMI leverer stationsobservationer, Open-Meteo leverer modellens vind og pollen, og OpenStreetMap leverer kortbaggrunden. Kilderne får regionale koordinater, når de relevante visninger åbnes.

DMI-varsler kan aktiveres via MeteoAlarm. WIS2 og Atom har separate forbindelsesstatusser. Lokale varsler filtreres på gyldig geometri. Varsler uden verificerbart område vises med den usikkerhed; ved en feedfejl kan der stadig blive vist cachede, gyldige varsler. Brug [DMI's officielle varsler](https://www.dmi.dk/varsler) for den aktuelle officielle visning.

## Lokal kontrol

Installér Python, Node.js og de deklarerede Python-pakker samt pytest. Kør fra roden:

```sh
python scripts/test-local.py
```

### Praktisk accepttest i Home Assistant

| Område | Test | Forventet resultat |
|---|---|---|
| Installation | Opdatér fra 0.1.18 på en testinstallation og genstart | Sidebar og tidligere dashboard åbner. Tidligere skærmprofiler og layout kan indlæses. |
| A | Vælg et fungerende RSS-/Atom-feed og en struktureret HTML-kilde. Gem en artikel, genstart, og find den på udgivelsesdatoen. Vælg en kalender med en heldagsaftale og en tidsbestemt aftale omkring et tidszoneskift. | Arkivet bevarer artiklen. Kalenderen viser korrekt lokaldato og eksklusiv slutdato. Fejl på én kalender er synlig. |
| B | Flyt og skalér felter, brug Shift, skift lag, fortryd, anvend tema og gem. Genindlæs med to skærmopløsninger. | Preview og dashboard viser samme layout og tema. 16:9-fladen er centreret og scrollbar-fri. |
| C | Opret to profiler med hver sin adgang, en plan over midnat og en almindelig bruger. Prøv begge webadresser og gem et profil-eksport/import-forløb. Afbryd og genetablér forbindelsen. | Brugeren ser tilladte profiler, og skærmen skifter efter planen. Dashboardet genoptager opdatering. |
| D | Vis HA- og go2rtc-kamera, afbryd streamen, og genetablér den. Optag via bevægelse med prebuffer. Afspil og søg i optagelsen, test galleritilladelser og oprydning. | Streamen kommer tilbage. Optagelsen bevares på tværs af genstart, og afspilning kræver gyldig adgang. |
| E | Brug aktuel HA-vejrentitet, DMI-observationer, vindkort og MeteoAlarm/WIS2. Afbryd en kilde. | Datakilde, aktualitet og kildefejl fremgår. Sammenlign aktive varsler med DMI. |
| F–G | Lad den fysiske skærm køre et døgn. Genindlæs integrationen og browseren under testen. Kontroller CPU, diskplads og antal videoforbindelser før og efter. | Dashboardet genoptager drift, og antal forbindelser stiger ikke for hver genindlæsning. |

Ved fejlsøgning skal du kontrollere **Indstillinger → System → Logfiler** og Studio → Diagnostik. Tjek HA-brugerens entitetsadgang, skærm-ID og profilnavn, hvis et dashboard mangler indhold. Ved videofejl kontrolleres stream fra samme klient, TLS, FFmpeg og plads på konfigurationsdisken.
