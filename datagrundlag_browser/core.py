# -*- coding: utf-8 -*-
# Datagrundlag Browser – QGIS-plugin til datagrundlag.dk
# Copyright (C) 2026 Ali Shahri
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version. See the LICENSE file.
"""Kerne-logik: katalog, datasæt-info og lag for datagrundlag.dk."""

import json
from urllib.parse import urljoin

BASE = "https://datagrundlag.s3.eu-west-1.amazonaws.com/filer/dk/"
CATALOG_URL = BASE + "catalog.json"
LAYER_PROP = "datagrundlag/collection"   # gemmes på laget, så det kan opdateres
DATE_PROP = "datagrundlag/pinned_date"   # tom = følg nyeste
COPY_PROP = "datagrundlag/copy"          # "1" = fast kopi (kortudsnit), opdateres ikke
GROUP_NAME = "Datagrundlag"

LARGE_ROWS = 250_000        # over dette spørger vi, om man vil hente et kortudsnit
GUARD_SCALE = 50_000        # store lag vises først, når man er zoomet ind til 1:50.000
MAX_EXTENT_FEATURES = 300_000

# Tabeller uden geometri, men med en koordinat-kolonne (WKT-punkt i EPSG:25832)
# og de mest brugte kolonner, så der hentes så lidt som muligt.
POINT_TABLES = {
    "bbr.bygning": "byg404koordinat",
    "bbr.tekniskanlaeg": "tek109koordinat",
}
POINT_COLUMNS = {   # hver ekstra kolonne koster et par sekunders hentning – derfor kun de vigtigste
    "bbr.bygning": [
        "kommunekode", "status", "byg021bygningensanvendelse", "byg026opførelsesår",
        "byg038samletbygningsareal", "byg039bygningenssamledeboligareal", "byg054antaletager",
        "byg056varmeinstallation", "byg032ydervæggensmateriale"],
    "bbr.tekniskanlaeg": [
        "kommunekode", "status", "tek020klassifikation", "tek024etableringsår", "tek032størrelse",
        "tek036rumfang", "tek039effekt", "tek068materiale"],
}
# Store id- og systemkolonner, der springes over, når tabeller laves til punkter
POINT_SKIP_PREFIXES = ("datafordeler", "id_", "gid", "grund", "husnummer", "jordstykke",
                       "bygning", "ejerlejlighed", "virkning", "registrering",
                       "forretnings", "status_", "objectid")
# Tunge kolonner med få nyttige oplysninger – springes over for at hente mindre
POINT_SKIP_PARTS = ("revisionsdato", "kildetil", "kvalitetaf", "supplerendeoplysning", "koordinatsystem",
                    "opdateringstid", "importsequence")


# ---------------------------------------------------------------------------
# Netværk (blokerende – kun til korte opslag ved klik på "Tilføj")
# ---------------------------------------------------------------------------

def _default_fetch(url):
    """Hent JSON via QGIS' netværk (respekterer QGIS' proxy-indstillinger)."""
    from qgis.core import QgsNetworkAccessManager
    from qgis.PyQt.QtCore import QUrl
    from qgis.PyQt.QtNetwork import QNetworkRequest

    if not url.startswith("https://"):
        raise ValueError(f"Kun https-adresser er tilladt: {url}")
    reply = QgsNetworkAccessManager.instance().blockingGet(QNetworkRequest(QUrl(url)))
    if reply.error():
        raise IOError(f"{url}: {reply.errorString()}")
    return json.loads(bytes(reply.content()).decode("utf-8"))


# ---------------------------------------------------------------------------
# Katalog og navne
# ---------------------------------------------------------------------------

def collection_dir(collection_id):
    """'dagi.kommuneinddeling' eller 'dagi/kommuneinddeling' -> mappe-URL."""
    schema, rel = collection_id.replace("/", ".").split(".", 1)
    return f"{BASE}schema={schema}/relation={rel}/"


def parse_catalog(cat):
    """catalog.json -> [(id, titel), ...]."""
    out = []
    for link in cat.get("links", []):
        if link.get("rel") != "child":
            continue
        parts = link["href"].strip("./").split("/")   # schema=bbr/relation=bygning/collection.json
        schema = parts[0].split("=", 1)[1]
        rel = parts[1].split("=", 1)[1]
        out.append((f"{schema}.{rel}", link.get("title", "")))
    return out


