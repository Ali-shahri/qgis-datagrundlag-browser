# Tjekliste: udgiv på plugins.qgis.org

## Før første udgivelse

- [x] Offentligt GitHub-repo: https://github.com/Ali-shahri/qgis-datagrundlag-browser
- [x] Links, forfatter og e-mail (GitHub noreply) er udfyldt i `metadata.txt`.
- [ ] Tjek, at de tre links i `metadata.txt` virker i en browser.

## Byg og upload

1. Kør `python make_zip.py` fra repoets rod. ZIP-filen lægges i `dist/`.
2. Installér ZIP-filen i din egen QGIS og afprøv den en sidste gang.
3. Log ind på https://plugins.qgis.org/ med en OSGeo-konto (opret en, hvis du ikke har en).
4. Vælg **Upload a plugin** og upload ZIP-filen.
5. Vent på godkendelse. Det kan tage fra få minutter til nogle dage (uploads i weekenden bliver typisk godkendt om mandagen).

## Når den er afprøvet af andre

- Sæt `experimental=False` i `metadata.txt`, så pluginet kan findes uden at slå eksperimentelle plugins til.

## Ved hver ny version

- [ ] Hæv `version=` i `metadata.txt` (fx 0.1.0 → 0.2.0).
- [ ] Tilføj en linje øverst under `changelog=`.
- [ ] Kør `python make_zip.py` og upload den nye ZIP-fil.
