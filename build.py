#!/usr/bin/env python3
"""
Wedding thank-you page builder.

  python build.py            build everything into site/
  python build.py --qr       also generate a QR code image per family (needs `pip install qrcode`)

Reads:  config.json, families.csv, message.md, template.html, photos-original/
Writes: site/<slug>/index.html for every family, shared assets, links.csv,
        robots.txt, 404.html, and a generic landing page.

If a family's `slug` cell is blank, an unguessable slug is generated from
their display name plus a random suffix and written back into families.csv,
so you never have to invent slugs yourself.
"""

import csv, html, io, json, re, secrets, shutil, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).parent
SITE = ROOT / "site"
PHOTOS = ROOT / "photos-original"

# ---------------------------------------------------------------- helpers

def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    s = re.sub(r"^(the-)", "", s)
    suffix = secrets.token_hex(2)  # 4 hex chars -> 65k combos per name
    return f"{s}-{suffix}"

def esc(s: str) -> str:
    return html.escape(s or "", quote=True)

def paragraphs(text: str, greeting: str) -> str:
    text = text.replace("{{greeting}}", greeting)
    paras = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return "\n".join(f"      <p>{esc(p)}</p>" for p in paras)

# ---------------------------------------------------------------- photos

def process_photo(src: Path, dest_dir: Path, max_w: int = 1100):
    """Resize + recompress a photo. Returns (filename, width, height) or None."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        print("  ! Pillow not installed (pip install pillow) — copying photo as-is")
        out = dest_dir / src.name
        shutil.copy2(src, out)
        return (out.name, 0, 0)
    im = Image.open(src)
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "P", "LA"):
        im = im.convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    out = dest_dir / (src.stem + ".jpg")
    im.save(out, "JPEG", quality=78, optimize=True, progressive=True)
    return (out.name, im.width, im.height)

# ---------------------------------------------------------------- build

def main():
    make_qr = "--qr" in sys.argv

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    template = (ROOT / "template.html").read_text(encoding="utf-8")
    message = (ROOT / "message.md").read_text(encoding="utf-8")

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "assets").mkdir(parents=True)
    (SITE / "photos").mkdir()

    # shared assets (fonts)
    for f in (ROOT / "assets").iterdir():
        shutil.copy2(f, SITE / "assets" / f.name)

    # process every photo once, shared by all pages
    photo_files = {}
    if PHOTOS.exists():
        for src in sorted(PHOTOS.iterdir()):
            if src.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
                info = process_photo(src, SITE / "photos")
                if info:
                    photo_files[src.name] = info
                    photo_files[src.stem] = info  # allow "jones" as well as "jones.jpg"
                    print(f"  photo: {src.name} -> photos/{info[0]}")

    # families
    rows = []
    with (ROOT / "families.csv").open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        for row in reader:
            if not (row.get("display_name") or "").strip():
                continue
            rows.append({k: (v or "").strip() for k, v in row.items()})

    # assign slugs where missing, write back
    changed = False
    for row in rows:
        if not row.get("slug"):
            row["slug"] = slugify(row["display_name"])
            changed = True
    if changed:
        with (ROOT / "families.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print("  wrote generated slugs back into families.csv")

    site_url = (cfg.get("site_url") or "").rstrip("/")
    links = []

    # calendar file shared by every page
    ics_summary = cfg.get("ics_summary") or f"{cfg['couple']}'s Wedding"
    ics_name = re.sub(r"[^A-Za-z0-9]+", "-", ics_summary).strip("-") + ".ics"
    date_iso = cfg.get("date_iso") or ""
    if date_iso:
        from datetime import date, timedelta
        d0 = date.fromisoformat(date_iso)
        d1 = d0 + timedelta(days=1)
        (SITE / "wedding.ics").write_text(
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//wedding-thanks//EN\r\n"
            "BEGIN:VEVENT\r\n"
            f"UID:wedding-{d0.strftime('%Y%m%d')}@thanks\r\n"
            f"DTSTAMP:{d0.strftime('%Y%m%d')}T000000Z\r\n"
            f"DTSTART;VALUE=DATE:{d0.strftime('%Y%m%d')}\r\n"
            f"DTEND;VALUE=DATE:{d1.strftime('%Y%m%d')}\r\n"
            f"SUMMARY:{ics_summary}\r\n"
            "END:VEVENT\r\nEND:VCALENDAR\r\n", encoding="utf-8")

    for row in rows:
        slug = row["slug"]
        greeting = row.get("greeting") or row["display_name"]
        page_dir = SITE / slug
        page_dir.mkdir()

        # gallery: optional per-family photo first, then the shared moments
        items = []
        if row.get("photo"):
            items.append({"file": row["photo"],
                          "caption": row.get("photo_caption") or ""})
        items += cfg.get("gallery", [])
        tilts = [-2, 1.6, -1.4, 2, -1.8, 1.2]
        figs, og_photo = [], None
        for i, g in enumerate(items):
            info = photo_files.get(g["file"]) or photo_files.get(Path(g["file"]).stem)
            if not info:
                continue
            name, pw, ph = info
            if og_photo is None:
                og_photo = name
            dims = f'width="{pw}" height="{ph}" ' if pw else ""
            cap = f"\n      <figcaption>{esc(g.get('caption') or '')}</figcaption>" if g.get("caption") else ""
            figs.append(
                '    <figure class="polaroid fade-up" style="--tilt:%sdeg">\n'
                '      <img src="{{ROOT}}photos/%s" alt="%s" %sloading="lazy" decoding="async">%s\n'
                '    </figure>' % (tilts[i % len(tilts)], name, esc(cfg["couple"]), dims, cap)
            )
        if figs:
            photo_html = (
                '  <section class="moments">\n'
                '    <div class="orn fade-up">\n'
                '      <span class="line"></span>\n'
                '      <svg width="11" height="11" viewBox="0 0 10 10" fill="currentColor" aria-hidden="true"><path d="M5 0l1.6 3.4L10 5 6.6 6.6 5 10 3.4 6.6 0 5l3.4-1.6z"/></svg>\n'
                '      <span class="line"></span>\n'
                '    </div>\n'
                '    <h2 class="fade-up">A few of our favorite moments</h2>\n'
                '    <p class="sub fade-up">and we are so glad you are part of the next one</p>\n'
                '    <div class="gal">\n' + "\n".join(figs) + '\n    </div>\n'
                '  </section>'
            )
        else:
            photo_html = ""
        photo_name = og_photo

        note = row.get("note") or ""
        note_html = f'    <div class="note fade-up"><p>{esc(note)}</p></div>' if note else ""

        og_image = ""
        if site_url and photo_name:
            og_image = f'<meta property="og:image" content="{site_url}/photos/{photo_name}">'

        page = (template
            .replace("{{TITLE_NAME}}", esc(row["display_name"]))
            .replace("{{GREETING}}", esc(greeting))
            .replace("{{MESSAGE_HTML}}", paragraphs(message, esc(greeting)))
            .replace("{{NOTE_HTML}}", note_html)
            .replace("{{GALLERY_HTML}}", photo_html)
            .replace("{{DATE_ISO}}", cfg.get("date_iso") or "")
            .replace("{{ICS_NAME}}", ics_name)
            .replace("{{COUPLE}}", esc(cfg["couple"]))
            .replace("{{COUPLE_SHORT}}", esc(cfg.get("couple_short") or cfg["couple"]))
            .replace("{{COUPLE_CAPS}}", esc(cfg["couple"]))
            .replace("{{INITIALS}}", esc(cfg.get("initials") or ""))
            .replace("{{DATE_TEXT}}", esc(cfg.get("wedding_date") or ""))
            .replace("{{DATE_SHORT}}", esc(cfg.get("date_short") or cfg.get("wedding_date") or ""))
            .replace("{{OG_IMAGE}}", og_image)
            .replace("{{ROOT}}", "../"))
        (page_dir / "index.html").write_text(page, encoding="utf-8")

        url = f"{site_url}/{slug}/" if site_url else f"/{slug}/"
        links.append({"display_name": row["display_name"], "greeting": greeting,
                      "url": url, "sent": row.get("sent", "")})
        print(f"  page:  /{slug}/  ({row['display_name']})")

    # links.csv for mail-merge / texting
    with (ROOT / "links.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["display_name", "greeting", "url", "sent"])
        w.writeheader()
        w.writerows(links)

    # optional QR codes
    if make_qr:
        try:
            import qrcode
            qr_dir = ROOT / "qr-codes"
            qr_dir.mkdir(exist_ok=True)
            for l in links:
                if not site_url:
                    print("  ! set site_url in config.json to generate QR codes"); break
                img = qrcode.make(l["url"])
                safe = re.sub(r"[^a-z0-9-]+", "-", l["display_name"].lower()).strip("-")
                img.save(qr_dir / f"{safe}.png")
            else:
                print(f"  QR codes -> qr-codes/")
        except ImportError:
            print("  ! qrcode not installed (pip install qrcode) — skipped")

    # robots.txt, 404, landing page
    (SITE / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    generic = (template
        .replace("{{TITLE_NAME}}", "Our Wonderful Guests")
        .replace("{{GREETING}}", "friends and family")
        .replace("{{MESSAGE_HTML}}", paragraphs(message, "friends and family"))
        .replace("{{NOTE_HTML}}", "")
        .replace("{{GALLERY_HTML}}", "")
        .replace("{{DATE_ISO}}", cfg.get("date_iso") or "")
        .replace("{{ICS_NAME}}", ics_name)
        .replace("{{COUPLE}}", esc(cfg["couple"]))
        .replace("{{COUPLE_SHORT}}", esc(cfg.get("couple_short") or cfg["couple"]))
        .replace("{{COUPLE_CAPS}}", esc(cfg["couple"]))
        .replace("{{INITIALS}}", esc(cfg.get("initials") or ""))
        .replace("{{DATE_TEXT}}", esc(cfg.get("wedding_date") or ""))
        .replace("{{DATE_SHORT}}", esc(cfg.get("date_short") or cfg.get("wedding_date") or ""))
        .replace("{{OG_IMAGE}}", "")
        .replace("{{ROOT}}", "./"))
    (SITE / "index.html").write_text(generic, encoding="utf-8")
    (SITE / "404.html").write_text(generic, encoding="utf-8")

    print(f"\nBuilt {len(links)} page(s) into site/ — links written to links.csv")

if __name__ == "__main__":
    main()
