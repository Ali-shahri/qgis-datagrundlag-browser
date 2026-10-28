# -*- coding: utf-8 -*-
# Datagrundlag Browser – QGIS-plugin til datagrundlag.dk
# Copyright (C) 2026 Ali Shahri
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version. See the LICENSE file.
"""Baggrundsopgaver: kopiér et kortudsnit, og lav tabeller med koordinater om til punkter."""

from qgis.core import (Qgis, QgsFeature, QgsFeatureRequest, QgsField, QgsGeometry, QgsPointXY,
                       QgsTask, QgsVectorLayer, QgsWkbTypes)

from . import core


def _wkb(name):
    """Qgis.WkbType.X (QGIS 3.30+/4) eller QgsWkbTypes.X (ældre)."""
    enum = getattr(Qgis, "WkbType", None)
    return getattr(enum, name) if enum is not None else getattr(QgsWkbTypes, name)


def _field(name, kind):
    """QgsField der virker i både QGIS 3 (QVariant) og QGIS 4 (QMetaType)."""
    try:
        from qgis.PyQt.QtCore import QMetaType
        types = {"int": QMetaType.Type.Int, "int8": QMetaType.Type.LongLong,
                 "double": QMetaType.Type.Double, "string": QMetaType.Type.QString}
        return QgsField(name, types[kind])
    except (ImportError, AttributeError, TypeError):
        from qgis.PyQt.QtCore import QVariant
        types = {"int": QVariant.Int, "int8": QVariant.LongLong,
                 "double": QVariant.Double, "string": QVariant.String}
        return QgsField(name, types[kind])


def memory_layer(name, wkb_type, crs_authid, fields):
    lyr = QgsVectorLayer(f"{QgsWkbTypes.displayString(wkb_type)}?crs={crs_authid}", name, "memory")
    lyr.dataProvider().addAttributes(fields)
    lyr.updateFields()
    return lyr


class ExtentCopyTask(QgsTask):
    """Hent kun features inden for kortudsnittet og læg dem i et lokalt lag."""

    def __init__(self, description, source, extent, on_done):
        super().__init__(description)
        self.source, self.extent, self.on_done = source, extent, on_done
        self.features, self.fields, self.wkb, self.crs, self.error = [], None, None, None, None

    def run(self):
        lyr = QgsVectorLayer(self.source, "udsnit", "ogr")
        if not lyr.isValid():
            self.error = "Kunne ikke åbne datasættet."
            return False
        self.fields, self.wkb, self.crs = lyr.fields(), lyr.wkbType(), lyr.crs().authid()
        req = QgsFeatureRequest().setFilterRect(self.extent)
        for f in lyr.getFeatures(req):
            if self.isCanceled():
                return False
            self.features.append(QgsFeature(f))
            n = len(self.features)
            if n > core.MAX_EXTENT_FEATURES:
                self.error = (f"Der er mere end {core.MAX_EXTENT_FEATURES:,} objekter i kortudsnittet. "
                              "Zoom længere ind og prøv igen.").replace(",", ".")
                return False
            if n % 5000 == 0:
                self.setProgress(min(95, n / 1000))
        if self.wkb in (_wkb("Unknown"), _wkb("NoGeometry")) and self.features:
            first = next((f for f in self.features if f.hasGeometry()), None)
            if first:
                self.wkb = QgsWkbTypes.multiType(first.geometry().wkbType())
        if QgsWkbTypes.isMultiType(self.wkb):
            for f in self.features:
                if f.hasGeometry() and not f.geometry().isMultipart():
                    g = f.geometry()
                    g.convertToMultiType()
                    f.setGeometry(g)
        return True

    def finished(self, ok):
        self.on_done(self, ok)

    def build_layer(self, name):
        lyr = memory_layer(name, self.wkb, self.crs, self.fields.toList())
        lyr.dataProvider().addFeatures(self.features)
        lyr.updateExtents()
        return lyr


