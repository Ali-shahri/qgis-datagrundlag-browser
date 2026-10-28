# -*- coding: utf-8 -*-
# Datagrundlag Browser – QGIS-plugin til datagrundlag.dk
# Copyright (C) 2026 Ali Shahri
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version. See the LICENSE file.
"""Kartografi: lagene får farver og symboler, som danske kortbrugere kender.

Rækkefølge:
  1. Officielle QML-stilarter, hvor de findes (GeoFA – fra GeoDanmarkGeoFA/QGIS_GeoFA, GPL-2).
  2. Klimadatastyrelsens skærmkort-farver for GeoDanmark-objekter
     (SDFIdk/vector_tiles_assets, MIT-licens): vand er blå, skov grøn, bygninger laks osv.
  3. Faste regler for andre kendte datasæt: grænser vises kun som omrids, Natura 2000 med
     skravering, jordforurening i orange/rød, forslag med stiplet kant osv.
  4. Ellers temaets farve.
"""

import os
import re

from . import core

STYLE_DIR = os.path.join(os.path.dirname(__file__), "styles")
GEOFA_DIR = os.path.join(STYLE_DIR, "geofa")
GEOFA_SYMBOLS = os.path.join(GEOFA_DIR, "symboler")

OFFICIAL_QML = {
    "geofa.t_5800_fac_pkt": "Friluftsliv faciliteter, punkter.qml",
    "geofa.t_5801_fac_fl": "Friluftsliv faciliteter, flader.qml",
    "geofa.t_5802_fac_li": "Friluftsliv faciliteter, linjer.qml",
    "geofa.t_5607_ladefacilitet": "Ladefaciliteter.qml",
    "geofa.t_5608_cykelkrydspunkter": "Cykelknudepunkter.qml",
    "geofa.t_5609_cykelkrydspunktsstraekninger": "Cykelknudepunktsstrækninger.qml",
    "geofa.t_5710_born_skole_dis": "Skoledistrikter.qml",
    "geofa.t_5711_and_dis": "Andre Distrikter.qml",
    "geofa.t_5712_plej_aeldr_dis": "Pleje- og ældredistrikter.qml",
    "geofa.t_5713_prog_stat_dis": "Prognose- og statistik distrikter.qml",
}
# Et symbol, som GeoFA-stilen henviser til, men som mangler i GeoFA's repo
SVG_FIX = {"Ladefaciliteter/LADESTATION_BIL.svg": "Ladefaciliteter/Ladefacilitet_bil.svg"}

# ---------------------------------------------------------------------------
# Stil-specifikationer
#   fill/outline: farver · alpha: fyldets gennemsigtighed (0-255) · width: kantbredde (mm)
#   brush: "solid", "b_diagonal", "f_diagonal", "no" · dash: stiplet kant/linje
#   label: feltnavn til etiket (kun hvis feltet findes)
# ---------------------------------------------------------------------------
WATER = dict(fill="#C2EBFF", outline="#6ED0FA", alpha=255, width=0.3, line="#3FA9E0", lwidth=0.6)
SEA = dict(fill="#DEEDFF", outline="#9CC8F0", alpha=255, width=0.3)
FOREST = dict(fill="#94D19E", outline="#5BA86A", alpha=255, width=0.25, point="#3E8E50")
GREEN_AREA = dict(fill="#94D1A1", outline="#5BA86A", alpha=255, width=0.25)
HEATH = dict(fill="#FFE6E6", outline="#E3A6A6", alpha=255, width=0.25)
SAND = dict(fill="#F4F4D1", outline="#D6D69A", alpha=255, width=0.25)
WETLAND = dict(fill="#CFE8E0", outline="#6FB9A5", alpha=255, width=0.25)
BUILDING = dict(fill="#FFB18C", outline="#D9805A", alpha=255, width=0.2, point="#D9805A")
BUILT_UP = dict(fill="#F7D9B8", outline="#E0B48A", alpha=255, width=0.25)
TECHNICAL = dict(fill="#EEEEEE", outline="#BDBDBD", alpha=255, width=0.25)
ROAD = dict(line="#E8A35E", lwidth=0.35, outline="#E39A4F", fill="#FAC79B", alpha=255, width=0.3)
ROAD_EDGE = dict(line="#B9B9B9", lwidth=0.25)
RAIL = dict(line="#6E6E6E", lwidth=0.7)
POWER = dict(line="#5A5A5A", lwidth=0.4, dash=True)
PATH = dict(line="#8C8C8C", lwidth=0.4, dash=True)

