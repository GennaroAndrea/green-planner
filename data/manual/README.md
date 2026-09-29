# Hand-made data

Files in this folder are transcribed by hand, so they are committed (unlike `data/raw/`, which is re-downloadable).

## `arpa_annual_2025.csv`

2025 annual mean concentrations (µg/m³) at the 5 ARPA stations in Bari.

- **Source**: ARPA Puglia, UOC Centro Regionale Aria, *Relazione annuale integrata sulla qualità dell'aria – Regione Puglia – Anno 2025*, Rev. 1, July 2026 (prot. n. 0049015/2026).
  - Page: https://www.arpa.puglia.it/pagina2873_report-annuali-e-mensili-qualit-dellaria-rrqa.html
  - PDF: https://www.arpa.puglia.it/moduli/output_immagine.php?id=8789
- **Transcribed from**: Figura 4 (PM10, p. 21), Figura 10 (PM2.5, p. 31) and Figura 14 (NO₂, p. 37). The values are the integer labels on the bar charts, as published.
- **Transcribed on**: 2026-09-29.
- **Cross-check**: the report text (p. 37) confirms Bari - Cavour NO₂ = 26 µg/m³.
- Empty `pm25_ugm3` means the station doesn't measure PM2.5 (Carbonara, CUS), consistent with the data-coverage table on p. 65.
- `id_station` matches `id_station` in the ARPA stations GeoJSON (`data/raw/air_stations/stations.geojson`).
- Limit values drawn in the report's charts (D.Lgs. 155/2010): NO₂ 40, PM10 40, PM2.5 25 µg/m³ (annual means).