def list_datasets(fetch=_default_fetch):
    return parse_catalog(fetch(CATALOG_URL))


SOURCE_LABELS = {
    "bbr": "BBR – bygninger og boliger",
    "cvr": "CVR – virksomheder",
    "dagi": "DAGI – administrative grænser",
    "danmarksarealinformation": "Danmarks Arealinformation",
    "dar": "DAR – adresser",
    "dkjord": "Jordforurening",
    "geodanmark": "GeoDanmark",
    "geofa": "GeoFA – kommunale fagdata",
    "geus": "Jupiter – boringer (GEUS)",
    "grukos": "GRUKOS – grundvand",
    "jordbrugsanalyser": "Jordbrugsanalyser",
    "kulturarvsstyrelsen": "Kulturarv",
    "kystatlas": "Kystatlas",
    "landbrugsdrift": "Landbrugsdrift",
    "matrikel": "Matriklen",
    "naturdatabasen": "Naturdatabasen",
    "plandatadk": "Plandata.dk – planer",
    "puls": "PULS – miljøtilsyn",
    "redningsnumre": "Redningsnumre",
    "stednavne": "Stednavne",
    "vejdirektoratet": "Vejdirektoratet",
}

# Tema-visning: hvilke kilder hører til hvilket emne – og temaets farve på kortet
THEMES = [
    ("Ejendomme, adresser og virksomheder", ("bbr", "dar", "matrikel", "cvr"), "#d9822b", "ejendomme"),
    ("Natur og miljø", ("naturdatabasen", "danmarksarealinformation", "puls"), "#3a9d5d", "natur"),
    ("Jord og grundvand", ("dkjord", "geus", "grukos"), "#8c6d46", "jord"),
    ("Planer", ("plandatadk",), "#7b5ea7", "planer"),
    ("Kort, grænser og stednavne", ("geodanmark", "dagi", "stednavne"), "#4a6fa5", "kort"),
    ("Kyst og hav", ("kystatlas", "redningsnumre"), "#2a9fb8", "kyst"),
    ("Landbrug", ("landbrugsdrift", "jordbrugsanalyser"), "#a5a32b", "landbrug"),
    ("Kulturarv", ("kulturarvsstyrelsen",), "#b5485d", "kulturarv"),
    ("Veje og trafik", ("vejdirektoratet",), "#5f6b73", "veje"),
    ("Kommunale fagdata (GeoFA)", ("geofa",), "#c0507a", "geofa"),
]
_THEME_OF = {s: name for name, schemas, _c, _i in THEMES for s in schemas}
_COLOR_OF = {s: color for _n, schemas, color, _i in THEMES for s in schemas}
THEME_ICON = {name: ic for name, _s, _c, ic in THEMES}

# Startpakker: flere lag på én gang. (id, vis først ved indzoomning?) – øverste lag først.
PACKAGES = [
    ("basiskort", "Basiskort", "Et klassisk danmarkskort fra GeoDanmark i skærmkortets farver: "
     "kommunegrænser, jernbaner, veje, vandløb, bygninger, søer og skov.",
     [("dagi.kommuneinddeling", False), ("geodanmark.jernbane", False), ("geodanmark.vejmidte", True),
      ("geodanmark.vandloebsmidte", True), ("geodanmark.bygning", True), ("geodanmark.soe", False),
      ("geodanmark.skov", False)]),
    ("natur", "Natur og beskyttelse", "Natura 2000 (habitat- og fuglebeskyttelsesområder), fredninger, "
     "§ 3-natur og bygge- og beskyttelseslinjer omkring åer, søer og skove.",
     [("danmarksarealinformation.habitat_omr", False), ("danmarksarealinformation.fugle_bes_omr", False),
      ("danmarksarealinformation.fredede_omr", False), ("danmarksarealinformation.aa_bes_linjer", False),
      ("danmarksarealinformation.soe_bes_linjer", False), ("danmarksarealinformation.skovbyggelinjer", False),
      ("danmarksarealinformation.bes_naturtyper", True)]),
    ("vand", "Grundvand og jordforurening", "Boringer (Jupiter), boringsnære beskyttelsesområder, "
     "drikkevandsinteresser og V1/V2-kortlagt jordforurening.",
     [("geus.jupiter_boringer_ws", True), ("grukos.bnbo", False), ("dkjord.dkjord_v2", False),
      ("dkjord.dkjord_v1", False), ("grukos.drikkevandsinteresser", False)]),
    ("planer", "Planer", "Vedtagne lokalplaner og kommuneplanrammer, landzonetilladelser og kystnærhedszonen.",
     [("plandatadk.pdk_lokalplan_vedtaget_v", False), ("plandatadk.pdk_kommuneplanramme_vedtaget_v", False),
      ("plandatadk.pdk_landzonetilladelse_vedtaget_v", False),
      ("plandatadk.knz_kystnaerhedszone_polygon", False)]),
    ("kulturarv", "Kulturarv", "Fredede fortidsminder (punkter og flader), fortidsmindernes "
     "beskyttelseslinjer og fredede bygninger.",
     [("kulturarvsstyrelsen.fortidsminder_punkt_fredet", False), ("kulturarvsstyrelsen.bygning_fredede", False),
      ("kulturarvsstyrelsen.fundogfortidsminder_areal_fredet", False),
      ("kulturarvsstyrelsen.fundfortidsminder_areal_beskyttelse", False)]),
]
PACKAGE_PREFIX = "pakke:"


