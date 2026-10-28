# -*- coding: utf-8 -*-
# Datagrundlag Browser – QGIS-plugin til datagrundlag.dk
# Copyright (C) 2026 Ali Shahri
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version. See the LICENSE file.
"""QGIS-plugin: Datagrundlag Browser."""


def classFactory(iface):  # noqa: N802 – navnet kræves af QGIS
    from .plugin import DatagrundlagPlugin
    return DatagrundlagPlugin(iface)