MUNICIPALITY = dict(brush="no", outline="#B0279B", width=0.7, label="navn", label_color="#B0279B")
BOUNDARY = dict(brush="no", outline="#7A5C9E", width=0.6, dash=True, label="navn")
BOUNDARY_STRONG = dict(brush="no", outline="#5B3F80", width=1.0, label="navn")
PARCEL = dict(brush="no", outline="#E0473C", width=0.25, line="#E0473C", lwidth=0.25, point="#E0473C")

NATURA_HAB = dict(fill="#3A9D5D", brush="b_diagonal", outline="#2E7D4A", width=0.5)
NATURA_BIRD = dict(fill="#3D7FC1", brush="f_diagonal", outline="#2F6497", width=0.5)
RAMSAR = dict(fill="#2A9FB8", brush="b_diagonal", outline="#1F7A8C", width=0.5)
PROTECTED_NATURE = dict(fill="#B7DFA5", outline="#4E9A3A", alpha=170, width=0.3)
PRESERVATION = dict(fill="#8E5BA8", brush="b_diagonal", outline="#6E3F88", width=0.5)
BUFFER_WATER = dict(fill="#3FA9E0", brush="f_diagonal", outline="#3FA9E0", width=0.3, dash=True)
BUFFER_FOREST = dict(fill="#3E8E50", brush="f_diagonal", outline="#3E8E50", width=0.3, dash=True)
BUFFER_OTHER = dict(fill="#8E5BA8", brush="f_diagonal", outline="#8E5BA8", width=0.3, dash=True)

SOIL_V1 = dict(fill="#F6B44B", outline="#D98A1C", alpha=170, width=0.3)
SOIL_V2 = dict(fill="#E34A33", outline="#B30000", alpha=170, width=0.3)
SOIL_OTHER = dict(fill="#FDE38A", outline="#D9B43A", alpha=150, width=0.3)
SOIL_GONE = dict(fill="#BDBDBD", outline="#8C8C8C", alpha=120, width=0.3)
GROUNDWATER = dict(fill="#9ECAE1", outline="#3182BD", alpha=140, width=0.35, point="#3182BD")
RAW_MATERIAL = dict(fill="#D2B48C", outline="#9C7A4E", alpha=170, width=0.3)

PLAN = dict(fill="#7B5EA7", outline="#5E3F8F", alpha=40, width=0.45)
PLAN_DRAFT = dict(fill="#7B5EA7", outline="#7B5EA7", alpha=25, width=0.45, dash=True)
PLAN_CANCELLED = dict(fill="#9E9E9E", outline="#7A7A7A", alpha=30, width=0.35, dash=True)
COAST_ZONE = dict(brush="no", outline="#2A9FB8", width=0.6, dash=True)

HERITAGE = dict(fill="#B5485D", outline="#8E2F42", alpha=150, width=0.35, point="#B5485D")
HERITAGE_SOFT = dict(fill="#E7A3B1", outline="#B5485D", alpha=150, width=0.3, point="#E7A3B1")

