"""Fit references/calibration separately from labelled, held-out evaluation."""

from collections import Counter

import numpy as np
from sklearn.metrics import roc_auc_score

from .dataset import validate_splits
from .novelty import ReferenceIndex, calibrate_threshold
from .perception import Perception


def fit_perception(rows, familiar, encoder, false_alert_rate=.05) -> Perception:
    validate_splits(rows, familiar)
    reference = [r for r in rows if r["split"] == "reference"]
    validation = [r for r in rows if r["split"] == "validation"]
    index = ReferenceIndex(encoder.encode([r["image_path"] for r in reference]),
                           [r["category"] for r in reference],
                           [r["image_path"] for r in reference])
    scores, _ = index.query(encoder.encode([r["image_path"] for r in validation]))
    return Perception(encoder, index, calibrate_threshold(scores, false_alert_rate))


def evaluate(perception: Perception, rows: list[dict], familiar: list[str]) -> dict:
    validate_splits(rows, familiar)
    test = [r for r in rows if r["split"] == "test"]
    predictions = []
    for row in test:
        result = perception.predict(row["image_path"]).to_dict()
        # This labelled payload belongs to evaluation/gallery, never planner state.
        predictions.append({"sample_id": row["sample_id"], "true_category": row["category"],
                            "true_unknown": row["category"] not in familiar,
                            "source_url": row.get("source_url"),
                            "source_id": row.get("source_id"),
                            "image_license": row.get("image_license"),
                            "annotation_license": row.get("annotation_license"),
                            "attribution": row.get("attribution"), **result})
    known = [r for r in predictions if not r["true_unknown"]]
    unknown = [r for r in predictions if r["true_unknown"]]
    # Report raw NN accuracy as well as accuracy after rejecting unfamiliar images.
    labels_by_reference = dict(zip(perception.index.references, perception.index.labels))
    return {
        "schema_version": 1,
        "encoder": perception.encoder.identity,
        "novelty_definition": "cosine distance to nearest familiar reference; not a probability",
        "threshold": perception.threshold,
        "counts": {"reference": sum(r["split"] == "reference" for r in rows),
                   "validation": sum(r["split"] == "validation" for r in rows),
                   "test_familiar": len(known), "test_unknown": len(unknown)},
        "test_category_counts": dict(Counter(r["category"] for r in test)),
        "familiar_nn_accuracy": float(np.mean([
            labels_by_reference[r["nearest_reference"]] == r["true_category"] for r in known])),
        "familiar_classification_accuracy": float(np.mean([
            r["predicted_category"] == r["true_category"] for r in known])),
        "unknown_category_recall": float(np.mean([r["is_unknown"] for r in unknown])),
        "false_novelty_alert_rate": float(np.mean([r["is_unknown"] for r in known])),
        "novelty_auroc": float(roc_auc_score(
            [r["true_unknown"] for r in predictions], [r["novelty_score"] for r in predictions])),
        "predictions": predictions,
        "limitations": ["Reference-unfamiliarity is not scientific species novelty.",
                        "Source grouping reduces, but cannot eliminate, near-duplicate leakage.",
                        "Small-sample results do not establish ecological or regional generalisation."],
    }
