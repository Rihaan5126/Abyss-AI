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
    assert "reveal" not in (UI / "explorer.js").read_text(encoding="utf-8").lower()
