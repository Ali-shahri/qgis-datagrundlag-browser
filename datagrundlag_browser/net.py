# -*- coding: utf-8 -*-
# Datagrundlag Browser – QGIS-plugin til datagrundlag.dk
# Copyright (C) 2026 Ali Shahri
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version. See the LICENSE file.
"""Hentning af JSON i baggrunden, så QGIS aldrig fryser."""

import json

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

_NO_ERROR = QNetworkReply.NetworkError.NoError
_pending = set()   # hold referencer, så svarene ikke bliver ryddet væk undervejs


def get_json(url, callback):
    """Hent JSON asynkront. callback(data, fejltekst) kaldes på hovedtråden."""
    if not url.startswith("https://"):
        callback(None, f"Kun https-adresser er tilladt: {url}")
        return
    reply = QgsNetworkAccessManager.instance().get(QNetworkRequest(QUrl(url)))
    _pending.add(reply)

    def done():
        _pending.discard(reply)
        try:
            if reply.error() != _NO_ERROR:
                callback(None, reply.errorString())
                return
            try:
                data = json.loads(bytes(reply.readAll()).decode("utf-8"))
            except ValueError as e:
                callback(None, f"Ugyldigt svar fra {url}: {e}")
                return
            callback(data, None)
        finally:
            reply.deleteLater()

    reply.finished.connect(done)


def get_many(urls, callback):
    """Hent flere JSON-filer parallelt. callback({url: data}, fejltekst) når alle er hentet."""
    results, errors = {}, []
    remaining = [len(urls)]

    def one(url):
        def cb(data, err):
            if err:
                errors.append(err)
            else:
                results[url] = data
            remaining[0] -= 1
            if remaining[0] == 0:
                callback(results, errors[0] if errors else None)
        return cb

    for u in urls:
        get_json(u, one(u))
