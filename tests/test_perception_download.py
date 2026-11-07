from io import BytesIO
import hashlib
import json

from PIL import Image
import pytest

from perception import download


def test_downloader_filters_licences_and_records_real_crop_provenance(tmp_path, monkeypatch):
    image = Image.new("RGB", (20, 20), "red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    payload = buffer.getvalue()

    def record(uuid, license="CC-BY-4.0"):
        return {
            "uuid": uuid, "url": f"https://example.test/dive/{uuid}.png",
            "imageLicense": license, "contributorsEmail": "source@example.test",
            "boundingBoxes": [{"uuid": uuid + "-box", "concept": "Jelly", "x": 2, "y": 3,
                               "width": 5, "height": 6, "annotationLicense": "CC-BY-4.0"}],
        }

    records = [record("allowed"), record("restricted", "CC-BY-NC-ND-4.0")]
    requests = []

    def fetch(url):
        requests.append(url)
        return json.dumps(records).encode() if url.startswith(download.API) else payload

    monkeypatch.setattr(download, "fetch_bytes", fetch)
    manifest = download.download_categories(["Jelly"], tmp_path)
    rows = json.loads(manifest.read_text())
    assert len(rows) == 1 and rows[0]["image_uuid"] == "allowed"
    assert rows[0]["source_id"] == "https://example.test/dive"
    assert rows[0]["image_license"] == "CC-BY-4.0"
    assert rows[0]["original_sha256"] and rows[0]["crop_sha256"]
    assert not rows[0]["local_analysis_only"]
    assert all("restricted.png" not in url for url in requests)
    with Image.open(tmp_path / rows[0]["image_path"]) as crop:
        assert crop.size == (5, 6)
    count = len(requests)
    download.download_categories(["Jelly"], tmp_path)
    assert len(requests) == count  # cached metadata and verified crop require no network


def test_downloader_reports_missing_eligible_images(tmp_path, monkeypatch):
    monkeypatch.setattr(download, "fetch_bytes", lambda _: b"[]")
    with pytest.raises(ValueError, match="No eligible crops"):
        download.download_categories(["jelly"], tmp_path)
    report = json.loads((tmp_path / "download_report.json").read_text())
    assert report["counts"] == {"jelly": 0}


def test_restore_recreates_exact_original_and_refuses_changed_sources(tmp_path, monkeypatch):
    buffer = BytesIO()
    Image.new("RGB", (20, 20), "blue").save(buffer, format="PNG")
    payload = buffer.getvalue()
    row = {"sample_id": "one", "category": "jelly", "image_path": "not-downloaded.png",
           "source_id": "dive-1", "source_url": "https://example.test/image.png",
           "image_license": "CC-BY-4.0", "annotation_license": "CC-BY-4.0",
           "original_sha256": hashlib.sha256(payload).hexdigest(),
           "bbox": dict(x=0, y=0, width=5, height=6), "split": "reference"}
    manifest = tmp_path / "snapshot.json"
    manifest.write_text(json.dumps([row]))
    monkeypatch.setattr(download, "fetch_bytes", lambda _: payload)
    restored = download.restore_manifest(manifest, tmp_path / "restored")
    rows = json.loads(restored.read_text())
    assert rows[0]["split"] == "reference"
    with Image.open(restored.parent / rows[0]["image_path"]) as image:
        assert image.size == (5, 6)
    monkeypatch.setattr(download, "fetch_bytes", lambda _: pytest.fail("Verified cache should avoid network"))
    download.restore_manifest(restored, tmp_path / "restored")
    monkeypatch.setattr(download, "fetch_bytes", lambda _: b"changed-image")
    with pytest.raises(ValueError, match="checksum changed"):
        download.restore_manifest(manifest, tmp_path / "changed")


def test_restore_checks_source_licence_before_downloading(tmp_path, monkeypatch):
    row = {"sample_id": "one", "category": "jelly", "image_path": "one.png",
           "source_id": "dive", "image_license": "CC-BY-NC-ND-4.0",
           "annotation_license": "CC-BY-NC-4.0"}
    manifest = tmp_path / "snapshot.json"
    manifest.write_text(json.dumps([row]))
    monkeypatch.setattr(download, "fetch_bytes", lambda _: pytest.fail("Must check licence first"))
    with pytest.raises(ValueError, match="licence not allowed"):
        download.restore_manifest(manifest, tmp_path / "restored")
