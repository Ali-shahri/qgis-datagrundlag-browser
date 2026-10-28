# Tjekliste: ny version på plugins.qgis.org

1. Hæv `version=` i `datagrundlag_browser/metadata.txt`, og tilføj en linje øverst under `changelog=`.
2. Kør `python make_zip.py` fra repoets rod. ZIP-filen lægges i `dist/`.
3. Installér ZIP-filen i din egen QGIS og afprøv den.
4. Log ind på https://plugins.qgis.org/, åbn pluginet (ID 6770), klik **Add version** og upload ZIP-filen.
5. Tjek, at **Security Scan** og **Qt6 Check** er grønne.
6. Lav en release på GitHub med samme versionsnummer (fx `v1.1.3`) ud fra `main`, og vedhæft ZIP-filen.
