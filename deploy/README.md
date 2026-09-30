# deploy/

`deploy/data/` is a **committed snapshot** of the artefacts the backend loads (Q51): `metadata.json`, `zones.parquet`, `cells_<size>.parquet` and the `layer_*.geojson` context layers (about 1.7 MB). The large `cells_*.geojson` files are not included because the backend doesn't read them.

It is used by:
- the **Docker image** (`Dockerfile`), built from git by GitHub Actions (Q60), which has no access to `data/processed/`;
- the tests that need data (`tests/test_chat.py`), so they also run in CI;
- `scripts/demo.sh`, as the last data fallback when a fresh clone has neither `data/processed/` nor `data/raw/`.

**Refresh it after every `pipeline build`** with `make snapshot`, and commit it. `scripts/demo.sh` warns when `deploy/data/metadata.json` differs from `data/processed/metadata.json`.
