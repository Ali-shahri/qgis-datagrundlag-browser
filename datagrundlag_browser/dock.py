# -*- coding: utf-8 -*-
# Datagrundlag Browser – QGIS-plugin til datagrundlag.dk
# Copyright (C) 2026 Ali Shahri
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version. See the LICENSE file.
"""Panelet (dock widget) til Datagrundlag Browser."""

import json
import os
import time
from collections import defaultdict

from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsProject, QgsSettings)
from qgis.gui import QgsFilterLineEdit
from qgis.PyQt.QtCore import QDate, Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import (
    QApplication, QDateEdit, QDialog, QDialogButtonBox, QDockWidget, QFrame,
    QHBoxLayout, QLabel, QMenu, QMessageBox, QSizePolicy, QSplitter,
    QTextBrowser, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import core, net
from .tasks import ExtentCopyTask, PointsTask

try:   # Qt6 (QGIS 4): QAction/QActionGroup ligger i QtGui
    from qgis.PyQt.QtGui import QAction, QActionGroup
except ImportError:   # Qt5 (QGIS 3)
    from qgis.PyQt.QtWidgets import QAction, QActionGroup

ROLE = Qt.ItemDataRole.UserRole
SETTINGS = "datagrundlag_browser/"
MAX_RECENT = 8
CACHE_MAX_AGE = 24 * 3600
MAX_POINT_AREA_KM2 = 2500          # ca. 50 × 50 km
MODE_SOURCE, MODE_THEME = "source", "theme"
HELP_URL = "https://github.com/Ali-shahri/qgis-datagrundlag-browser#readme"
GEOM_ICON = {"polygon": "/mIconPolygonLayer.svg", "line": "/mIconLineLayer.svg",
             "point": "/mIconPointLayer.svg", "mixed": "/mIconGeometryCollectionLayer.svg"}


ICON_DIR = os.path.join(os.path.dirname(__file__), "icons")


def icon(name):
    return QgsApplication.getThemeIcon(name)


def own_icon(name):
    path = os.path.join(ICON_DIR, f"{name}.svg")
    return QIcon(path) if os.path.exists(path) else QIcon(os.path.join(ICON_DIR, "andet.svg"))


def is_package(cid):
    return cid.startswith(core.PACKAGE_PREFIX)


def _load_list(key):
    try:
        val = json.loads(QgsSettings().value(SETTINGS + key, "[]"))
        return [x for x in val if isinstance(x, str)]
    except (TypeError, ValueError):
        return []


def _save_list(key, values):
    QgsSettings().setValue(SETTINGS + key, json.dumps(values))


def _cache_path():
    return os.path.join(QgsApplication.qgisSettingsDirPath(), "datagrundlag_browser", "catalog.json")


class DatagrundlagDock(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Datagrundlag Browser", parent)
        self.iface = iface
        self.setObjectName("DatagrundlagBrowserDock")
        self._loaded = False
        self._loading = False
        self._datasets = []          # [(cid, title)]
        self._titles = {}            # cid -> title
        self._info = {}              # cid -> info (fra collection/latest/metadata)
        self._info_pending = set()
        self._groups = []            # [(label, total)] i samme rækkefølge som træet
        self._tasks = set()
        self._base_status = ""
        self.favorites = _load_list("favorites")
        self.recent = _load_list("recent")
        self.mode = QgsSettings().value(SETTINGS + "mode", MODE_SOURCE)
        self._build_ui()

    # ======================================================================
    # Layout
    # ======================================================================
    def _build_ui(self):
        root = QWidget()
        v = QVBoxLayout(root)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        # Søgning + "⋯"-menu
        top = QHBoxLayout()
        self.search = QgsFilterLineEdit()
        self.search.setShowSearchIcon(True)
        self.search.setPlaceholderText("Søg efter data, fx lokalplan, skov, bygninger …")
        top.addWidget(self.search, 1)
        self.btn_more = QToolButton()
        self.btn_more.setText("⋯")
        self.btn_more.setToolTip("Flere muligheder")
        self.btn_more.setAutoRaise(True)
        self.btn_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_more.setMenu(self._build_more_menu())
        top.addWidget(self.btn_more)
        v.addLayout(top)

        # Træ
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIndentation(14)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Infokort
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(8, 6, 8, 6)
        cv.setSpacing(4)
        head = QHBoxLayout()
        self.btn_toggle = QToolButton()
        self.btn_toggle.setAutoRaise(True)
        self.btn_toggle.setToolTip("Vis/skjul beskrivelse")
        head.addWidget(self.btn_toggle, 0, Qt.AlignmentFlag.AlignTop)
        self.info_title = QLabel("Vælg et datasæt")
        f = self.info_title.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.1)
        self.info_title.setFont(f)
        self.info_title.setWordWrap(True)
        head.addWidget(self.info_title, 1)
        self.btn_fav = QToolButton()
        self.btn_fav.setAutoRaise(True)
        self.btn_fav.setEnabled(False)
        f2 = self.btn_fav.font()
        f2.setPointSizeF(f2.pointSizeF() * 1.3)
        self.btn_fav.setFont(f2)
        head.addWidget(self.btn_fav, 0, Qt.AlignmentFlag.AlignTop)
        cv.addLayout(head)
        self.info_meta = QLabel("")
        self.info_meta.setWordWrap(True)
        self.info_meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.info_meta.setOpenExternalLinks(True)
        cv.addWidget(self.info_meta)
        self.info_note = QLabel("")
        self.info_note.setWordWrap(True)
        self.info_note.setStyleSheet("background: rgba(230,160,40,40); border-radius: 4px; padding: 4px 6px;")
        self.info_note.hide()
        cv.addWidget(self.info_note)
        self.info_desc = QTextBrowser()
        self.info_desc.setFrameShape(QFrame.Shape.NoFrame)
        self.info_desc.setOpenExternalLinks(True)
        self.info_desc.setPlaceholderText(
            "Klik på et datasæt for at se, hvad det indeholder.\n\n"
            "Tip: Dobbeltklik tilføjer det til kortet. Højreklik giver flere muligheder, "
            "og ☆ gemmer det som favorit.")
        cv.addWidget(self.info_desc, 1)
        self._set_desc_visible(QgsSettings().value(SETTINGS + "desc_visible", "1") == "1")
        self._set_fav_button(False)

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.tree)
        split.addWidget(card)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setChildrenCollapsible(False)
        v.addWidget(split, 1)

        # Hovedknap med lille menu
        self.btn_add = QToolButton()
        self.btn_add.setIcon(icon("/mActionAddLayer.svg"))
        self.btn_add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_add.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.btn_add.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_add.setMinimumHeight(34)
        fb = self.btn_add.font()
        fb.setBold(True)
        self.btn_add.setFont(fb)
        self.add_menu = QMenu(self.btn_add)
        self.act_full = self.add_menu.addAction(icon("/mActionAddLayer.svg"), "Tilføj hele datasættet")
        self.act_extent = self.add_menu.addAction(icon("/mActionZoomActual.svg"), "Tilføj kun mit kortudsnit")
        self.act_date = self.add_menu.addAction(icon("/mIconHistory.svg"), "Tilføj data fra en bestemt dato …")
        self.btn_add.setMenu(self.add_menu)
        v.addWidget(self.btn_add)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: palette(mid);")
        v.addWidget(self.status)
        self.setWidget(root)
        self._update_add_button(None)

        # Signaler
        self.search.valueChanged.connect(self._filter)
        self.tree.currentItemChanged.connect(self._on_select)
        self.tree.itemDoubleClicked.connect(self._on_double)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.btn_fav.clicked.connect(self._toggle_current_fav)
        self.btn_toggle.clicked.connect(lambda: self._set_desc_visible(not self.info_desc.isVisible()))
        self.btn_add.clicked.connect(self._add_default)
        self.act_full.triggered.connect(lambda _c=False: self._add_full())
        self.act_extent.triggered.connect(lambda _c=False: self._add_extent())
        self.act_date.triggered.connect(lambda _c=False: self._add_from_date())

    def _build_more_menu(self):
        m = QMenu(self)
        m.addSection("Gruppér efter")
        grp = QActionGroup(m)
        self.act_mode_source = QAction("Kilde (BBR, GeoDanmark …)", m, checkable=True)
        self.act_mode_theme = QAction("Tema (natur, planer, ejendomme …)", m, checkable=True)
        for a in (self.act_mode_source, self.act_mode_theme):
            grp.addAction(a)
            m.addAction(a)
        (self.act_mode_theme if self.mode == MODE_THEME else self.act_mode_source).setChecked(True)
        self.act_mode_source.triggered.connect(lambda _c=False: self._set_mode(MODE_SOURCE))
        self.act_mode_theme.triggered.connect(lambda _c=False: self._set_mode(MODE_THEME))
        m.addSeparator()
        m.addAction(icon("/mActionExpandTree.svg"), "Fold alle grupper ud").triggered.connect(
            lambda _c=False: self.tree.expandAll())
        m.addAction(icon("/mActionCollapseTree.svg"), "Fold alle grupper sammen").triggered.connect(
            lambda _c=False: self.tree.collapseAll())
        m.addSeparator()
        m.addAction(icon("/mActionReload.svg"), "Opdatér mine lag til nyeste data").triggered.connect(
            lambda _c=False: self._refresh())
        m.addAction(icon("/mActionRefresh.svg"), "Hent kataloget igen").triggered.connect(
            lambda _c=False: self.load_catalog(force=True))
        m.addSeparator()
        m.addAction(icon("/mActionHelpContents.svg"), "Hjælp og kildekode").triggered.connect(
            lambda _c=False: QDesktopServices.openUrl(QUrl(HELP_URL)))
        return m

    def _set_desc_visible(self, on):
        self.info_desc.setVisible(on)
        self.btn_toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        QgsSettings().setValue(SETTINGS + "desc_visible", "1" if on else "0")

    def _set_fav_button(self, is_fav):
        self.btn_fav.setText("★" if is_fav else "☆")
        self.btn_fav.setToolTip("Fjern fra favoritter" if is_fav else "Gem som favorit")

    # ======================================================================
    # Katalog (cache + baggrundshentning)
    # ======================================================================
    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded and not self._loading:
            self.load_catalog()

    def load_catalog(self, force=False):
        path = _cache_path()
        cached = None
        if not force and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    cached = json.load(fh)
            except (OSError, ValueError):
                cached = None
        if cached:
            self._apply_catalog(cached)
            if time.time() - os.path.getmtime(path) < CACHE_MAX_AGE:
                return
        if not self._loaded:
            self._show_placeholder("Henter kataloget fra datagrundlag.dk …")
        self._loading = True
        self.status.setText("Henter kataloget …" if force or not cached else self.status.text())
        net.get_json(core.CATALOG_URL, self._on_catalog)

    def _on_catalog(self, data, err):
        self._loading = False
        if err:
            if not self._loaded:
                self._show_placeholder("Kunne ikke hente kataloget. Tjek netforbindelsen og prøv igen "
                                       "via ⋯ → Hent kataloget igen.")
            self.status.setText(f"Kunne ikke hente kataloget: {err}")
            return
        try:
            os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
            with open(_cache_path(), "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        except OSError:
            pass
        self._apply_catalog(data)

    def _apply_catalog(self, cat):
        self._datasets = core.parse_catalog(cat)
        self._titles = dict(self._datasets)
        for key, name, _desc, _layers in core.PACKAGES:
            self._titles[core.PACKAGE_PREFIX + key] = name
        self._loaded = True
        sources = {core.source_label(cid) for cid, _ in self._datasets}
        self._base_status = f"{len(self._datasets)} datasæt fra {len(sources)} kilder"
        self.search.setPlaceholderText(f"Søg i {len(self._datasets)} datasæt, fx lokalplan, skov, bygninger …")
        self._build_tree()

    def _show_placeholder(self, text):
        self.tree.clear()
        self._groups = []
        it = QTreeWidgetItem([text])
        it.setFlags(Qt.ItemFlag.NoItemFlags)
        self.tree.addTopLevelItem(it)

    # ======================================================================
    # Træ
    # ======================================================================
    def _set_mode(self, mode):
        self.mode = mode
        QgsSettings().setValue(SETTINGS + "mode", mode)
        self._build_tree()

    def _item_icon(self, cid):
        info = self._info.get(cid)
        if not info:
            return None
        if info["kind"] == "empty":
            return icon("/mIconWarning.svg")
        if info["kind"] == "table":
            return icon("/mIconTableLayer.svg")
        return icon(GEOM_ICON.get(info.get("geom"), "/mIconVector.svg"))

    def _make_group(self, label, group_icon, entries):
        g = QTreeWidgetItem([label])
        g.setIcon(0, group_icon)
        g.setData(0, ROLE, None)
        g.setFlags(Qt.ItemFlag.ItemIsEnabled)
        fg = g.font(0)
        fg.setBold(True)
        g.setFont(0, fg)
        for cid, text in entries:
            c = QTreeWidgetItem([text])
            c.setData(0, ROLE, (cid, self._titles.get(cid, cid)))
            c.setToolTip(0, f"{self._titles.get(cid, cid)}\n{cid}")
            ic = own_icon("pakke") if is_package(cid) else self._item_icon(cid)
            if ic:
                c.setIcon(0, ic)
            g.addChild(c)
        self.tree.addTopLevelItem(g)
        self._groups.append((label, len(entries)))
        return g

    def _build_tree(self):
        if not self._loaded:
            return
        keep = self._selected()
        self.tree.blockSignals(True)
        self.tree.clear()
        self._groups = []
        theme_mode = self.mode == MODE_THEME

        self._make_group("Startpakker", own_icon("pakke"),
                         [(core.PACKAGE_PREFIX + key, name) for key, name, _d, _l in core.PACKAGES])
        favs = [c for c in self.favorites if c in self._titles]
        if favs:
            self._make_group("★ Favoritter", own_icon("favorit"),
                             [(c, self._titles[c]) for c in favs]).setExpanded(True)
        recent = [c for c in self.recent if c in self._titles]
        if recent:
            self._make_group("Senest tilføjet", own_icon("senest"), [(c, self._titles[c]) for c in recent])

        groups = defaultdict(list)
        group_of = core.theme_label if theme_mode else core.source_label
        for cid, _t in self._datasets:
            groups[group_of(cid)].append(cid)
        if theme_mode:
            order = [name for name, _s, _c in core.THEMES if name in groups]
            order += sorted(k for k in groups if k not in order)
        else:
            order = sorted(groups, key=str.lower)
        for label in order:
            entries = []
            for cid in groups[label]:
                t = self._titles.get(cid, cid)
                entries.append((cid, t if theme_mode else (core.short_title(t) or cid)))
            entries.sort(key=lambda x: x[1].lower())
            if theme_mode:
                gicon = own_icon(core.THEME_ICON.get(label, "andet"))
            else:
                gicon = own_icon(core.schema_of(groups[label][0]))
            self._make_group(label, gicon, entries)

        self.tree.blockSignals(False)
        self._filter(self.search.value())
        if keep:
            self._reselect(keep[0])

    def _reselect(self, cid):
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            for j in range(g.childCount()):
                c = g.child(j)
                if c.data(0, ROLE)[0] == cid and not c.isHidden():
                    g.setExpanded(True)
                    self.tree.setCurrentItem(c)
                    return

    def _filter(self, txt):
        if not self._groups:
            return
        t = (txt or "").strip().lower()
        shown = set()
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            label, total = self._groups[i]
            group_hit = bool(t) and t in label.lower()
            visible = 0
            for j in range(g.childCount()):
                c = g.child(j)
                cid, title = c.data(0, ROLE)
                hit = (not t or group_hit or t in title.lower() or t in cid.lower()
                       or t in core.source_label(cid).lower())
                c.setHidden(not hit)
                if hit:
                    visible += 1
                    shown.add(cid)
            g.setText(0, f"{label}  ({visible} af {total})" if t else f"{label}  ({total})")
            g.setHidden(visible == 0)
            if t:
                g.setExpanded(visible > 0)
            elif label.startswith("★"):
                g.setExpanded(True)
        if t and not shown:
            self.status.setText(f"Ingen datasæt matcher «{txt.strip()}». Prøv et andet ord.")
        else:
            self.status.setText(f"{len(shown)} datasæt matcher «{txt.strip()}»" if t else self._base_status)

    # ======================================================================
    # Valg og infokort (info hentes i baggrunden)
    # ======================================================================
    def _selected(self):
        it = self.tree.currentItem()
        return it.data(0, ROLE) if it else None

    def _on_select(self, cur, _prev):
        data = cur.data(0, ROLE) if cur else None
        self.btn_fav.setEnabled(bool(data))
        if not data:
            self.info_title.setText("Vælg et datasæt")
            self.info_meta.setText("")
            self.info_note.hide()
            self.info_desc.clear()
            self._set_fav_button(False)
            self._update_add_button(None)
            return
        cid, title = data
        if is_package(cid):
            self._show_package(cid)
            return
        self._set_fav_button(cid in self.favorites)
        self.info_title.setText(title or cid)
        if cid in self._info:
            self._show_info(cid)
        else:
            self.info_meta.setText("<span style='color:gray'>Henter information …</span>")
            self.info_note.hide()
            self.info_desc.clear()
            self._update_add_button(None, selected=True)
            self._fetch_info(cid)

    def _fetch_info(self, cid, then=None):
        if cid in self._info_pending:
            return
        self._info_pending.add(cid)
        coll_url, latest_url = core.info_urls(cid)

        def got_first(res, err):
            if err:
                return fail(err)
            latest = res[latest_url]
            try:
                murl = core.metadata_url(cid, latest)
            except KeyError:
                return finish(res[coll_url], latest, {})
            net.get_json(murl, lambda meta, e2: finish(res[coll_url], latest, meta or {}))

        def finish(coll, latest, meta):
            self._info_pending.discard(cid)
            self._info[cid] = core.build_info(cid, coll, latest, meta)
            self._set_item_icons(cid)
            if then:
                then()
            sel = self._selected()
            if sel and sel[0] == cid:
                self._show_info(cid)

        def fail(err):
            self._info_pending.discard(cid)
            sel = self._selected()
            if sel and sel[0] == cid:
                self.info_meta.setText("")
                self.info_desc.setPlainText(f"Kunne ikke hente information: {err}")
                self._update_add_button(None, selected=True)

        net.get_many([coll_url, latest_url], got_first)

    def _set_item_icons(self, cid):
        ic = self._item_icon(cid)
        if not ic:
            return
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            for j in range(g.childCount()):
                if g.child(j).data(0, ROLE)[0] == cid:
                    g.child(j).setIcon(0, ic)

    def _show_info(self, cid):
        info = self._info[cid]
        n = len(info["snapshots"])
        first = info["snapshots"][0] if n else "–"
        parts = [core.KIND_TEXT.get(info["kind"], "")]
        if info["kind"] != "empty":
            parts.append(core.fmt_rows(info["rows"]))
        self.info_meta.setText(
            f"{'  ·  '.join(p for p in parts if p)}<br>"
            f"Nyeste data: <b>{info['latest']}</b>  ·  historik siden {first} ({n} snapshots)<br>"
            f"<span style='color:gray'>{cid}</span>  ·  "
            f"<a href='{core.website_url(cid)}'>Se på datagrundlag.dk</a>")
        note = ""
        if core.needs_parquet(info) and not core.has_parquet():
            note = ("Din QGIS kan ikke læse GeoParquet, som dette datasæt kun findes i. "
                    "Det kræver QGIS 3.34+ med Parquet-understøttelse (fx installeret via OSGeo4W).")
        elif info["kind"] == "points":
            note = ("Tabellen har koordinater, men ingen geometri. Pluginet kan lave punkter for "
                    "dit kortudsnit. Det henter op til ca. 150 MB i baggrunden og tager typisk 1–2 minutter "
                    "– du kan arbejde videre imens.")
        elif core.is_large(info):
            note = ("Stort datasæt. Hent kun dit kortudsnit for at holde QGIS hurtig, "
                    "eller tilføj det hele – så vises det først, når du zoomer ind.")
        self.info_note.setText(note)
        self.info_note.setVisible(bool(note))
        self.info_desc.setPlainText(info["description"] or "Ingen beskrivelse.")
        self._update_add_button(info, selected=True)

    def _package(self, cid):
        key = cid[len(core.PACKAGE_PREFIX):]
        return next(p for p in core.PACKAGES if p[0] == key)

    def _show_package(self, cid):
        key, name, desc, layers = self._package(cid)
        self.btn_fav.setEnabled(False)
        self.info_title.setText(f"Startpakke: {name}")
        names = "".join(f"<li>{core.short_title(self._titles.get(c, c))}</li>" for c, _g in layers)
        self.info_meta.setText(f"{len(layers)} lag i deres egen gruppe, klar til brug<ul style='margin:2px 0 0 -20px'>"
                               f"{names}</ul>")
        self.info_note.hide()
        self.info_desc.setPlainText(desc + "\n\nStore lag (fx bygninger og veje) vises først, når du zoomer "
                                    "ind til 1:50.000 eller tættere, så QGIS forbliver hurtig.")
        self.btn_add.setText(f"  Tilføj pakken ({len(layers)} lag)")
        self.btn_add.setEnabled(True)
        self.btn_add.setToolTip("")
        for a in (self.act_full, self.act_extent, self.act_date):
            a.setEnabled(False)

    def _update_add_button(self, info, selected=False):
        b = self.btn_add
        can_full = can_extent = can_date = True
        if not selected:
            text, enabled, tip = "Tilføj til kortet", False, "Vælg et datasæt i listen"
            can_full = can_extent = can_date = False
        elif info is None:
            text, enabled, tip = "Tilføj til kortet", True, ""
        elif info["kind"] == "empty":
            text, enabled, tip = "Datasættet er tomt", False, "Der er ingen data i datasættet endnu"
            can_full = can_extent = can_date = False
        elif core.needs_parquet(info) and not core.has_parquet():
            text, enabled, tip = "Kræver Parquet-understøttelse", False, self.info_note.text()
            can_full = can_extent = can_date = False
        elif info["kind"] == "points":
            text, enabled, tip = "Vis som punkter for mit kortudsnit", True, ""
            can_full = False
        elif info["kind"] == "table":
            text, enabled, tip = "Tilføj tabel", True, "Tabellen har ingen geometri"
            can_extent = False
        elif core.is_large(info):
            text, enabled, tip = "Tilføj til kortet …", True, "Stort datasæt – du får et par valg"
        else:
            text, enabled, tip = "Tilføj til kortet", True, ""
        b.setText("  " + text)
        b.setEnabled(enabled)
        b.setToolTip(tip)
        self.act_full.setEnabled(can_full)
        self.act_extent.setEnabled(can_extent)
        self.act_date.setEnabled(can_date)

    def _on_double(self, item, _col):
        if item.data(0, ROLE) and self.btn_add.isEnabled():
            self._add_default()

    # ======================================================================
    # Favoritter, senest brugt og højrekliksmenu
    # ======================================================================
    def _toggle_fav(self, cid):
        if cid in self.favorites:
            self.favorites.remove(cid)
            msg = "Fjernet fra favoritter"
        else:
            self.favorites.append(cid)
            msg = "★ Gemt som favorit"
        _save_list("favorites", self.favorites)
        self._build_tree()
        self.status.setText(msg)

    def _toggle_current_fav(self):
        data = self._selected()
        if data:
            self._toggle_fav(data[0])

    def _remember(self, cid):
        self.recent = ([cid] + [c for c in self.recent if c != cid])[:MAX_RECENT]
        _save_list("recent", self.recent)

    def _context_menu(self, pos):
        item = self.tree.itemAt(pos)
        data = item.data(0, ROLE) if item else None
        if not data:
            return
        self.tree.setCurrentItem(item)
        if is_package(data[0]):
            m = QMenu(self.tree)
            a = m.addAction(own_icon("pakke"), self.btn_add.text().strip())
            a.triggered.connect(lambda _c=False: self._add_default())
            m.exec(self.tree.viewport().mapToGlobal(pos))
            return
        self._build_menu(data[0]).exec(self.tree.viewport().mapToGlobal(pos))

    def _build_menu(self, cid):
        m = QMenu(self.tree)

        def act(icon_name, text, slot, enabled=True):
            a = m.addAction(icon(icon_name), text)
            a.setEnabled(enabled)
            a.triggered.connect(lambda _checked=False: slot())

        act("/mActionAddLayer.svg", self.btn_add.text().strip(), self._add_default, self.btn_add.isEnabled())
        act("/mActionZoomActual.svg", "Tilføj kun mit kortudsnit", self._add_extent, self.act_extent.isEnabled())
        act("/mIconHistory.svg", "Tilføj data fra en bestemt dato …", self._add_from_date,
            self.act_date.isEnabled())
        m.addSeparator()
        act("/mIconFavorites.svg", "Fjern fra favoritter" if cid in self.favorites else "Gem som favorit",
            lambda: self._toggle_fav(cid))
        m.addSeparator()
        act("/mActionEditCopy.svg", "Kopiér datasæt-id", lambda: self._copy(cid, "Datasæt-id kopieret"))
        act("/mActionEditCopy.svg", "Kopiér fil-URL (til DuckDB/Python)", lambda: self._copy_url(cid))
        act("/mActionOpenTable.svg", "Åbn på datagrundlag.dk",
            lambda: QDesktopServices.openUrl(QUrl(core.website_url(cid))))
        return m

    def _copy(self, text, msg):
        QApplication.clipboard().setText(text)
        self.status.setText(msg)

    def _copy_url(self, cid):
        try:
            urls = core.resolve(cid)
            self._copy(urls["fgb"] or urls["parquet"], "Fil-URL kopieret")
        except Exception as e:  # noqa: BLE001
            self.status.setText(str(e))

    # ======================================================================
    # Tilføj data
    # ======================================================================
    def _with_info(self, then):
        """Sørg for at info er hentet, før der tilføjes (henter i baggrunden ved behov)."""
        data = self._selected()
        if not data:
            return
        cid = data[0]
        if is_package(cid):
            self._add_package(cid)
            return
        if cid in self._info:
            then(cid, data[1], self._info[cid])
        else:
            self.status.setText("Henter information …")
            self._fetch_info(cid, then=lambda: then(cid, data[1], self._info[cid]))

    def _add_default(self):
        def go(cid, title, info):
            if info["kind"] == "points":
                self._start_points(cid, title, info)
            elif core.is_large(info):
                self._ask_large(cid, title, info)
            else:
                self._add_full_now(cid, title, info)
        self._with_info(go)

    def _add_full(self):
        self._with_info(lambda cid, title, info: self._add_full_now(cid, title, info, guard=core.is_large(info)))

    def _add_extent(self):
        def go(cid, title, info):
            if info["kind"] == "points":
                self._start_points(cid, title, info)
            else:
                self._start_extent(cid, title, info)
        self._with_info(go)

    def _add_from_date(self):
        self._with_info(self._ask_date)

    def _ask_large(self, cid, title, info):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Stort datasæt")
        box.setText(f"<b>{core.short_title(title)}</b> har {core.fmt_rows(info['rows'])}.")
        box.setInformativeText(
            "Vil du kun hente data for dit kortudsnit? Det er hurtigst og anbefales.\n\n"
            "Tilføjer du hele datasættet, vises det først, når du zoomer ind til 1:50.000 "
            "eller tættere, så QGIS ikke går i stå.")
        b_ext = box.addButton("Kun mit kortudsnit", QMessageBox.ButtonRole.AcceptRole)
        b_full = box.addButton("Hele datasættet", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Annullér", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(b_ext)
        box.exec()
        if box.clickedButton() is b_ext:
            self._start_extent(cid, title, info)
        elif box.clickedButton() is b_full:
            self._add_full_now(cid, title, info, guard=True)

    def _ask_date(self, cid, title, info):
        snaps = info["snapshots"]
        if not snaps:
            self.status.setText("Datasættet har ingen historik endnu.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Data fra en bestemt dato")
        lay = QVBoxLayout(dlg)
        lab = QLabel(f"<b>{core.short_title(title)}</b><br>Der er data fra <b>{snaps[0]}</b> til "
                     f"<b>{snaps[-1]}</b>.<br>Du får data, som de så ud på den valgte dato.")
        lab.setWordWrap(True)
        lay.addWidget(lab)
        de = QDateEdit()
        de.setCalendarPopup(True)
        de.setDisplayFormat("yyyy-MM-dd")
        lo, hi = QDate.fromString(snaps[0], "yyyy-MM-dd"), QDate.fromString(snaps[-1], "yyyy-MM-dd")
        de.setDateRange(lo, hi)
        de.setDate(hi)
        lay.addWidget(de)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        d = de.date().toString("yyyy-MM-dd")
        if info["kind"] == "points":
            self._start_points(cid, title, info, date=d)
        elif core.is_large(info):
            self._start_extent(cid, title, info, date=d)
        else:
            self._add_full_now(cid, title, info, date=d)

    def _busy(self, on):
        if on:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _add_full_now(self, cid, title, info, date=None, guard=False):
        self.status.setText(f"Tilføjer {core.short_title(title)} …")
        QApplication.processEvents()
        self._busy(True)
        try:
            lyr = core.add_layer(cid, date, title, info, guard=guard)
        except Exception as e:  # noqa: BLE001
            self._fail(str(e))
            return
        finally:
            self._busy(False)
        self._done(cid, f"✓ Tilføjet: {lyr.name()}")
        if guard:
            self.iface.messageBar().pushMessage(
                "Datagrundlag Browser",
                f"{core.short_title(title)} vises, når du zoomer ind til 1:50.000 eller tættere.",
                level=Qgis.MessageLevel.Info, duration=8)

    def _extent_25832(self):
        canvas = self.iface.mapCanvas()
        src = canvas.mapSettings().destinationCrs()
        dst = QgsCoordinateReferenceSystem("EPSG:25832")
        rect = canvas.extent()
        if src != dst:
            rect = QgsCoordinateTransform(src, dst, QgsProject.instance()).transformBoundingBox(rect)
        return rect

    def _start_extent(self, cid, title, info, date=None):
        try:
            urls = core.resolve(cid, date)
        except Exception as e:  # noqa: BLE001
            self._fail(str(e))
            return
        rect = self._extent_25832()
        name = core.layer_name(cid, title, urls["snapshot_date"], "kortudsnit")

        def done(task, ok):
            self._tasks.discard(task)
            if not ok:
                self._fail(task.error or "Hentningen blev annulleret.")
                return
            lyr = task.build_layer(name)
            core.finish_layer(lyr, cid, info, date or urls["snapshot_date"], copy=True)
            self._done(cid, f"✓ Tilføjet {len(task.features):,} objekter fra dit kortudsnit".replace(",", "."))
            self._tell_temporary()

        task = ExtentCopyTask(f"Datagrundlag: {core.short_title(title)} (kortudsnit)",
                              core.gdal_source(urls), rect, done)
        self._run_task(task, f"Henter {core.short_title(title)} for dit kortudsnit …")

    def _start_points(self, cid, title, info, date=None):
        rect = self._extent_25832()
        area = rect.width() * rect.height() / 1e6
        if area > MAX_POINT_AREA_KM2:
            self._fail(f"Kortudsnittet er for stort ({area:,.0f} km²). Zoom ind til et område på "
                       f"højst ca. 50 × 50 km – fx en by eller en kommune.".replace(",", "."))
            return
        try:
            urls = core.resolve(cid, date)
        except Exception as e:  # noqa: BLE001
            self._fail(str(e))
            return
        name = core.layer_name(cid, title, urls["snapshot_date"], "punkter i kortudsnit")

        def done(task, ok):
            self._tasks.discard(task)
            if not ok:
                self._fail(task.error or "Hentningen blev annulleret.")
                return
            if not task.rows:
                self._fail("Der var ingen data i dit kortudsnit.")
                return
            lyr = task.build_layer(name)
            core.finish_layer(lyr, cid, info, date or urls["snapshot_date"], copy=True)
            self._done(cid, f"✓ Tilføjet {len(task.rows):,} punkter fra dit kortudsnit".replace(",", "."))
            self._tell_temporary()

        task = PointsTask(f"Datagrundlag: {core.short_title(title)} som punkter",
                          urls["parquet"], core.POINT_TABLES[cid],
                          (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()), done,
                          core.POINT_COLUMNS.get(cid))
        self._run_task(task, f"Henter {core.short_title(title)} … (se fremdriften nederst i QGIS)")

    def _run_task(self, task, msg):
        self._tasks.add(task)
        task.progressChanged.connect(
            lambda p, t=task: self.status.setText(f"{t.description()} … {int(p)} %"))
        QgsApplication.taskManager().addTask(task)
        self.status.setText(msg)

    def _tell_temporary(self):
        self.iface.messageBar().pushMessage(
            "Datagrundlag Browser",
            "Laget er en midlertidig kopi af dit kortudsnit. Klik på ikonet ved laget og vælg "
            "'Gør permanent', hvis du vil gemme det sammen med projektet.",
            level=Qgis.MessageLevel.Info, duration=10)

    def _add_package(self, cid):
        key, name, _desc, layers = self._package(cid)

        def progress(n, total, title):
            self.status.setText(f"Tilføjer {name}: {core.short_title(title)} ({n + 1}/{total}) …")
            QApplication.processEvents()

        self._busy(True)
        try:
            added, errors = core.add_package(key, self._titles, progress)
        finally:
            self._busy(False)
        self.status.setText(f"✓ Tilføjede startpakken {name} ({len(added)} lag)")
        if errors:
            self._fail("Nogle lag kunne ikke tilføjes: " + "; ".join(errors))
        elif any(g for _c, g in layers):
            self.iface.messageBar().pushMessage(
                "Datagrundlag Browser", f"{name} er tilføjet. Zoom ind til 1:50.000 eller tættere for at se "
                "de store lag (fx bygninger og veje).", level=Qgis.MessageLevel.Success, duration=8)

    def _done(self, cid, msg):
        self._remember(cid)
        self._build_tree()
        self.status.setText(msg)

    def _fail(self, msg):
        self.status.setText(msg)
        self.iface.messageBar().pushMessage("Datagrundlag Browser", msg,
                                            level=Qgis.MessageLevel.Warning, duration=8)

    def _refresh(self):
        self._busy(True)
        try:
            ch = core.refresh_all()
            self.status.setText(f"✓ Opdaterede {len(ch)} lag" if ch else "Alle lag viser allerede nyeste data")
        except Exception as e:  # noqa: BLE001
            self.status.setText(str(e))
        finally:
            self._busy(False)
