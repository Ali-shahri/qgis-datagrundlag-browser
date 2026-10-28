# -*- coding: utf-8 -*-
# Datagrundlag Browser – QGIS-plugin til datagrundlag.dk
# Copyright (C) 2026 Ali Shahri
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version. See the LICENSE file.
"""Panelet (dock widget) til Datagrundlag-pluginet."""

from qgis.core import Qgis
from qgis.PyQt.QtCore import Qt, QDate
from qgis.PyQt.QtWidgets import (
    QApplication, QCheckBox, QDateEdit, QDockWidget, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from . import core


class DatagrundlagDock(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Datagrundlag Browser", parent)
        self.iface = iface
        self.setObjectName("DatagrundlagBrowserDock")
        self._loaded = False

        w = QWidget()
        v = QVBoxLayout(w)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Søg, fx bygning, lokalplan, geofa, natura …")
        self.search.setClearButtonEnabled(True)
        self.lst = QListWidget()
        self.status = QLabel("")
        self.status.setWordWrap(True)

        self.hist = QCheckBox("Data som de så ud på dato:")
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setEnabled(False)
        self.hist.toggled.connect(self.date.setEnabled)
        h = QHBoxLayout()
        h.addWidget(self.hist)
        h.addWidget(self.date)

        self.btn_add = QPushButton("Tilføj valgte lag")
        self.btn_ref = QPushButton("Opdatér alle lag til nyeste")
        self.btn_reload = QPushButton("Genindlæs katalog")

        v.addWidget(self.search)
        v.addWidget(self.lst)
        v.addLayout(h)
        v.addWidget(self.btn_add)
        v.addWidget(self.btn_ref)
        v.addWidget(self.btn_reload)
        v.addWidget(self.status)
        self.setWidget(w)

        self.search.textChanged.connect(self._filter)
        self.btn_add.clicked.connect(self._add)
        self.lst.itemDoubleClicked.connect(lambda _: self._add())
        self.btn_ref.clicked.connect(self._refresh)
        self.btn_reload.clicked.connect(self.load_catalog)

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
        self.lst.clear()
        for cid, title in datasets:
            it = QListWidgetItem(f"{title}  [{cid}]" if title else cid)
            it.setData(Qt.ItemDataRole.UserRole, (cid, title))
            it.setToolTip(cid)
            self.lst.addItem(it)
        self._loaded = True
        self._filter(self.search.text())
        self.status.setText(f"{len(datasets)} datasæt i kataloget")

    def _filter(self, txt):
        t = txt.lower()
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            it.setHidden(t not in it.text().lower())

    def _add(self):
        sel = self.lst.selectedItems()
        if not sel:
            self.status.setText("Vælg et datasæt først")
            return
        cid, title = sel[0].data(Qt.ItemDataRole.UserRole)
        d = self.date.date().toString("yyyy-MM-dd") if self.hist.isChecked() else None
        self.status.setText(f"Tilføjer {cid} …")
        QApplication.processEvents()
        self._busy(True)
        try:
            lyr = core.add_layer(cid, d, title)
            self.status.setText(f"Tilføjet: {lyr.name()}")
        except Exception as e:  # noqa: BLE001
            self.status.setText(str(e))
            self.iface.messageBar().pushMessage("Datagrundlag Browser", str(e), level=Qgis.MessageLevel.Warning)
        finally:
            self._busy(False)

    def _refresh(self):
        self._busy(True)
        try:
            ch = core.refresh_all()
            self.status.setText(f"Opdaterede {len(ch)} lag" if ch else "Alle lag er allerede nyeste")
        except Exception as e:  # noqa: BLE001
            self.status.setText(str(e))
        finally:
            self._busy(False)
