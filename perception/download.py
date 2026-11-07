"""Bounded FathomNet downloads with attribution, licence filtering and crop manifests."""

from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import logging
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image

from .preprocess import crop_organism
from .dataset import read_manifest

API = "https://database.fathomnet.org/api/images/query/concept/"
DEFAULT_LICENSES = ("CC-BY-4.0", "CC0-1.0")
LOGGER = logging.getLogger(__name__)


def fetch_bytes(url: str, max_bytes=40_000_000) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("Only HTTPS image sources are supported")
    request = Request(url, headers={"User-Agent": "ABYSS-research-prototype/0.1"})
    with urlopen(request, timeout=40) as response:
        payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError(f"Response exceeds {max_bytes} bytes")
    return payload


def download_categories(categories: list[str], output: str | Path, per_category=20,
                        seed=42, allowed_licenses=DEFAULT_LICENSES) -> Path:
    if per_category < 1 or not categories or len(set(categories)) != len(categories):
        raise ValueError("Choose unique categories and a positive per-category limit")
    output = Path(output).resolve()
    (output / "crops").mkdir(parents=True, exist_ok=True)
    (output / "metadata").mkdir(exist_ok=True)
    rows, failures, originals_seen = [], [], set()
    for category in categories:
        metadata_path = output / "metadata" / f"{hashlib.sha256(category.encode()).hexdigest()}.json"
        if not metadata_path.exists():
            metadata_path.write_bytes(fetch_bytes(API + quote(category, safe="")))
        records = json.loads(metadata_path.read_text())
        # Stable seeded order, independent of API ordering; one crop per original.
        records.sort(key=lambda r: hashlib.sha256(f"{seed}:{r['uuid']}".encode()).hexdigest())
        count = 0
        for record in records:
            if count >= per_category:
                break
            if record.get("imageLicense") not in allowed_licenses:
                continue
            boxes = [b for b in record.get("boundingBoxes", [])
                     if b.get("concept", "").casefold() == category.casefold()
                     and b.get("annotationLicense") in allowed_licenses
                     and not b.get("groupOf")]
            if not boxes or record["uuid"] in originals_seen:
                continue
            box = sorted(boxes, key=lambda b: b["uuid"])[0]
            try:
                payload = fetch_bytes(record["url"])
                original_sha = hashlib.sha256(payload).hexdigest()
                if original_sha in originals_seen:
                    continue
                with Image.open(BytesIO(payload)) as image:
                    crop = crop_organism(image, box)
                sample_id = f"{record['uuid']}_{box['uuid']}"
                crop_path = output / "crops" / f"{sample_id}.png"
                crop.save(crop_path)
                rows.append({
                    "sample_id": sample_id, "category": category,
                    "image_path": f"crops/{crop_path.name}", "image_uuid": record["uuid"],
                    "source_id": record["url"].rsplit("/", 1)[0],
                    "source_url": record["url"],
                    "fathomnet_url": f"https://database.fathomnet.org/imagery/{record['uuid']}",
                    "image_license": record["imageLicense"],
                    "annotation_license": box["annotationLicense"],
                    "attribution": record.get("contributorsEmail"),
                    "source_tags": record.get("tags", []),
                    "bbox": {k: box[k] for k in ("x", "y", "width", "height")},
                    "original_sha256": original_sha,
                    "crop_sha256": hashlib.sha256(crop_path.read_bytes()).hexdigest(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "local_analysis_only": "ND" in record["imageLicense"],
                })
                originals_seen.update((record["uuid"], original_sha))
                count += 1
            except (OSError, ValueError) as exc:
                failures.append({"category": category, "uuid": record["uuid"], "error": str(exc)})
                LOGGER.warning("Skipping %s: %s", record["uuid"], exc)
        LOGGER.info("%s: downloaded %d/%d crops", category, count, per_category)
    report = {"allowed_licenses": list(allowed_licenses), "failures": failures,
              "counts": {c: sum(r["category"] == c for r in rows) for c in categories}}
    (output / "download_report.json").write_text(json.dumps(report, indent=2) + "\n")
    manifest = output / "manifest.json"
    manifest.write_text(json.dumps(rows, indent=2) + "\n")
    missing = [c for c, n in report["counts"].items() if not n]
    if missing:
        raise ValueError(f"No eligible crops for {missing}. Inspect download_report.json and source licences")
    return manifest


def restore_manifest(manifest: str | Path, output: str | Path,
                     allowed_licenses=DEFAULT_LICENSES) -> Path:
    """Recreate a frozen data snapshot without querying a changing category API."""
    rows = read_manifest(manifest)
    output = Path(output).resolve()
    (output / "crops").mkdir(parents=True, exist_ok=True)
    restored = []
    for row in rows:
        if (row.get("image_license") not in allowed_licenses
                or row.get("annotation_license") not in allowed_licenses):
            raise ValueError(f"Source licence not allowed for {row['sample_id']}")
        sample_id = row["sample_id"]
        if Path(sample_id).name != sample_id or sample_id in {".", ".."}:
            raise ValueError("sample_id must be a plain filename component")
        payload = fetch_bytes(row["source_url"])
        if hashlib.sha256(payload).hexdigest() != row["original_sha256"]:
            raise ValueError(f"Source checksum changed for {sample_id}; refusing a different image")
        with Image.open(BytesIO(payload)) as image:
            crop = crop_organism(image, row["bbox"])
        relative = f"crops/{sample_id}.png"
        path = output / relative
        crop.save(path)
        restored.append({**row, "image_path": relative,
                         "crop_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    path = output / "manifest.json"
    path.write_text(json.dumps(restored, indent=2) + "\n")
    return path
