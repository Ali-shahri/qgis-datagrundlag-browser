"""Byg en ZIP-fil af pluginet, klar til upload på plugins.qgis.org.

Kør fra repoets rod:  python make_zip.py
Resultat:             dist/datagrundlag_browser-<version>.zip
"""
import configparser
import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
PLUGIN = ROOT / "datagrundlag_browser"
SKIP_DIRS = {"__pycache__", ".git"}
SKIP_SUFFIX = {".pyc", ".pyo"}

meta = configparser.ConfigParser()
meta.read(PLUGIN / "metadata.txt", encoding="utf-8")
version = meta["general"]["version"]

dist = ROOT / "dist"
dist.mkdir(exist_ok=True)
out = dist / f"datagrundlag_browser-{version}.zip"

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(PLUGIN.rglob("*")):
        if f.is_dir() or SKIP_DIRS & set(f.parts) or f.suffix in SKIP_SUFFIX:
            continue
        z.write(f, f.relative_to(ROOT))

print(f"Lavet: {out}")
