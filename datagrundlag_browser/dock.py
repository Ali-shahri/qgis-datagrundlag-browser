# -*- coding: utf-8 -*-
# Datagrundlag Browser – QGIS-plugin til datagrundlag.dk
# Copyright (C) 2026 Ali Shahri
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version. See the LICENSE file.
"""Panelet (dock widget) til Datagrundlag Browser."""

from collections import defaultdict

from qgis.core import Qgis, QgsApplication
from qgis.gui import QgsFilterLineEdit
from qgis.PyQt.QtCore import QDate, Qt
from qgis.PyQt.QtWidgets import (
    QApplication, QCheckBox, QDateEdit, QDockWidget, QFrame, QHBoxLayout,
    QLabel, QPushButton, QSplitter, QTextBrowser, QToolButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from . import core

ROLE = Qt.ItemDataRole.UserRole


def icon(name):
    return QgsApplication.getThemeIcon(name)


class DatagrundlagDock(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Datagrundlag Browser", parent)
        self.iface = iface
        self.setObjectName("DatagrundlagBrowserDock")
        self._loaded = False
        self._info_cache = {}
        self._base_status = ""
        self._groups = []

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
        self.btn_expand = self._tool("/mActionExpandTree.svg", "Fold alle kilder ud")
        self.btn_collapse = self._tool("/mActionCollapseTree.svg", "Fold alle kilder sammen")
        self.btn_reload = self._tool("/mActionRefresh.svg", "Genindlæs kataloget")
        for b in (self.btn_expand, self.btn_collapse, self.btn_reload):
            top.addWidget(b)
        v.addLayout(top)

        # --- Træ med kilder og datasæt + infoboks ---------------------------
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIndentation(14)

        info = QFrame()
        info.setFrameShape(QFrame.Shape.StyledPanel)
        iv = QVBoxLayout(info)
        iv.setContentsMargins(8, 6, 8, 6)
        self.info_title = QLabel("Vælg et datasæt")
        f = self.info_title.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.1)
        self.info_title.setFont(f)
        self.info_title.setWordWrap(True)
        self.info_meta = QLabel("")
        self.info_meta.setWordWrap(True)
        self.info_meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.info_desc = QTextBrowser()
        self.info_desc.setFrameShape(QFrame.Shape.NoFrame)
        self.info_desc.setOpenExternalLinks(True)
        self.info_desc.setPlaceholderText("Klik på et datasæt for at se beskrivelse, "
                                          "nyeste snapshot og om det kan vises på kortet.")
        iv.addWidget(self.info_title)
        iv.addWidget(self.info_meta)
        iv.addWidget(self.info_desc, 1)

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
        self.tree.currentItemChanged.connect(self._on_select)
        self.tree.itemDoubleClicked.connect(self._on_double)
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

    # --- Katalog ---------------------------------------------------------------
    def load_catalog(self):
        self.status.setText("Henter katalog …")
        QApplication.processEvents()
        self._busy(True)
        try:
            datasets = core.list_datasets()
        except Exception as e:  # noqa: BLE001
            self.status.setText(f"Kunne ikke hente katalog: {e}")
            return
        finally:
            self._busy(False)

        groups = defaultdict(list)
        for cid, title in datasets:
            groups[core.source_label(cid)].append((cid, title))

        self.tree.clear()
        self._groups = []
        folder = icon("/mIconFolder.svg")
        for label in sorted(groups, key=str.lower):
            items = sorted(groups[label], key=lambda x: core.short_title(x[1]).lower())
            g = QTreeWidgetItem([f"{label}  ({len(items)})"])
            g.setIcon(0, folder)
            g.setData(0, ROLE, None)
            g.setFlags(Qt.ItemFlag.ItemIsEnabled)
            fg = g.font(0)
            fg.setBold(True)
            g.setFont(0, fg)
            for cid, title in items:
                c = QTreeWidgetItem([core.short_title(title) or cid])
                c.setData(0, ROLE, (cid, title))
                c.setToolTip(0, f"{title}\n{cid}")
                g.addChild(c)
            self.tree.addTopLevelItem(g)
            self._groups.append((label, len(items)))

        self._loaded = True
        self._base_status = f"{len(datasets)} datasæt fra {len(groups)} kilder"
        self.status.setText(self._base_status)
        self._filter(self.search.value())

    def _filter(self, txt):
        t = (txt or "").strip().lower()
        shown = 0
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            group_hit = bool(t) and t in g.text(0).lower()
            visible = 0
            for j in range(g.childCount()):
                c = g.child(j)
                cid, title = c.data(0, ROLE)
                hit = not t or group_hit or t in title.lower() or t in cid.lower()
                c.setHidden(not hit)
                visible += hit
            label, total = self._groups[i]
            g.setText(0, f"{label}  ({visible} af {total})" if t else f"{label}  ({total})")
            g.setHidden(visible == 0)
            g.setExpanded(bool(t) and visible > 0)
            shown += visible
        if self._loaded:
            self.status.setText(f"{shown} datasæt matcher «{txt.strip()}»" if t else self._base_status)

    # --- Valg og info -----------------------------------------------------------
    def _selected(self):
        it = self.tree.currentItem()
        return it.data(0, ROLE) if it else None

    def _on_select(self, cur, _prev):
        data = cur.data(0, ROLE) if cur else None
        self.btn_add.setEnabled(bool(data))
        if not data:
            self.info_title.setText("Vælg et datasæt")
            self.info_meta.setText("")
            self.info_desc.clear()
            return
        cid, title = data
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
            f"Nyeste data: <b>{info['latest']}</b>  ·  {n} snapshots siden {first}"
        )
        self.info_desc.setPlainText(info["description"] or "Ingen beskrivelse.")
        cur.setIcon(0, icon("/mIconPolygonLayer.svg" if info["has_geometry"]
                            else "/mIconTableLayer.svg"))

    def _on_double(self, item, _col):
        if item.data(0, ROLE):
            self._add()

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
            self.status.setText(f"✓ Tilføjet: {lyr.name()}")
        except Exception as e:  # noqa: BLE001
            self.status.setText(str(e))
            self.iface.messageBar().pushMessage("Datagrundlag Browser", str(e),
                                                level=Qgis.MessageLevel.Warning)
        finally:
            self._busy(False)

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