def schema_of(collection_id):
    return collection_id.split(".", 1)[0]


def theme_label(collection_id):
    return _THEME_OF.get(schema_of(collection_id), "Andet")


def theme_color(collection_id):
    return _COLOR_OF.get(schema_of(collection_id), "#4a6fa5")


def source_label(collection_id):
    return SOURCE_LABELS.get(schema_of(collection_id), schema_of(collection_id))


def short_source(collection_id):
    """'BBR – bygninger og boliger' -> 'BBR'."""
    return source_label(collection_id).split(" – ", 1)[0]


def short_title(title):
    """'BBR – Bygninger' -> 'Bygninger' (kilden står allerede i gruppen)."""
    return title.split(" – ", 1)[1] if " – " in title else title


def website_url(collection_id):
    """Datasættets side på datagrundlag.dk."""
    schema, rel = collection_id.split(".", 1)
    return f"https://datagrundlag.dk/data/{schema}/{rel}/"


def layer_name(collection_id, title, snapshot, suffix=""):
    """'Kommuner · DAGI (2026-10-27)' – kort, læsbart og med dato."""
    base = short_title(title or collection_id)
    extra = f", {suffix}" if suffix else ""
    return f"{base} · {short_source(collection_id)} ({snapshot}{extra})"


# ---------------------------------------------------------------------------
# Datasæt-info
# ---------------------------------------------------------------------------

def info_urls(collection_id):
    d = collection_dir(collection_id)
    return d + "collection.json", d + "latest.json"


def metadata_url(collection_id, latest):
    return urljoin(collection_dir(collection_id) + "latest.json",
                   latest["assets"]["metadata"]["href"])


def build_info(collection_id, coll, latest, meta):
    """Saml beskrivelse, snapshots, rækketal og type ét sted."""
    dates = sorted(
        lnk["href"].split("_gc2_snapshot_date=")[1].split("/")[0]
        for lnk in coll.get("links", []) if lnk.get("rel") == "item"
    )
    schema = (meta or {}).get("schema", [])
    geom_cols = [c["column_name"] for c in schema
                 if str(c.get("data_type", "")).startswith("geometry")]
    geom = None
    for col in schema:
        dt = str(col.get("data_type", "")).lower()
        if dt.startswith("geometry"):
            geom = ("polygon" if "polygon" in dt else "line" if "line" in dt
                    else "point" if "point" in dt else "mixed")
            break
    has_fgb = "flatgeobuf" in latest.get("assets", {})
    rows = (meta or {}).get("row_count")
    if rows == 0:
        kind = "empty"
    elif has_fgb:
        kind = "fgb"
    elif geom_cols:
        kind = "parquet"
    elif collection_id in POINT_TABLES:
        kind = "points"
        geom = "point"
    else:
        kind = "table"
    return {
        "title": coll.get("title", collection_id),
        "description": coll.get("description", ""),
        "snapshots": dates,
        "latest": latest.get("snapshot_date"),
        "rows": rows,
        "kind": kind,
        "geom": geom,
        "columns": [c["column_name"] for c in schema],
    }


