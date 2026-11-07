"""Local evaluation report; labelled truth here must not enter planner state."""

from html import escape
from pathlib import Path
import hashlib
import shutil
from .quality import diagnostics, error_kind


def write_gallery(report: dict, output: str | Path):
    output = Path(output)
    assets = output.parent / (output.stem + '-images')
    assets.mkdir(parents=True, exist_ok=True)
    def local_image(path):
        source = Path(path).resolve()
        filename = hashlib.sha256(source.read_bytes()).hexdigest() + source.suffix
        target = assets / filename
        if not target.exists(): shutil.copyfile(source, target)
        return assets.name + '/' + filename
    cards = []
    for row in report["predictions"]:
        image = local_image(row["image_reference"])
        reference = local_image(row['nearest_reference'])
        source_url = row.get("source_url") or ""
        source = (f'<a href="{escape(source_url, quote=True)}">Original image</a>'
                  if source_url.startswith("https://") else "Source unavailable")
        cards.append(f'''<article><strong>{escape(error_kind(row))}</strong>
<p>Input crop</p><img src="{escape(image, quote=True)}" alt="Organism crop">
<p>Nearest reference (may differ from a voting prediction)</p><img src="{escape(reference, quote=True)}" alt="Nearest reference">
<h2>{escape(row['true_category'])}</h2>
<p>Prediction: {escape(row['predicted_category'] or 'Reference-unfamiliar')}</p>
<p>Novelty: {row['novelty_score']:.3f} · Unknown: {row['is_unknown']}</p>
<p>Similarity: {row['similarity_score']:.3f} · Threshold: {report['threshold']:.3f}</p>
<p>Held-out category: {row['true_unknown']}</p>
<p>{escape(row.get('attribution') or 'Attribution in source manifest')} ·
{escape(row.get('image_license') or 'See source licence')} · {source}</p></article>''')
    metrics = " · ".join(f"{escape(key)}: {report[key]:.3f}" for key in (
        "familiar_classification_accuracy", "unknown_category_recall", "false_novelty_alert_rate", "novelty_auroc"))
    detail = diagnostics(report['predictions'])
    table = '<table><tr><th>True category</th><th>Images</th><th>Precision</th><th>Recall</th><th>Unfamiliar flags</th></tr>'
    for label, stats in detail['per_category'].items():
        table += f"<tr><td>{escape(label)}</td><td>{stats['count']}</td><td>{stats['precision']:.2f}</td><td>{stats['recall']:.2f}</td><td>{stats['unfamiliar_flags']}/{stats['count']}</td></tr>"
    table += '</table>'
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ABYSS · Local perception evaluation</title>
<style>body{{background:#071923;color:#ddf4f5;font:16px system-ui;max-width:1200px;margin:40px auto;padding:20px}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}}
article{{background:#102b38;padding:16px;border-radius:12px}}img{{width:100%;height:200px;object-fit:contain}}
h2{{font-size:20px}}p{{color:#b8d4db}}td,th{{padding:8px;text-align:left}}@media print{{body{{background:white;color:black}}p{{color:black}}article{{break-inside:avoid}}}}</style><h1>ABYSS · Perception evaluation</h1>
<p>Local analysis only. Crops may have restrictive source licences; do not publish this gallery.</p>
<p>Recorded evaluation results · Reference-unfamiliarity does not mean a new species.</p>
<p>{metrics}</p><p>Category precision/recall include unknown rejection. Unknown species rows have zero classification recall by design; use unknown recall to assess rejection.</p>{table}
<p>Use your browser Print command to save this local report as PDF. Image-level intervals do not establish independence across dives.</p>
<main>{''.join(cards)}</main></html>'''
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html)