class PointsTask(QgsTask):
    """Læs en Parquet-tabel med WKT-koordinater og lav punkter for kortudsnittet.

    Kun de nødvendige kolonner hentes (store id-kolonner springes over), og filtreringen
    sker i baggrunden, så QGIS ikke fryser.
    """

    def __init__(self, description, parquet_url, coord_col, bbox, on_done, columns=None):
        super().__init__(description)
        self.url, self.coord, self.bbox, self.on_done = parquet_url, coord_col, bbox, on_done
        self.columns = columns
        self.rows, self.out_cols, self.col_kinds, self.error = [], [], {}, None

    def run(self):
        import numpy
        from osgeo import ogr
        ds = ogr.Open("/vsicurl/" + self.url)
        if ds is None:
            self.error = ("QGIS kunne ikke læse Parquet-filen. Det kræver en QGIS med "
                          "Parquet-understøttelse (fx QGIS 3.34+ fra OSGeo4W).")
            return False
        layer = ds.GetLayer(0)
        defn = layer.GetLayerDefn()
        kinds, names = {}, []
        for i in range(defn.GetFieldCount()):
            fd = defn.GetFieldDefn(i)
            names.append(fd.GetName())
            kinds[fd.GetName()] = {ogr.OFTInteger: "int", ogr.OFTInteger64: "int8",
                                   ogr.OFTReal: "double"}.get(fd.GetType(), "string")
        if self.columns:
            keep = [n for n in names if n == self.coord or n in self.columns]
        else:
            keep = [n for n in names
                    if n == self.coord or not (n.lower().startswith(core.POINT_SKIP_PREFIXES)
                                               or any(s in n.lower() for s in core.POINT_SKIP_PARTS))]
        layer.SetIgnoredFields([n for n in names if n not in keep])
        self.out_cols = [n for n in keep if n != self.coord]
        self.col_kinds = {n: kinds[n] for n in self.out_cols}
        total = max(1, layer.GetFeatureCount())
        xmin, ymin, xmax, ymax = self.bbox

        def parse(v):
            if v is None:
                return None
            if isinstance(v, bytes):
                v = v.decode("utf-8", "ignore")
            a, b = v.find("("), v.find(")")
            if a < 0 or b < 0:
                return None
            parts = v[a + 1:b].split()
            if len(parts) != 2:
                return None
            try:
                return float(parts[0]), float(parts[1])
            except ValueError:
                return None

        def convert(v, kind):
            if v is None:
                return None
            if isinstance(v, bytes):
                return v.decode("utf-8", "ignore")
            if kind in ("int", "int8"):
                return int(v)
            if kind == "double":
                return float(v)
            return str(v)

        seen = 0
        if hasattr(layer, "GetArrowStreamAsNumPy"):
            stream = layer.GetArrowStreamAsNumPy(options=["MAX_FEATURES_IN_BATCH=65536"])
            for batch in stream:
                coords = batch[self.coord]
                hits = []
                for i in range(len(coords)):
                    xy = parse(coords[i])
                    if xy and xmin <= xy[0] <= xmax and ymin <= xy[1] <= ymax:
                        hits.append((i, xy))
                if hits:
                    cols = []
                    for c in self.out_cols:
                        arr = batch[c]
                        mask = numpy.ma.getmaskarray(arr) if isinstance(arr, numpy.ma.MaskedArray) else None
                        cols.append((arr.data if mask is not None else arr, mask, self.col_kinds[c]))
                    for i, xy in hits:
                        self.rows.append((xy, [None if (m is not None and m[i]) else convert(d[i], k)
                                               for d, m, k in cols]))
                seen += len(coords)
                self.setProgress(min(99, 100 * seen / total))
                if self.isCanceled():
                    return False
                if len(self.rows) > core.MAX_EXTENT_FEATURES:
                    self.error = "For mange punkter i kortudsnittet. Zoom længere ind og prøv igen."
                    return False
        else:   # ældre GDAL: langsommere, men virker
            for feat in layer:
                xy = parse(feat.GetField(self.coord))
                if xy and xmin <= xy[0] <= xmax and ymin <= xy[1] <= ymax:
                    self.rows.append((xy, [convert(feat.GetField(c), self.col_kinds[c])
                                           for c in self.out_cols]))
                seen += 1
                if seen % 20000 == 0:
                    self.setProgress(min(99, 100 * seen / total))
                    if self.isCanceled():
                        return False
        return True

    def finished(self, ok):
        self.on_done(self, ok)

    def build_layer(self, name):
        fields = [_field(c, self.col_kinds[c]) for c in self.out_cols]
        lyr = memory_layer(name, _wkb("Point"), "EPSG:25832", fields)
        flds = lyr.fields()
        feats = []
        for (x, y), attrs in self.rows:
            f = QgsFeature(flds)
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            f.setAttributes(attrs)
            feats.append(f)
        lyr.dataProvider().addFeatures(feats)
        lyr.updateExtents()
        return lyr