def dataset_info(collection_id, fetch=_default_fetch):
    """Blokerende udgave (bruges i test og som reserve)."""
    coll_url, latest_url = info_urls(collection_id)
    coll, latest = fetch(coll_url), fetch(latest_url)
    meta = fetch(metadata_url(collection_id, latest))
    return build_info(collection_id, coll, latest, meta)


KIND_TEXT = {
    "fgb": "Kortlag",
    "parquet": "Kortlag (GeoParquet – kræver Parquet-understøttelse i QGIS)",
    "points": "Tabel med koordinater – kan vises som punkter for dit kortudsnit",
    "table": "Tabel uden geometri (kræver Parquet-understøttelse i QGIS)",
    "empty": "Tomt datasæt – der er ingen data endnu",
}


_PARQUET = None


def has_parquet():
    """Kan denne QGIS læse GeoParquet? (Kræver GDAL med Parquet-driver.)"""
    global _PARQUET
    if _PARQUET is None:
        try:
            from osgeo import ogr
            _PARQUET = ogr.GetDriverByName("Parquet") is not None
        except ImportError:
            _PARQUET = False
    return _PARQUET


def needs_parquet(info):
    return bool(info) and info.get("kind") in ("parquet", "points", "table")


def is_large(info):
    return bool(info and (info.get("rows") or 0) >= LARGE_ROWS
                and info.get("kind") in ("fgb", "parquet"))


def fmt_rows(n):
    if n is None:
        return "ukendt antal rækker"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} mio. rækker".replace(".", ",")
    return f"{n:,} rækker".replace(",", ".")


# ---------------------------------------------------------------------------
# Filer og snapshots
# ---------------------------------------------------------------------------

def resolve(collection_id, date=None, fetch=_default_fetch):
    """
    Find fil-URL'er for et datasæt.
    date=None -> nyeste snapshot (latest.json)
    date='YYYY-MM-DD' -> nyeste snapshot på eller før datoen
    Returnerer dict: snapshot_date, fgb (eller None), parquet
    """
    d = collection_dir(collection_id)
    if date is None:
        base = d + "latest.json"
        meta = fetch(base)
        assets, snap = meta["assets"], meta["snapshot_date"]
    else:
        coll = fetch(d + "collection.json")
        items = [lnk["href"] for lnk in coll["links"] if lnk.get("rel") == "item"]
        dated = sorted((h.split("_gc2_snapshot_date=")[1].split("/")[0], h) for h in items)
        valid = [x for x in dated if x[0] <= date]
        if not valid:
            first = dated[0][0] if dated else "?"
            raise ValueError(f"Der er ingen data på eller før {date}. De første data er fra {first}.")
        snap, href = valid[-1]
        base = urljoin(d + "collection.json", href)
        assets = fetch(base)["assets"]
    fgb = assets.get("flatgeobuf")
    return {
        "snapshot_date": snap,
        "fgb": urljoin(base, fgb["href"]) if fgb else None,
        "parquet": urljoin(base, assets["data"]["href"]),
    }


def gdal_source(urls):
    """GDAL-sti: FlatGeobuf hvis muligt (rumligt indeks), ellers GeoParquet."""
    return "/vsicurl/" + (urls["fgb"] or urls["parquet"])


# ---------------------------------------------------------------------------
# Lag: gruppe, stil og metadata
# ---------------------------------------------------------------------------

def geometry_types():
    """(polygon, linje, punkt) – virker i både QGIS 3.28+ og QGIS 4."""
    from qgis.core import Qgis, QgsWkbTypes
    gt = getattr(Qgis, "GeometryType", None)
    if gt is not None:
        return gt.Polygon, gt.Line, gt.Point
    return (QgsWkbTypes.GeometryType.PolygonGeometry, QgsWkbTypes.GeometryType.LineGeometry,
            QgsWkbTypes.GeometryType.PointGeometry)


