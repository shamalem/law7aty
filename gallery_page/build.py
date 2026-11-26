"""Build the static gallery page from the photos in gallery_photos/.

Usage: python3 gallery_page/build.py
Writes gallery_page/index.html and gallery_page/files.json
(files.json maps each published photo path to its source file).
"""
import html
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHOTOS = ROOT / "gallery_photos"
OUT = Path(__file__).resolve().parent
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
INSTAGRAM = "https://www.instagram.com/law7atiii"


def artist_name(stem: str) -> str:
    s = stem.replace("_", " ").strip()
    s = re.sub(r"^\d+\s*", "", s)          # leading timestamp
    if re.match(r"(?i)^(img|dsc|pxl|photo|image|whatsapp|screenshot)\b", s):
        return ""
    s = re.sub(r"[\s\-–(]*\d+\)?$", "", s)  # trailing counter
    s = s.strip(" -–")
    return s if re.search(r"[^\W\d_]", s) else ""


def added_time(p: Path) -> int:
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%ct", "-1", "--", str(p)],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
        return int(out) if out else int(p.stat().st_mtime)
    except Exception:
        return int(p.stat().st_mtime)


def main():
    photos = [p for p in PHOTOS.iterdir() if p.suffix.lower() in EXTS] if PHOTOS.exists() else []
    photos.sort(key=lambda p: (-added_time(p), p.name))
    items, files = [], {}
    for i, p in enumerate(photos, 1):
        pub = f"photos/{i:03d}{p.suffix.lower()}"
        files[pub] = str(p.relative_to(ROOT))
        items.append({"src": pub, "name": artist_name(p.stem)})

    template = (OUT / "template.html").read_text(encoding="utf-8")
    page = (template
            .replace("__ITEMS__", json.dumps(items, ensure_ascii=False))
            .replace("__COUNT__", str(len(items)))
            .replace("__INSTAGRAM__", html.escape(INSTAGRAM)))
    (OUT / "index.html").write_text(page, encoding="utf-8")
    files["logo.png"] = "static/logo.png"
    (OUT / "files.json").write_text(json.dumps(files, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(items)} photos")


if __name__ == "__main__":
    main()
