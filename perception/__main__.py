"""Run with python -m perception --help; no model downloads during import."""

import argparse
import hashlib
import json
import logging
from pathlib import Path
from importlib.metadata import version

from .dataset import make_splits, read_manifest
from .download import DEFAULT_LICENSES, download_categories, restore_manifest
from .embed import CachedEncoder, DINO_REVISION, DinoV2Encoder
from .evaluate import evaluate, fit_perception
from .perception import Perception


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


def encoder_for(args):
    return CachedEncoder(DinoV2Encoder(
        revision=args.revision, cache_dir=args.model_cache, offline=args.offline,
        device=args.device,
    ), args.embedding_cache)


def main(argv=None):
    parser = argparse.ArgumentParser(description="ABYSS marine reference-unfamiliarity pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download", help="Download attributed FathomNet crops")
    download.add_argument("--categories", nargs="+", required=True)
    download.add_argument("--output", default="data/fathomnet")
    download.add_argument("--per-category", type=int, default=20)
    download.add_argument("--seed", type=int, default=42)
    download.add_argument("--allow-license", nargs="+", default=list(DEFAULT_LICENSES),
                          help="Explicit image AND annotation licence allowlist; ND crops stay local")
    restore = commands.add_parser("restore", help="Fetch exact images from a frozen, checksummed manifest")
    restore.add_argument("manifest")
    restore.add_argument("--output", default="data/restored")
    restore.add_argument("--allow-license", nargs="+", default=list(DEFAULT_LICENSES))
    split = commands.add_parser("split", help="Create source-disjoint splits before fitting")
    split.add_argument("manifest")
    split.add_argument("--familiar", nargs="+", required=True)
    split.add_argument("--seed", type=int, default=42)
    split.add_argument("--output", default="data/fathomnet/splits.json")
    prepare = commands.add_parser("prepare-model", help="Download DINOv2 once for later offline use")
    fit = commands.add_parser("fit", help="Build references and calibrate on familiar validation only")
    fit.add_argument("manifest")
    fit.add_argument("--familiar", nargs="+", required=True)
    fit.add_argument("--false-alert-rate", type=float, default=.05)
    fit.add_argument("--artifact", default="data/perception")
    test = commands.add_parser("evaluate", help="Measure held-out familiar and unknown performance")
    test.add_argument("manifest")
    test.add_argument("--artifact", default="data/perception")
    test.add_argument("--output", default="results/perception.json")
    predict = commands.add_parser("predict", help="Image-only inference, suitable for simulator integration")
    predict.add_argument("image")
    predict.add_argument("--artifact", default="data/perception")
    gallery = commands.add_parser("gallery", help="Write a local diagnostic image gallery from an evaluation")
    gallery.add_argument("report")
    gallery.add_argument("--output", default="results/gallery.html")
    for command in (prepare, fit, test, predict):
        command.add_argument("--offline", action="store_true")
        command.add_argument("--revision", default=DINO_REVISION, help="Pinned Hugging Face model commit")
        command.add_argument("--model-cache", default=".cache/huggingface")
        command.add_argument("--embedding-cache", default=".cache/embeddings")
        command.add_argument("--device", default="cpu")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "download":
            print(download_categories(args.categories, args.output, args.per_category,
                                      args.seed, args.allow_license))
        elif args.command == "restore":
            print(restore_manifest(args.manifest, args.output, args.allow_license))
        elif args.command == "split":
            rows = make_splits(read_manifest(args.manifest), args.familiar, args.seed)
            write_json(args.output, rows)
            write_json(str(args.output) + ".config.json", {
                "seed": args.seed, "familiar": args.familiar,
                "source_manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
                "retained_samples": len(rows),
            })
            print(args.output)
        elif args.command == "gallery":
            from .gallery import write_gallery
            write_gallery(json.loads(Path(args.report).read_text()), args.output)
            print(args.output)
        else:
            encoder = encoder_for(args)
            if args.command == "prepare-model":
                print(encoder.identity)
            elif args.command == "fit":
                rows = read_manifest(args.manifest)
                perception = fit_perception(rows, args.familiar, encoder, args.false_alert_rate)
                perception.save(args.artifact)
                write_json(Path(args.artifact) / "provenance.json", {
                    "manifest_sha256": hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest(),
                    "familiar": args.familiar, "false_alert_rate": args.false_alert_rate,
                    "software_versions": {p: version(p) for p in (
                        "numpy", "Pillow", "scikit-learn", "torch", "transformers")},
                    "reference_sample_ids": [r["sample_id"] for r in rows if r["split"] == "reference"],
                    "calibration_sample_ids": [r["sample_id"] for r in rows if r["split"] == "validation"],
                })
                print(json.dumps({"artifact": args.artifact, "threshold": perception.threshold}))
            elif args.command == "evaluate":
                provenance = json.loads((Path(args.artifact) / "provenance.json").read_text())
                digest = hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest()
                if digest != provenance["manifest_sha256"]:
                    raise ValueError("Evaluation manifest differs from the frozen fit manifest")
                report = evaluate(Perception.load(args.artifact, encoder),
                                  read_manifest(args.manifest), provenance["familiar"])
                report["provenance"] = provenance
                write_json(args.output, report)
                print(json.dumps({k: v for k, v in report.items() if k != "predictions"}, indent=2))
            elif args.command == "predict":
                print(json.dumps(Perception.load(args.artifact, encoder).predict(args.image).to_dict(), indent=2))
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
