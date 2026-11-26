"""Build the static gallery page from the photos in gallery_photos/.

Usage: python3 gallery_page/build.py
If gallery_photos/gallery.csv (an export of the student_gallery table) exists,
its rows give the order and the artist names; each row is matched to a photo
by the file name at the end of image_url. Photos with no row come after them,
named from their file name.
Writes gallery_page/index.html and gallery_page/files.json
(files.json maps each published photo path to its source file).
"""
import csv
import html
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote

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
    ordered, used = [], set()  # (photo, artist name)
    table = PHOTOS / "gallery.csv"
    if table.exists():
        with table.open(encoding="utf-8-sig", newline="") as f:
            rows = sorted(csv.DictReader(f), key=lambda r: -int(r.get("id") or 0))
        missing = []
        for r in rows:
            fname = unquote((r.get("image_url") or "").rsplit("/", 1)[-1]).lower()
            # exact name, or a download that dropped/added the timestamp prefix
            p = next((q for q in photos if q.name.lower() == fname), None) or next(
                (q for q in photos if fname.endswith(q.name.lower()) or q.name.lower().endswith(fname)), None)
            if p is None or p in used:
                missing.append(fname)
                continue
            used.add(p)
            ordered.append((p, (r.get("student_name") or "").strip()))
        if missing:
            print("no photo file for:", ", ".join(missing))
    ordered += [(p, artist_name(p.stem)) for p in photos if p not in used]

    items, files = [], {}
    for i, (p, name) in enumerate(ordered, 1):
        pub = f"photos/{i:03d}{p.suffix.lower()}"
        files[pub] = str(p.relative_to(ROOT))
        items.append({"src": pub, "name": name})

    template = (OUT / "template.html").read_text(encoding="utf-8")
    page = (template
            .replace("__ITEMS__", json.dumps(items, ensure_ascii=False))
            .replace("__COUNT__", str(len(items)))
            .replace("__INSTAGRAM__", html.escape(INSTAGRAM)))
    (OUT / "index.html").write_text(page, encoding="utf-8")
    files["logo.png"] = "gallery_page/logo-square.png"
    (OUT / "files.json").write_text(json.dumps(files, ensure_ascii=False, indent=1), encoding="utf-8")

    # Standalone copy for static hosting (GitHub Pages etc.): full HTML document + files.
    site = OUT / "site"
    shutil.rmtree(site, ignore_errors=True)
    (site / "photos").mkdir(parents=True)
    for pub, src in files.items():
        shutil.copy(ROOT / src, site / pub)
    head, _, body = page.partition("</style>")
    (site / "index.html").write_text(
        '<!doctype html>\n<html lang="ar" dir="rtl">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<link rel="icon" href="logo.png">\n'
        + head + "\n  *, *::before, *::after { box-sizing: border-box; }\n"
        "  body { margin: 0; }\n  img { max-width: 100%; }\n</style>\n</head>\n<body>\n"
        + body + "\n</body>\n</html>\n",
        encoding="utf-8",
    )
    (site / ".nojekyll").write_text("")
    print(f"{len(items)} photos")


if __name__ == "__main__":
    main()