# GeoDanmark: præcise id'er → skærmkort-farver
GEODANMARK = {
    "soe": WATER, "bassin": WATER, "vandloebsmidte": WATER, "vandloebskant": WATER,
    "afvandingsgroeft": WATER, "vandknude": WATER, "vandhaendelse": WATER, "kyst": WATER,
    "skov": FOREST, "kratbevoksning": FOREST, "traegruppe": FOREST, "trae": FOREST, "hegn": FOREST,
    "hede": HEATH, "sandklit": SAND, "vaadomraade": WETLAND,
    "rekreativtomraade": GREEN_AREA, "begravelsesomraade": GREEN_AREA, "sportsbane": GREEN_AREA,
    "gartneri": GREEN_AREA,
    "bygning": BUILDING, "bygvaerk": BUILDING,
    "bykerne": BUILT_UP, "hoejbebyggelse": BUILT_UP, "lavbebyggelse": BUILT_UP, "erhverv": BUILT_UP,
    "tekniskareal": TECHNICAL, "tekniskanlaegflade": TECHNICAL, "startbane": TECHNICAL,
    "parkering": TECHNICAL, "plads": TECHNICAL, "havn": TECHNICAL, "raastofomraade": RAW_MATERIAL,
    "vejmidte": ROAD, "vejkant": ROAD_EDGE, "helle": ROAD_EDGE, "chikane": ROAD_EDGE,
    "jernbane": RAIL, "togstation": RAIL, "hoejspaendingsledning": POWER,
}

# Andre datasæt: (nøgleord i id eller titel, stil) – første match vinder
KEYWORD_RULES = [
    (("dagi.kommuneinddeling", "matrikel.matrikelkommune", "plandatadk.kommune",
      "geodanmark.kommuneomraade"), MUNICIPALITY),
    (("dagi.regionsinddeling", "dagi.danmark", "matrikel.matrikelregion"), BOUNDARY_STRONG),
    (("dagi.", "matrikel.matrikelkommune", "matrikel.matrikelsogn", "plandatadk.kommune"), BOUNDARY),
    (("matrikel.ejerlav",), dict(BOUNDARY, outline="#C0392B")),
    (("matrikel.lodflade", "matrikel.jordstykke", "matrikel.matrikelskel", "matrikel.skelpunkt",
      "matrikel.centroide", "matrikel.samletfastejendom"), PARCEL),
    (("matrikel.optagetvej",), ROAD),
    (("fredskov", "jordstykketema", "temalinje", "skovbyggelinje"), BUFFER_FOREST),
    (("habitat_omr", "habitatområde"), NATURA_HAB),
    (("fugle_bes", "fuglebeskyttelse"), NATURA_BIRD),
    (("ramsar",), RAMSAR),
    (("natur_vildt_reservat",), RAMSAR),
    (("fredede_omr", "fredede områder"), PRESERVATION),
    (("bes_naturtyper", "§ 3", "naturtyper", "levesteder", "hnvskov"), PROTECTED_NATURE),
    (("aa_bes", "soe_bes", "åbeskyttelse", "søbeskyttelse", "bes_vandloeb"), BUFFER_WATER),
    (("kirkebyggelinje", "strandbeskyttelse", "klitfred", "beskyttelseslinjer"), BUFFER_OTHER),
    (("dkjord_v2",), SOIL_V2),
    (("dkjord_v1",), SOIL_V1),
    (("dkjord.uek", "dkjord.uik", "udgået"), SOIL_GONE),
    (("dkjord", "jordforurening", "paabud_jfl", "omr_klassificering"), SOIL_OTHER),
    (("grukos", "jupiter", "boring", "grundvand", "bnbo", "osd", "indvinding", "drikkevand"), GROUNDWATER),
    (("raastof", "råstof"), RAW_MATERIAL),
    (("kystnaerhedszone",), COAST_ZONE),
    (("aflyst",), PLAN_CANCELLED),
    (("forslag",), PLAN_DRAFT),
    (("plandatadk",), PLAN),
    (("fredede", "fortidsminde", "kulturarv", "bevaringsværdi (save 1", "fredningstatus_hoej"), HERITAGE),
    (("kulturarvsstyrelsen", "fbb"), HERITAGE_SOFT),
    (("soe", "sø", "vandløb", "vandloeb", "farvand", "havnebassin"), WATER),
    (("skov",), FOREST),
    (("cykel", "rednings_sti", "stier"), PATH),
    (("vejdirektoratet", "vej"), ROAD),
    (("bbr.bygning", "bygning"), BUILDING),
    (("distrikt", "afstemningsomraade", "postnummer"), BOUNDARY),
]


