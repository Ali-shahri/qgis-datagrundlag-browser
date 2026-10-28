# Datagrundlag Browser – QGIS-plugin

Søg i og tilføj danske grunddata fra [datagrundlag.dk](https://datagrundlag.dk/) direkte som lag i QGIS.

*English: An unofficial QGIS plugin for browsing [datagrundlag.dk](https://datagrundlag.dk/), an open catalogue of Danish public base data published as GeoParquet and FlatGeobuf. Search all datasets, add the latest snapshot, load data as of a given date, and refresh layers to the latest snapshot. The user interface is in Danish.*

> Uofficielt plugin. Det er ikke lavet af eller tilknyttet datagrundlag.dk eller MapCentia.

## Hvad kan det?

- **Søg** i alle datasæt i kataloget, fx "lokalplan", "geofa" eller "natura".
- **Tilføj nyeste data** med et dobbeltklik. Lagnavnet viser snapshot-datoen.
- **Gå tilbage i tid:** hent data, som de så ud på en bestemt dato (nyeste snapshot på eller før datoen).
- **Opdatér alle lag** til nyeste snapshot med ét klik. Lag, der er låst til en dato, bliver ikke ændret.

## Installation

**Fra QGIS' plugin-arkiv** (når pluginet er godkendt):
1. Vælg **Plugins → Administrer og installer plugins**.
2. Søg efter **Datagrundlag Browser** og klik **Installer**.

Så længe pluginet er markeret som eksperimentelt, skal **Vis også eksperimentelle plugins** være slået til under fanen *Indstillinger*.

**Fra ZIP-fil:**
1. Hent den nyeste ZIP under *Releases*.
2. Vælg **Plugins → Administrer og installer plugins → Installer fra ZIP**.

## Brug

1. Klik på den blå database-knap i værktøjslinjen, eller vælg **Web → Datagrundlag Browser**.
2. Skriv i søgefeltet og dobbeltklik på et datasæt.
3. Zoom ind på dit område, før du tilføjer store landsdækkende datasæt. QGIS henter kun de features, der er i kortudsnittet.

Lagene gemmes i projektet som almindelige lag. Brug **Opdatér alle lag til nyeste**, når du åbner projektet igen senere.

## Krav

- QGIS 3.28 eller nyere.
- Datasæt med geometri hentes som FlatGeobuf og virker i alle understøttede QGIS-versioner.
- Tabeller uden geometri (fx BBR-bygninger og DAR-adresser) hentes som GeoParquet. Det kræver en GDAL med Parquet-driver, fx QGIS 3.34+ installeret via OSGeo4W på Windows.

## Sådan virker det

Pluginet læser STAC-kataloget på `https://datagrundlag.s3.eu-west-1.amazonaws.com/filer/dk/catalog.json`. For hvert datasæt slår det `latest.json` op (nyeste snapshot) eller `collection.json` (alle snapshots) og åbner filen direkte fra S3 via GDAL's `/vsicurl/`. Der er ingen server eller login involveret.

## Data og vilkår

Data kommer fra en række offentlige kilder, og hver kilde har sine egne vilkår. Se [datagrundlag.dk/om](https://datagrundlag.dk/om/), før du bruger data kommercielt. Datagrundlag.dk er en høstet kopi og ikke den officielle kilde. Brug myndighedernes egne tjenester, når en opgave kræver juridisk gyldige data.

## Fejl og forslag

Opret en sag under [Issues](https://github.com/Ali-shahri/qgis-datagrundlag-browser/issues).

## Licens

GNU General Public License v2.0 eller nyere. Se [LICENSE](LICENSE).
