"""The demo must run offline, and the 3D view must not invent its own data."""

import json
import re
from pathlib import Path

UI = Path("ui")


def test_three_js_is_served_locally():
    html = (UI / "index.html").read_text(encoding="utf-8")
    block = re.search(r'<script type="importmap">(.*?)</script>', html, re.S).group(1)
    imports = json.loads(block)["imports"]
    assert not any(target.startswith("http") for target in imports.values())
    assert (UI / imports["three"]).exists()
    assert (UI / imports["three/addons/"] / "OrbitControls.js").exists()
    assert (UI / "vendor/three/LICENSE").exists()


def test_fonts_are_served_locally_with_licences():
    css = (UI / "style.css").read_text(encoding="utf-8")
    fonts = re.findall(r"url\((vendor/fonts/[^)]+)\)", css)
    assert len(fonts) >= 5
    assert all((UI / font).exists() for font in fonts)
    assert (UI / "vendor/fonts/LICENSE-instrument-serif").exists()
    assert (UI / "vendor/fonts/LICENSE-ibm-plex").exists()


def test_descent_is_labelled_illustrative():
    assert "descent is illustrative" in (UI / "index.html").read_text(encoding="utf-8")
    assert "descent is illustrative" in (UI / "app.js").read_text(encoding="utf-8")


def test_hidden_layer_guards_against_negative_smoothed_values():
    # A fractional power of an overshoot below zero gives NaN, which crashed Reveal.
    assert "Math.max(0, t) ** 0.55" in (UI / "explorer.js").read_text(encoding="utf-8")


def test_mode_is_always_shown_and_narration_handles_unfamiliar_images():
    app = (UI / "app.js").read_text(encoding="utf-8")
    assert 'id="mode-badge"' in (UI / "index.html").read_text(encoding="utf-8")
    assert "That does not mean a new species" in app
    assert "Something unfamiliar to its references" in app


def test_report_describes_the_planner_actually_compared():
    report = (UI / "report.js").read_text(encoding="utf-8")
    assert "STRATEGY[other.planner]" in report
    assert "not the published 6,300-mission" in report


def test_docs_point_to_main_rather_than_old_feature_branches():
    for path in Path("docs").glob("*.md"):
        assert "git switch ammar/" not in path.read_text(encoding="utf-8"), path
        assert "origin ammar/" not in path.read_text(encoding="utf-8"), path


def test_page_loads_nothing_from_other_hosts():
    for name in ("index.html", "app.js", "explorer.js", "style.css"):
        text = (UI / name).read_text(encoding="utf-8")
        for url in re.findall(r"""(?:src|href|import\(|from)\s*=?\s*["'](https?://[^"']+)""", text):
            raise AssertionError(f"{name} loads {url}")


def test_3d_view_says_it_is_a_visualisation():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert "not real footage" in html
    assert "exaggerated" in html
    assert "VERTICAL_EXAGGERATION = 3" in (UI / "explorer.js").read_text(encoding="utf-8")


def test_3d_view_never_loads_reveal_files_itself():
    code = (UI / "explorer.js").read_text(encoding="utf-8")
    for forbidden in ("fetch(", "XMLHttpRequest", ".reveal", "encounter_richness_map", "expected_richness_map"):
        assert forbidden not in code, forbidden