def _xml_attr(text):
    """Gør en sti sikker at sætte ind i en XML-attribut."""
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def spec_for(collection_id, title=""):
    schema, rel = collection_id.split(".", 1)
    if schema == "geodanmark" and rel in GEODANMARK:
        return GEODANMARK[rel]
    key = f"{collection_id} {title}".lower()
    for words, spec in KEYWORD_RULES:
        if any(w in key for w in words):
            return spec
    c = core.theme_color(collection_id)
    return dict(fill=c, outline=c, alpha=70, width=0.35, line=c, lwidth=0.5, point=c)


def _rgba(color, alpha=255):
    h = color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha}"


def apply_official(lyr, collection_id):
    """Indlæs officiel QML-stil, hvis der findes en, og den passer til lagets felter."""
    from qgis.core import QgsApplication, QgsRenderContext
    qml = OFFICIAL_QML.get(collection_id)
    if not qml:
        return False
    src = os.path.join(GEOFA_DIR, qml)
    try:
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False

    def fix(m):
        rel = SVG_FIX.get(m.group(1), m.group(1))
        path = os.path.join(GEOFA_SYMBOLS, *rel.split("/"))
        return f'value="{_xml_attr(path)}"' if os.path.exists(path) else m.group(0)

    text = re.sub(r'value="([^"]+\.svg)"', fix, text)
    out_dir = os.path.join(QgsApplication.qgisSettingsDirPath(), "datagrundlag_browser", "styles")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, qml)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    _msg, ok = lyr.loadNamedStyle(out)
    if not ok or lyr.renderer() is None:
        return False
    used = lyr.renderer().usedAttributes(QgsRenderContext())
    names = set(lyr.fields().names())
    return all(a in names for a in used)


def apply_spec(lyr, spec):
    from qgis.core import QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol, QgsSingleSymbolRenderer
    polygon, line, point = core.geometry_types()
    gtype = lyr.geometryType()
    dash = "dash" if spec.get("dash") else "solid"
    if gtype == polygon:
        brush = spec.get("brush", "solid")
        props = {"outline_color": _rgba(spec.get("outline", "#666666")),
                 "outline_width": str(spec.get("width", 0.3)), "outline_style": dash,
                 "style": brush}
        if brush == "no":
            props["color"] = "0,0,0,0"
        else:
            props["color"] = _rgba(spec.get("fill", "#999999"),
                                   255 if brush != "solid" else spec.get("alpha", 120))
        sym = QgsFillSymbol.createSimple(props)
    elif gtype == line:
        sym = QgsLineSymbol.createSimple({
            "color": _rgba(spec.get("line") or spec.get("outline", "#666666")),
            "width": str(spec.get("lwidth", spec.get("width", 0.5))), "line_style": dash})
    elif gtype == point:
        sym = QgsMarkerSymbol.createSimple({
            "name": "circle", "size": str(spec.get("psize", 2.2)),
            "color": _rgba(spec.get("point") or spec.get("outline") or spec.get("fill", "#666666"), 230),
            "outline_color": "255,255,255,230", "outline_width": "0.3"})
    else:
        return
    lyr.setRenderer(QgsSingleSymbolRenderer(sym))
    label = spec.get("label")
    if label and label in lyr.fields().names():
        _label(lyr, label, spec.get("label_color", "#4A3470"))


def _label(lyr, field, color):
    from qgis.core import (QgsPalLayerSettings, QgsTextBufferSettings, QgsTextFormat,
                           QgsVectorLayerSimpleLabeling)
    from qgis.PyQt.QtGui import QColor
    fmt = QgsTextFormat()
    fmt.setSize(8)
    fmt.setColor(QColor(color))
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    buf.setColor(QColor("white"))
    fmt.setBuffer(buf)
    pal = QgsPalLayerSettings()
    pal.fieldName = field
    pal.setFormat(fmt)
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    lyr.setLabelsEnabled(True)


def style_layer(lyr, collection_id, title=""):
    """Giv laget en genkendelig stil. Returnerer 'official' eller 'standard'."""
    if not lyr.isSpatial():
        return None
    if apply_official(lyr, collection_id):
        return "official"
    apply_spec(lyr, spec_for(collection_id, title))
    return "standard"
