# -*- coding: utf-8 -*-
# Datagrundlag Browser – QGIS-plugin til datagrundlag.dk
# Copyright (C) 2026 Ali Shahri
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version. See the LICENSE file.
"""Plugin-klassen: knap i værktøjslinjen + menupunkt, der viser/skjuler panelet."""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .dock import DatagrundlagDock

MENU = "&Datagrundlag Browser"


class DatagrundlagPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock = None

    def initGui(self):  # noqa: N802 – navnet kræves af QGIS
        icon = QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))
        self.action = QAction(icon, "Datagrundlag Browser", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.setToolTip("Søg i og tilføj data fra datagrundlag.dk")

        self.dock = DatagrundlagDock(self.iface, self.iface.mainWindow())
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.hide()

        # Knap og panel følger hinanden
        self.action.toggled.connect(self.dock.setVisible)
        self.dock.visibilityChanged.connect(self.action.setChecked)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToWebMenu(MENU, self.action)

    def unload(self):
        self.iface.removePluginWebMenu(MENU, self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        self.action = None
