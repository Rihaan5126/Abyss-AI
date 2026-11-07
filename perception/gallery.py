"""Local evaluation report; labelled truth here must not enter planner state."""

from html import escape
from pathlib import Path


def write_gallery(report: dict, output: str | Path):
    cards = []
    for row in report["predictions"]:
        image = Path(row["image_reference"]).resolve().as_uri()
        source_url = row.get("source_url") or ""
        source = (f'<a href="{escape(source_url, quote=True)}">Original image</a>'
                  if source_url.startswith("https://") else "Source unavailable")
        cards.append(f'''<article><img src="{escape(image, quote=True)}" alt="Organism crop">
<h2>{escape(row['true_category'])}</h2>
<p>Prediction: {escape(row['predicted_category'] or 'Reference-unfamiliar')}</p>
<p>Novelty: {row['novelty_score']:.3f} · Unknown: {row['is_unknown']}</p>
<p>Held-out category: {row['true_unknown']}</p>
<p>{escape(row.get('attribution') or 'Attribution in source manifest')} ·
{escape(row.get('image_license') or 'See source licence')} · {source}</p></article>''')
    metrics = " · ".join(f"{escape(key)}: {report[key]:.3f}" for key in (
        "familiar_classification_accuracy", "unknown_category_recall", "false_novelty_alert_rate", "novelty_auroc"))
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ABYSS · Local perception evaluation</title>
<style>body{{background:#071923;color:#ddf4f5;font:16px system-ui;max-width:1200px;margin:40px auto;padding:20px}}
main{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}}
article{{background:#102b38;padding:16px;border-radius:12px}}img{{width:100%;height:200px;object-fit:contain}}
h2{{font-size:20px}}p{{color:#b8d4db}}</style><h1>ABYSS · Perception evaluation</h1>
<p>Local analysis only. Crops may have restrictive source licences; do not publish this gallery.</p>
<p>Actual held-out results · Reference-unfamiliarity does not mean a new species.</p>
<p>{metrics}</p><main>{''.join(cards)}</main></html>'''
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html)
