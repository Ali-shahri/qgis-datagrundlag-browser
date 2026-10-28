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
from collections import defaultdict

from qgis.core import Qgis, QgsApplication, QgsSettings
from qgis.gui import QgsFilterLineEdit
from qgis.PyQt.QtCore import QDate, Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QDockWidget, QFrame,
    QHBoxLayout, QLabel, QMenu, QPushButton, QSplitter, QTextBrowser,
    QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import core

ROLE = Qt.ItemDataRole.UserRole
SETTINGS = "datagrundlag_browser/"
MAX_RECENT = 8
MODE_SOURCE, MODE_THEME = "source", "theme"


def icon(name):
    return QgsApplication.getThemeIcon(name)


def _load_list(key):
    try:
        val = json.loads(QgsSettings().value(SETTINGS + key, "[]"))
        return [x for x in val if isinstance(x, str)]
    except (TypeError, ValueError):
        return []


def _save_list(key, values):
    QgsSettings().setValue(SETTINGS + key, json.dumps(values))


class DatagrundlagDock(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Datagrundlag Browser", parent)
        self.iface = iface
        self.setObjectName("DatagrundlagBrowserDock")
        self._loaded = False
        self._datasets = []          # [(cid, title)]
        self._titles = {}            # cid -> title
        self._info_cache = {}
        self._base_status = ""
        self._groups = []            # [(label, total)] i samme rækkefølge som træet
        self.favorites = _load_list("favorites")
        self.recent = _load_list("recent")

        root = QWidget()
        v = QVBoxLayout(root)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        # --- Søgning + værktøjsknapper -------------------------------------
        top = QHBoxLayout()
        self.search = QgsFilterLineEdit()
        self.search.setShowSearchIcon(True)
        self.search.setPlaceholderText("Søg i 553 datasæt, fx lokalplan, skov, geofa …")
        top.addWidget(self.search, 1)
        self.btn_expand = self._tool("/mActionExpandTree.svg", "Fold alle grupper ud")
        self.btn_collapse = self._tool("/mActionCollapseTree.svg", "Fold alle grupper sammen")
        self.btn_reload = self._tool("/mActionRefresh.svg", "Genindlæs kataloget")
        for b in (self.btn_expand, self.btn_collapse, self.btn_reload):
            top.addWidget(b)
        v.addLayout(top)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Gruppér efter:"))
        self.mode = QComboBox()
        self.mode.addItem("Kilde (BBR, GeoDanmark …)", MODE_SOURCE)
        self.mode.addItem("Tema (natur, planer, ejendomme …)", MODE_THEME)
        saved = QgsSettings().value(SETTINGS + "mode", MODE_SOURCE)
        self.mode.setCurrentIndex(1 if saved == MODE_THEME else 0)
        mode_row.addWidget(self.mode, 1)
        v.addLayout(mode_row)

        # --- Træ med grupper og datasæt + infoboks --------------------------
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIndentation(14)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        info = QFrame()
        info.setFrameShape(QFrame.Shape.StyledPanel)
        iv = QVBoxLayout(info)
        iv.setContentsMargins(8, 6, 8, 6)
        head = QHBoxLayout()
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
        self.btn_fav.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        head.addWidget(self.btn_fav, 0, Qt.AlignmentFlag.AlignTop)
        iv.addLayout(head)
        self.info_meta = QLabel("")
        self.info_meta.setWordWrap(True)
        self.info_meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.info_meta.setOpenExternalLinks(True)
        self.info_desc = QTextBrowser()
        self.info_desc.setFrameShape(QFrame.Shape.NoFrame)
        self.info_desc.setPlaceholderText("Klik på et datasæt for at se beskrivelse, "
                                          "nyeste data og om det kan vises på kortet.\n\n"
                                          "Tip: højreklik for flere muligheder, og tilføj "
                                          "dine mest brugte datasæt til favoritter med ☆.")
        iv.addWidget(self.info_meta)
        iv.addWidget(self.info_desc, 1)
        self._set_fav_button(False)

        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.tree)
        split.addWidget(info)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setChildrenCollapsible(False)
        v.addWidget(split, 1)

        # --- Tidsrejse -----------------------------------------------------
        h = QHBoxLayout()
        self.hist = QCheckBox("Hent data som de så ud på:")
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setEnabled(False)
        self.hist.toggled.connect(self.date.setEnabled)
        h.addWidget(self.hist)
        h.addWidget(self.date, 1)
        v.addLayout(h)

        # --- Handlinger ----------------------------------------------------
        self.btn_add = QPushButton(icon("/mActionAddLayer.svg"), "  Tilføj til kortet")
        self.btn_add.setMinimumHeight(32)
        self.btn_add.setEnabled(False)
        f = self.btn_add.font()
        f.setBold(True)
        self.btn_add.setFont(f)
        v.addWidget(self.btn_add)

        self.btn_ref = QPushButton(icon("/mActionReload.svg"), "  Opdatér mine lag til nyeste data")
        self.btn_ref.setToolTip("Peger alle Datagrundlag-lag i projektet på nyeste snapshot. "
                                "Lag hentet på en bestemt dato røres ikke.")
        v.addWidget(self.btn_ref)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: palette(mid);")
        v.addWidget(self.status)

        self.setWidget(root)

        # --- Signaler --------------------------------------------------------
        self.search.valueChanged.connect(self._filter)
        self.mode.currentIndexChanged.connect(self._on_mode)
        self.tree.currentItemChanged.connect(self._on_select)
        self.tree.itemDoubleClicked.connect(self._on_double)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.btn_fav.clicked.connect(self._toggle_current_fav)
        self.btn_add.clicked.connect(self._add)
        self.btn_ref.clicked.connect(self._refresh)
        self.btn_reload.clicked.connect(self.load_catalog)
        self.btn_expand.clicked.connect(self.tree.expandAll)
        self.btn_collapse.clicked.connect(self.tree.collapseAll)

    def _tool(self, icon_name, tip):
        b = QToolButton()
        b.setIcon(icon(icon_name))
        b.setToolTip(tip)
        b.setAutoRaise(True)
        return b

    # Kataloget hentes først, når panelet vises første gang (QGIS starter hurtigere)
    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self.load_catalog()

    def _busy(self, on):
        if on:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    # --- Katalog og træ ----------------------------------------------------------
    def load_catalog(self):
        self.status.setText("Henter katalog …")
        QApplication.processEvents()
        self._busy(True)
        try:
            self._datasets = core.list_datasets()
        except Exception as e:  # noqa: BLE001
            self.status.setText(f"Kunne ikke hente katalog: {e}")
            return
        finally:
            self._busy(False)
        self._titles = dict(self._datasets)
        self._loaded = True
        sources = {core.source_label(cid) for cid, _ in self._datasets}
        self._base_status = f"{len(self._datasets)} datasæt fra {len(sources)} kilder"
        self._build_tree()

    def _mode(self):
        return self.mode.currentData()

    def _on_mode(self, _idx):
        QgsSettings().setValue(SETTINGS + "mode", self._mode())
        self._build_tree()

    def _make_group(self, label, icon_name, entries, bold=True):
        g = QTreeWidgetItem([label])
        g.setIcon(0, icon(icon_name))
        g.setData(0, ROLE, None)
        g.setFlags(Qt.ItemFlag.ItemIsEnabled)
        fg = g.font(0)
        fg.setBold(bold)
        g.setFont(0, fg)
        for cid, text in entries:
            c = QTreeWidgetItem([text])
            c.setData(0, ROLE, (cid, self._titles.get(cid, cid)))
            c.setToolTip(0, f"{self._titles.get(cid, cid)}\n{cid}")
            if cid in self._info_cache:
                c.setIcon(0, self._kind_icon(self._info_cache[cid]))
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
        theme_mode = self._mode() == MODE_THEME

        def label_for(cid):
            title = self._titles.get(cid, cid)
            return title if theme_mode else (core.short_title(title) or cid)

        favs = [c for c in self.favorites if c in self._titles]
        if favs:
            g = self._make_group("★ Favoritter", "/mIconFavorites.svg",
                                 [(c, self._titles[c]) for c in favs])
            g.setExpanded(True)
        recent = [c for c in self.recent if c in self._titles]
        if recent:
            self._make_group("Senest tilføjet", "/mIconHistory.svg",
                             [(c, self._titles[c]) for c in recent])

        groups = defaultdict(list)
        group_of = core.theme_label if theme_mode else core.source_label
        for cid, _title in self._datasets:
            groups[group_of(cid)].append(cid)
        if theme_mode:
            order = [name for name, _ in core.THEMES if name in groups]
            order += sorted(k for k in groups if k not in order)
        else:
            order = sorted(groups, key=str.lower)
        for label in order:
            entries = sorted(((cid, label_for(cid)) for cid in groups[label]),
                             key=lambda x: x[1].lower())
            self._make_group(label, "/mIconFolder.svg", entries)

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
                hit = not t or group_hit or t in title.lower() or t in cid.lower() \
                    or t in core.source_label(cid).lower()
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
        if self._loaded:
            self.status.setText(f"{len(shown)} datasæt matcher «{txt.strip()}»" if t
                                else self._base_status)

    # --- Valg og info -----------------------------------------------------------
    def _selected(self):
        it = self.tree.currentItem()
        return it.data(0, ROLE) if it else None

    @staticmethod
    def _kind_icon(info):
        return icon("/mIconPolygonLayer.svg" if info["has_geometry"] else "/mIconTableLayer.svg")

    def _set_fav_button(self, is_fav):
        self.btn_fav.setText("★ Favorit" if is_fav else "☆ Favorit")
        self.btn_fav.setToolTip("Fjern fra favoritter" if is_fav else "Tilføj til favoritter")

    def _on_select(self, cur, _prev):
        data = cur.data(0, ROLE) if cur else None
        self.btn_add.setEnabled(bool(data))
        self.btn_fav.setEnabled(bool(data))
        if not data:
            self.info_title.setText("Vælg et datasæt")
            self.info_meta.setText("")
            self.info_desc.clear()
            self._set_fav_button(False)
            return
        cid, title = data
        self._set_fav_button(cid in self.favorites)
        self.info_title.setText(title or cid)
        self.info_meta.setText(f"<span style='color:gray'>{cid}</span>  ·  henter info …")
        QApplication.processEvents()
        info = self._info_cache.get(cid)
        if info is None:
            self._busy(True)
            try:
                info = core.dataset_info(cid)
                self._info_cache[cid] = info
            except Exception as e:  # noqa: BLE001
                self.info_meta.setText(f"<span style='color:gray'>{cid}</span>")
                self.info_desc.setPlainText(f"Kunne ikke hente info: {e}")
                return
            finally:
                self._busy(False)
        if self._selected() != data:   # brugeren har valgt noget andet i mellemtiden
            return
        kind = ("Kortlag (FlatGeobuf)" if info["has_geometry"]
                else "Tabel uden geometri (GeoParquet) – kræver Parquet-understøttelse")
        n = len(info["snapshots"])
        first = info["snapshots"][0] if n else "–"
        self.info_meta.setText(
            f"<span style='color:gray'>{cid}</span><br>"
            f"{kind}<br>"
            f"Nyeste data: <b>{info['latest']}</b>  ·  {n} snapshots siden {first}<br>"
            f"<a href='{core.website_url(cid)}'>Se datasættet på datagrundlag.dk</a>"
        )
        self.info_desc.setPlainText(info["description"] or "Ingen beskrivelse.")
        cur.setIcon(0, self._kind_icon(info))

    def _on_double(self, item, _col):
        if item.data(0, ROLE):
            self._add()

    # --- Favoritter og senest brugt -------------------------------------------------
    def _toggle_fav(self, cid):
        if cid in self.favorites:
            self.favorites.remove(cid)
            msg = "Fjernet fra favoritter"
        else:
            self.favorites.append(cid)
            msg = "★ Tilføjet til favoritter"
        _save_list("favorites", self.favorites)
        self._build_tree()
        self.status.setText(msg)

    def _toggle_current_fav(self):
        data = self._selected()
        if data:
            self._toggle_fav(data[0])

    def _remember(self, cid):
        self.recent = [cid] + [c for c in self.recent if c != cid]
        self.recent = self.recent[:MAX_RECENT]
        _save_list("recent", self.recent)

    # --- Højrekliksmenu -----------------------------------------------------------
    def _context_menu(self, pos):
        item = self.tree.itemAt(pos)
        data = item.data(0, ROLE) if item else None
        if not data:
            return
        self.tree.setCurrentItem(item)
        self._build_menu(data[0]).exec(self.tree.viewport().mapToGlobal(pos))

    def _build_menu(self, cid):
        m = QMenu(self.tree)

        def act(icon_name, text, slot):
            a = m.addAction(icon(icon_name), text)
            a.triggered.connect(lambda _checked=False: slot())

        act("/mActionAddLayer.svg", "Tilføj til kortet", self._add)
        m.addSeparator()
        act("/mIconFavorites.svg",
            "Fjern fra favoritter" if cid in self.favorites else "Tilføj til favoritter",
            lambda: self._toggle_fav(cid))
        m.addSeparator()
        act("/mActionEditCopy.svg", "Kopiér datasæt-id",
            lambda: self._copy(cid, "Datasæt-id kopieret"))
        act("/mActionEditCopy.svg", "Kopiér fil-URL (nyeste data)",
            lambda: self._copy_url(cid))
        act("/mActionOpenTable.svg", "Åbn på datagrundlag.dk",
            lambda: QDesktopServices.openUrl(QUrl(core.website_url(cid))))
        return m

    def _copy(self, text, msg):
        QApplication.clipboard().setText(text)
        self.status.setText(msg)

    def _copy_url(self, cid):
        self._busy(True)
        try:
            urls = core.resolve(cid)
            self._copy(urls["fgb"] or urls["parquet"], "Fil-URL kopieret")
        except Exception as e:  # noqa: BLE001
            self.status.setText(str(e))
        finally:
            self._busy(False)

    # --- Handlinger ---------------------------------------------------------------
    def _add(self):
        data = self._selected()
        if not data:
            self.status.setText("Vælg et datasæt først")
            return
        cid, title = data
        d = self.date.date().toString("yyyy-MM-dd") if self.hist.isChecked() else None
        self.status.setText(f"Tilføjer {core.short_title(title)} …")
        QApplication.processEvents()
        self._busy(True)
        try:
            lyr = core.add_layer(cid, d, title)
        except Exception as e:  # noqa: BLE001
            self.status.setText(str(e))
            self.iface.messageBar().pushMessage("Datagrundlag Browser", str(e),
                                                level=Qgis.MessageLevel.Warning)
            return
        finally:
            self._busy(False)
        self._remember(cid)
        self._build_tree()
        self.status.setText(f"✓ Tilføjet: {lyr.name()}")

    def _refresh(self):
        self._busy(True)
        try:
            ch = core.refresh_all()
            self.status.setText(f"✓ Opdaterede {len(ch)} lag" if ch
                                else "Alle lag viser allerede nyeste data")
        except Exception as e:  # noqa: BLE001
            self.status.setText(str(e))
        finally:
            self._busy(False)
