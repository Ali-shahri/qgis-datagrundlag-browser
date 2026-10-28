# -*- coding: utf-8 -*-
# Datagrundlag Browser – QGIS-plugin til datagrundlag.dk
# Copyright (C) 2026 Ali Shahri
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version. See the LICENSE file.
"""Kerne-logik: katalog-opslag og lag-håndtering for datagrundlag.dk."""

import json
from urllib.parse import urljoin

BASE = "https://datagrundlag.s3.eu-west-1.amazonaws.com/filer/dk/"
LAYER_PROP = "datagrundlag/collection"   # gemmes på laget, så det kan opdateres
DATE_PROP = "datagrundlag/pinned_date"   # tom = følg nyeste


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


def collection_dir(collection_id):
    """'dagi.kommuneinddeling' eller 'dagi/kommuneinddeling' -> mappe-URL."""
    schema, rel = collection_id.replace("/", ".").split(".", 1)
    return f"{BASE}schema={schema}/relation={rel}/"


def list_datasets(fetch=_default_fetch):
    """Alle datasæt i kataloget: [(id, titel), ...]."""
    cat = fetch(BASE + "catalog.json")
    out = []
    for link in cat.get("links", []):
        if link.get("rel") != "child":
            continue
        parts = link["href"].strip("./").split("/")   # schema=bbr/relation=bygning/collection.json
        schema = parts[0].split("=", 1)[1]
        rel = parts[1].split("=", 1)[1]
        out.append((f"{schema}.{rel}", link.get("title", "")))
    return out


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
            raise ValueError(f"Intet snapshot på eller før {date} (første er {first})")
        snap, href = valid[-1]
        base = urljoin(d + "collection.json", href)
        assets = fetch(base)["assets"]
    fgb = assets.get("flatgeobuf")
    return {
        "snapshot_date": snap,
        "fgb": urljoin(base, fgb["href"]) if fgb else None,
        "parquet": urljoin(base, assets["data"]["href"]),
    }


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


# Tema-visning: hvilke kilder hører til hvilket emne
THEMES = [
    ("Ejendomme, adresser og virksomheder", ("bbr", "dar", "matrikel", "cvr")),
    ("Natur og miljø", ("naturdatabasen", "danmarksarealinformation", "puls")),
    ("Jord og grundvand", ("dkjord", "geus", "grukos")),
    ("Planer", ("plandatadk",)),
    ("Kort, grænser og stednavne", ("geodanmark", "dagi", "stednavne")),
    ("Kyst og hav", ("kystatlas", "redningsnumre")),
    ("Landbrug", ("landbrugsdrift", "jordbrugsanalyser")),
    ("Kulturarv", ("kulturarvsstyrelsen",)),
    ("Veje og trafik", ("vejdirektoratet",)),
    ("Kommunale fagdata (GeoFA)", ("geofa",)),
]
_THEME_OF = {s: name for name, schemas in THEMES for s in schemas}


def theme_label(collection_id):
    return _THEME_OF.get(collection_id.split(".", 1)[0], "Andet")


def website_url(collection_id):
    """Datasættets side på datagrundlag.dk."""
    schema, rel = collection_id.split(".", 1)
    return f"https://datagrundlag.dk/data/{schema}/{rel}/"


def source_label(collection_id):
    schema = collection_id.split(".", 1)[0]
    return SOURCE_LABELS.get(schema, schema)


def short_title(title):
    """'BBR – Bygninger' -> 'Bygninger' (kilden står allerede i gruppen)."""
    return title.split(" – ", 1)[1] if " – " in title else title


def dataset_info(collection_id, fetch=_default_fetch):
    """Beskrivelse, snapshots og om datasættet har geometri."""
    d = collection_dir(collection_id)
    coll = fetch(d + "collection.json")
    latest = fetch(d + "latest.json")
    dates = sorted(
        lnk["href"].split("_gc2_snapshot_date=")[1].split("/")[0]
        for lnk in coll.get("links", []) if lnk.get("rel") == "item"
    )
    return {
        "title": coll.get("title", collection_id),
        "description": coll.get("description", ""),
        "snapshots": dates,
        "latest": latest.get("snapshot_date"),
        "has_geometry": "flatgeobuf" in latest.get("assets", {}),
    }


def gdal_source(urls):
    """GDAL-sti: FlatGeobuf hvis muligt (rumligt indeks), ellers GeoParquet."""
    return "/vsicurl/" + (urls["fgb"] or urls["parquet"])


def add_layer(collection_id, date=None, title=None):
    """Tilføj et datasæt som lag i det aktuelle projekt."""
    from qgis.core import QgsProject, QgsVectorLayer
    urls = resolve(collection_id, date)
    name = f"{title or collection_id} ({urls['snapshot_date']})"
    lyr = QgsVectorLayer(gdal_source(urls), name, "ogr")
    if not lyr.isValid():
        hint = "" if urls["fgb"] else " – tabellen har ingen geometri og kræver GDAL med Parquet-driver"
        raise RuntimeError(f"Kunne ikke åbne {collection_id}{hint}")
    lyr.setCustomProperty(LAYER_PROP, collection_id)
    lyr.setCustomProperty(DATE_PROP, date or "")
    QgsProject.instance().addMapLayer(lyr)
    return lyr


def refresh_all():
    """Peg alle ikke-fastlåste datagrundlag-lag på nyeste snapshot."""
    from qgis.core import QgsProject
    changed = []
    for lyr in QgsProject.instance().mapLayers().values():
        cid = lyr.customProperty(LAYER_PROP)
        if not cid or lyr.customProperty(DATE_PROP):
            continue
        urls = resolve(cid)
        src = gdal_source(urls)
        if lyr.source() != src:
            base_name = lyr.name().rsplit(" (", 1)[0]
            lyr.setDataSource(src, f"{base_name} ({urls['snapshot_date']})", "ogr")
            changed.append(cid)
    return changed