def set_metadata(lyr, collection_id, info):
    """Beskrivelse og kilde ind i lagets metadata (Egenskaber → Metadata)."""
    from qgis.core import QgsAbstractMetadataBase
    md = lyr.metadata()
    if info:
        md.setTitle(info.get("title") or collection_id)
        md.setAbstract(info.get("description") or "")
    md.setIdentifier(collection_id)
    md.setRights([f"Kilde: {source_label(collection_id)} via datagrundlag.dk. "
                  "Hver kilde har sine egne vilkår – se https://datagrundlag.dk/om/"])
    md.addLink(QgsAbstractMetadataBase.Link("datagrundlag.dk", "WWW:LINK", website_url(collection_id)))
    lyr.setMetadata(md)


def project_group(subgroup=None):
    """Gruppen 'Datagrundlag' (og evt. en undergruppe) i lagpanelet."""
    from qgis.core import QgsProject
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup(GROUP_NAME) or root.insertGroup(0, GROUP_NAME)
    group.setExpanded(True)
    if subgroup:
        group = group.findGroup(subgroup) or group.insertGroup(0, subgroup)
        group.setExpanded(True)
    return group


def add_to_project(lyr, group=None, position=0):
    """Læg laget i gruppen 'Datagrundlag'."""
    from qgis.core import QgsProject
    group = group or project_group()
    QgsProject.instance().addMapLayer(lyr, False)
    group.insertLayer(position, lyr)
    return lyr


def finish_layer(lyr, collection_id, info, date=None, copy=False, group=None, position=0):
    lyr.setCustomProperty(LAYER_PROP, collection_id)
    lyr.setCustomProperty(DATE_PROP, date or "")
    lyr.setCustomProperty(COPY_PROP, "1" if copy else "")
    from . import symbology
    symbology.style_layer(lyr, collection_id, (info or {}).get("title", ""))
    set_metadata(lyr, collection_id, info)
    return add_to_project(lyr, group, position)


def add_layer(collection_id, date=None, title=None, info=None, guard=False, group=None, position=0):
    """Tilføj hele datasættet som et 'streamet' lag (data hentes efter behov)."""
    from qgis.core import QgsVectorLayer
    urls = resolve(collection_id, date)
    name = layer_name(collection_id, title, urls["snapshot_date"])
    lyr = QgsVectorLayer(gdal_source(urls), name, "ogr")
    if not lyr.isValid():
        hint = "" if urls["fgb"] else (" – QGIS kunne ikke læse GeoParquet-filen. Det kræver en QGIS "
                                       "med Parquet-understøttelse (fx QGIS 3.34+ fra OSGeo4W).")
        raise RuntimeError(f"Kunne ikke åbne {short_title(title or collection_id)}{hint}")
    if guard and lyr.isSpatial():
        lyr.setScaleBasedVisibility(True)
        lyr.setMinimumScale(GUARD_SCALE)    # mest udzoomede skala, hvor laget vises
    return finish_layer(lyr, collection_id, info, date, group=group, position=position)


def add_package(key, titles, on_progress=None):
    """Tilføj en startpakke som undergruppe. Returnerer (tilføjede lag, fejl)."""
    pkg = next(p for p in PACKAGES if p[0] == key)
    group = project_group(pkg[1])
    added, errors = [], []
    for n, (cid, guard) in enumerate(pkg[3]):
        if on_progress:
            on_progress(n, len(pkg[3]), titles.get(cid, cid))
        try:
            info = {"title": titles.get(cid, cid), "description": ""}
            added.append(add_layer(cid, None, titles.get(cid, cid), info, guard=guard,
                                   group=group, position=len(added)))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{short_title(titles.get(cid, cid))}: {e}")
    return added, errors


def refresh_all():
    """Peg alle ikke-fastlåste datagrundlag-lag på nyeste snapshot."""
    from qgis.core import QgsProject
    changed = []
    for lyr in QgsProject.instance().mapLayers().values():
        cid = lyr.customProperty(LAYER_PROP)
        if not cid or lyr.customProperty(DATE_PROP) or lyr.customProperty(COPY_PROP):
            continue
        urls = resolve(cid)
        src = gdal_source(urls)
        if lyr.source() != src:
            base_name = lyr.name().rsplit(" (", 1)[0]
            lyr.setDataSource(src, f"{base_name} ({urls['snapshot_date']})", "ogr")
            changed.append(cid)
    return changed
