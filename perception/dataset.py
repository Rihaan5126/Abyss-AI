"""JSON manifests and deterministic source-disjoint reference/validation/test splits."""

from collections import Counter
import json
from pathlib import Path

import numpy as np


def read_manifest(path: str | Path) -> list[dict]:
    path = Path(path).resolve()
    rows = json.loads(path.read_text())
    if not isinstance(rows, list) or not rows:
        raise ValueError("Manifest must be a nonempty JSON list")
    for row in rows:
        for field in ("sample_id", "category", "image_path", "source_id"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise ValueError(f"Every sample requires a nonempty {field}")
        row["image_path"] = str((path.parent / row["image_path"]).resolve())
    if len({row["sample_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate sample_id in manifest")
    return rows


def validate_splits(rows: list[dict], familiar: list[str]):
    familiar_set = set(familiar)
    if not familiar_set or len(familiar_set) != len(familiar):
        raise ValueError("Familiar categories must be nonempty and unique")
    seen = {}
    for row in rows:
        split = row.get("split")
        if split not in {"reference", "validation", "test"}:
            raise ValueError("Each sample requires a reference, validation or test split")
        if split != "test" and row["category"] not in familiar_set:
            raise ValueError("Withheld categories must never enter reference or calibration")
        for field in ("source_id", "image_uuid", "original_sha256", "crop_sha256", "image_path", "near_duplicate_group"):
            value = row.get(field)
            if not value:
                continue
            key = (field, value)
            if key in seen and seen[key] != split:
                raise ValueError(f"Leakage across splits: shared {field}")
            seen[key] = split
    for split in ("reference", "validation", "test"):
        available = {r["category"] for r in rows if r["split"] == split}
        if not familiar_set <= available:
            raise ValueError(f"{split} is missing familiar categories: {sorted(familiar_set - available)}")
    if not any(r["category"] not in familiar_set for r in rows if r["split"] == "test"):
        raise ValueError("Test split needs at least one withheld category for unknown evaluation")


def make_splits(rows: list[dict], familiar: list[str], seed=42, test_sources=()) -> list[dict]:
    """Group by imaging source, merging duplicate originals across sources.

    Source IDs default to the image URL's parent (usually a dive archive).
    Review them before final evaluation; this is not a near-duplicate detector.
    Unknown rows in reference/validation source groups are discarded.
    """
    groups = sorted({r["source_id"] for r in rows})
    parent = {g: g for g in groups}

    def root(g):
        while parent[g] != g:
            parent[g] = parent[parent[g]]
            g = parent[g]
        return g

    duplicates = {}
    for row in rows:
        for field in ("image_uuid", "original_sha256", "crop_sha256", "image_path", "near_duplicate_group"):
            if value := row.get(field):
                key = (field, value)
                if key in duplicates:
                    parent[root(row["source_id"])] = root(duplicates[key])
                duplicates[key] = row["source_id"]
    groups = sorted({root(g) for g in groups})
    forced_test = {root(g) for g in test_sources}
    if len(groups) < 3:
        raise ValueError("Need at least three independent imaging sources; collect more dives")
    rng = np.random.default_rng(seed)
    n_val = max(1, round(.2 * len(groups)))
    n_test = max(1, round(.2 * len(groups)))
    for _ in range(5000):
        shuffled = list(rng.permutation(groups))
        assignments = {
            g: "validation" if i < n_val else "test" if i < n_val + n_test else "reference"
            for i, g in enumerate(shuffled)
        }
        assignments.update({g: 'test' for g in forced_test})
        output = []
        for row in rows:
            split = assignments[root(row["source_id"])]
            if row["category"] in familiar or split == "test":
                output.append({**row, "split": split})
        try:
            validate_splits(output, familiar)
        except ValueError:
            continue
        return output
    counts = Counter(r["category"] for r in rows)
    raise ValueError(f"Cannot form source-disjoint splits for {dict(counts)}; collect more independent dives")
