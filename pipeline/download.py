"""Download raw datasets listed in the city config into data/raw/<source>/.

Idempotent: files already on disk are skipped unless `force` is set. Every file is recorded
in data/raw/manifest.json with its source URL, size, SHA-256 and download time.
"""

import hashlib
import json
import re
import ssl
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from pipeline import satellite
from pipeline.config import RAW_DIR, project_path

MANIFEST_PATH = RAW_DIR / "manifest.json"
TIMEOUT = httpx.Timeout(30.0, read=120.0)
USER_AGENT = "green-planner/0.1 (open data research)"


@dataclass
class RemoteFile:
    url: str
    filename: str


def build_ssl_context(extra_ca_file: str | None) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if extra_ca_file:
        ctx.load_verify_locations(cafile=str(project_path(extra_ca_file)))
    return ctx


def resolve_ckan(client: httpx.Client, api: str, spec: dict[str, Any]) -> list[RemoteFile]:
    resp = client.get(f"{api}/package_show", params={"id": spec["dataset"]})
    resp.raise_for_status()
    resources = resp.json()["result"]["resources"]
    pattern = re.compile(spec["name_pattern"], re.IGNORECASE) if "name_pattern" in spec else None
    files = []
    for res in resources:
        if pattern and not pattern.search(res.get("name") or ""):
            continue
        files.append(RemoteFile(url=res["url"], filename=_ckan_filename(res)))
    return files


def _ckan_filename(resource: dict[str, Any]) -> str:
    name = Path(unquote(urlparse(resource["url"]).path)).name
    if "." in name:
        return name
    # Resource URL without a file name: build one from the resource name and format
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", resource.get("name") or resource["id"]).strip("_")
    return f"{base}.{(resource.get('format') or 'bin').lower()}"


def resolve_files(client: httpx.Client, api: str, spec: dict[str, Any]) -> list[RemoteFile]:
    if spec["type"] == "ckan":
        return resolve_ckan(client, api, spec)
    if spec["type"] == "url":
        files = [RemoteFile(url=f["url"], filename=f["filename"]) for f in spec["files"]]
        if spec.get("dated"):
            today = date.today().isoformat()
            files = [RemoteFile(f.url, f"{today}_{f.filename}") for f in files]
        return files
    raise ValueError(f"Unknown source type: {spec['type']}")


def fetch(client: httpx.Client, remote: RemoteFile, target: Path) -> dict[str, Any]:
    """Stream a file to disk (via a temp file) and return its manifest entry."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    sha = hashlib.sha256()
    with client.stream("GET", remote.url) as resp:
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        with tmp.open("wb") as out:
            for chunk in resp.iter_bytes(chunk_size=1 << 20):
                out.write(chunk)
                sha.update(chunk)
    if "text/html" in content_type and target.suffix.lower() not in (".html", ".htm"):
        tmp.unlink()
        raise ValueError(f"Got an HTML page instead of a data file from {remote.url}")
    tmp.replace(target)
    return _entry(remote, target, sha.hexdigest())


def _entry(remote: RemoteFile, target: Path, sha256: str) -> dict[str, Any]:
    return {
        "url": remote.url,
        "path": str(target.relative_to(RAW_DIR)),
        "bytes": target.stat().st_size,
        "sha256": sha256,
        "downloaded_at": datetime.fromtimestamp(target.stat().st_mtime, UTC).isoformat(),
    }


def _sha256_of(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def load_manifest() -> dict[str, Any]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"sources": {}}


def save_manifest(manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = datetime.now(UTC).isoformat()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def download_all(
    config: dict[str, Any], only: list[str] | None = None, force: bool = False
) -> bool:
    """Download every configured source. Returns False if a required source failed."""
    manifest = load_manifest()
    ok = True
    ssl_ctx = build_ssl_context(config.get("extra_ca_file"))
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(
        verify=ssl_ctx, timeout=TIMEOUT, follow_redirects=True, headers=headers
    ) as client:
        for key, spec in config["sources"].items():
            if only and key not in only:
                continue
            optional = spec.get("optional", False)
            print(f"[{key}]")
            previous = {f["path"]: f for f in manifest["sources"].get(key, {}).get("files", [])}
            record: dict[str, Any] = {"status": "ok", "files": [], "errors": []}
            if spec["type"] == "stac_ndvi_composite":
                ok &= _download_composite(client, key, spec, force, previous, record, optional)
                manifest["sources"][key] = record
                continue
            try:
                remotes = resolve_files(client, config["ckan_api"], spec)
            except Exception as exc:  # noqa: BLE001 - reported in the manifest
                remotes = []
                record["errors"].append(f"resolve: {exc}")
            for remote in remotes:
                target = RAW_DIR / key / remote.filename
                rel = str(target.relative_to(RAW_DIR))
                if target.exists() and not force:
                    entry = previous.get(rel) or _entry(remote, target, _sha256_of(target))
                    record["files"].append(entry)
                    print(f"  skip  {rel} (exists)")
                    continue
                try:
                    record["files"].append(fetch(client, remote, target))
                    print(f"  ok    {rel} ({target.stat().st_size / 1e6:.1f} MB)")
                except Exception as exc:  # noqa: BLE001 - reported in the manifest
                    record["errors"].append(f"{remote.url}: {exc}")
                    print(f"  FAIL  {rel}: {exc}")
            # Keep files from earlier runs that the source no longer lists (e.g. dated snapshots)
            listed = {f["path"] for f in record["files"]}
            record["files"] += [
                f for p, f in previous.items() if p not in listed and (RAW_DIR / p).exists()
            ]
            if record["errors"]:
                record["status"] = "partial" if record["files"] else "failed"
                if not optional:
                    ok = False
            manifest["sources"][key] = record
    save_manifest(manifest)
    return ok


def _download_composite(
    client: httpx.Client,
    key: str,
    spec: dict[str, Any],
    force: bool,
    previous: dict[str, Any],
    record: dict[str, Any],
    optional: bool,
) -> bool:
    """Satellite composite (built from many scenes, cached as one file). Fills `record`."""
    target = RAW_DIR / key / spec["filename"]
    rel = str(target.relative_to(RAW_DIR))
    if target.exists() and not force and rel in previous:
        record["files"].append(previous[rel])
        print(f"  skip  {rel} (exists)")
        return True
    try:
        record["files"].append(satellite.download_ndvi_composite(client, spec, target))
        print(f"  ok    {rel} ({target.stat().st_size / 1e6:.1f} MB)")
        return True
    except Exception as exc:  # noqa: BLE001 - reported in the manifest
        record["errors"].append(f"{spec['stac_api']}: {exc}")
        record["status"] = "failed"
        print(f"  FAIL  {rel}: {exc}")
        return optional
