from datetime import date

from pipeline.config import load_config
from pipeline.download import _ckan_filename, resolve_files


def test_ckan_filename_uses_url_basename():
    res = {"id": "x", "name": "Aree verdi", "format": "CSV", "url": "https://h/d/aree-verdi.csv"}
    assert _ckan_filename(res) == "aree-verdi.csv"


def test_ckan_filename_falls_back_to_name_and_format():
    res = {
        "id": "x",
        "name": "Mappa dei Municipi - Shape",
        "format": "ZIP",
        "url": "https://h/r/f0c48bab",
    }
    assert _ckan_filename(res) == "Mappa_dei_Municipi_-_Shape.zip"


def test_dated_url_source_prefixes_today():
    spec = {
        "type": "url",
        "dated": True,
        "files": [{"url": "https://h/a", "filename": "a.geojson"}],
    }
    files = resolve_files(client=None, api="", spec=spec)  # url sources make no HTTP calls
    assert files[0].filename == f"{date.today().isoformat()}_a.geojson"


def test_config_weights_sum_to_100():
    assert sum(load_config("bari")["weights"].values()) == 100
