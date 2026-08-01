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
from urllib.parse import quote

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

def salutation_for(row: dict) -> str:
    """The full 'Dear ...,' line for a family.

    Priority: an explicit `salutation` override (use verbatim, e.g. add
    'Uncle'/'Aunty' for elders) > a warm generic greeting for whole-household
    rows named 'The X Family' (so no elder is addressed by bare first name) >
    the first-name greeting for couples and individuals.
    """
    override = (row.get("salutation") or "").strip()
    if override:
        return f"Dear {esc(override)},"
    m = re.match(r"^The (.+?) Family$", (row.get("display_name") or "").strip())
    if m:
        return f"Dearest {esc(m.group(1))} family,"
    greeting = (row.get("greeting") or "").strip() or (row.get("display_name") or "").strip()
    return f"Dear {esc(greeting)},"

# ---------------------------------------------------------------- photos

def process_photo(src: Path, dest_dir: Path, max_w: int = 1000):
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
    im.save(out, "JPEG", quality=74, optimize=True, progressive=True)
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
    venue_name = cfg.get("venue_name") or ""
    venue_address = cfg.get("venue_address") or ""
    ics_location = ", ".join(p for p in (venue_name, venue_address) if p)
    if date_iso:
        from datetime import date, datetime, timedelta
        d0 = date.fromisoformat(date_iso)
        d1 = d0 + timedelta(days=1)

        def ics_esc(s):
            return s.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;")

        loc_line = f"LOCATION:{ics_esc(ics_location)}\r\n" if ics_location else ""
        start_t = cfg.get("ics_start_time") or ""
        tzid = cfg.get("ics_tzid") or "America/Chicago"

        if start_t:
            # timed event in the venue's local timezone (shows the same clock time everywhere)
            sh, sm = (int(x) for x in start_t.split(":")[:2])
            end_t = cfg.get("ics_end_time") or ""
            if end_t:
                eh, em = (int(x) for x in end_t.split(":")[:2])
                dt_end = datetime(d0.year, d0.month, d0.day, eh, em)
            else:
                dt_end = datetime(d0.year, d0.month, d0.day, sh, sm) + timedelta(hours=1, minutes=30)
            dt_start = datetime(d0.year, d0.month, d0.day, sh, sm)
            when = (
                f"DTSTART;TZID={tzid}:{dt_start.strftime('%Y%m%dT%H%M%S')}\r\n"
                f"DTEND;TZID={tzid}:{dt_end.strftime('%Y%m%dT%H%M%S')}\r\n"
            )
            # US-rules VTIMEZONE — correct for America/Chicago and other US zones
            vtimezone = (
                "BEGIN:VTIMEZONE\r\n"
                f"TZID:{tzid}\r\n"
                "BEGIN:DAYLIGHT\r\nTZOFFSETFROM:-0600\r\nTZOFFSETTO:-0500\r\nTZNAME:CDT\r\n"
                "DTSTART:19700308T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU\r\nEND:DAYLIGHT\r\n"
                "BEGIN:STANDARD\r\nTZOFFSETFROM:-0500\r\nTZOFFSETTO:-0600\r\nTZNAME:CST\r\n"
                "DTSTART:19701101T020000\r\nRRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU\r\nEND:STANDARD\r\n"
                "END:VTIMEZONE\r\n"
            )
        else:
            when = (
                f"DTSTART;VALUE=DATE:{d0.strftime('%Y%m%d')}\r\n"
                f"DTEND;VALUE=DATE:{d1.strftime('%Y%m%d')}\r\n"
            )
            vtimezone = ""

        (SITE / "wedding.ics").write_text(
            "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//wedding-thanks//EN\r\n"
            "CALSCALE:GREGORIAN\r\n"
            + vtimezone +
            "BEGIN:VEVENT\r\n"
            f"UID:wedding-{d0.strftime('%Y%m%d')}@thanks\r\n"
            f"DTSTAMP:{d0.strftime('%Y%m%d')}T000000Z\r\n"
            + when +
            f"SUMMARY:{ics_esc(ics_summary)}\r\n"
            + loc_line +
            "END:VEVENT\r\nEND:VCALENDAR\r\n", encoding="utf-8")

    # hero monogram letters, from initials ("A·B" -> "A", "B") or couple names
    mono = [p for p in re.split(r"[^A-Za-z0-9]+", cfg.get("initials") or "") if p]
    if len(mono) < 2:
        names = [w.strip() for w in (cfg.get("couple") or "").replace(" and ", " & ").split("&") if w.strip()]
        mono = [n[:1] for n in names]
    mono_l = mono[0] if mono else ""
    mono_r = mono[1] if len(mono) > 1 else ""

    # venue block for the save-the-date card (shared across pages)
    ceremony_time = cfg.get("ceremony_time") or ""
    venue_bits = []
    if ceremony_time:
        venue_bits.append(f'      <p class="venue-time">{esc(ceremony_time)}</p>')
    if venue_name:
        venue_bits.append(f'      <p class="venue-name">{esc(venue_name)}</p>')
    if venue_address:
        maps_url = "https://maps.google.com/?q=" + quote(ics_location or venue_address)
        venue_bits.append(
            f'      <a class="venue-addr" href="{maps_url}" target="_blank" rel="noopener">'
            f'{esc(venue_address)}</a>')
    venue_html = ('    <div class="venue">\n' + "\n".join(venue_bits) + "\n    </div>\n") if venue_bits else ""

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
            .replace("{{MONO_L}}", esc(mono_l))
            .replace("{{MONO_R}}", esc(mono_r))
            .replace("{{SALUTATION}}", salutation_for(row))
            .replace("{{GREETING}}", esc(greeting))
            .replace("{{MESSAGE_HTML}}", paragraphs(message, esc(greeting)))
            .replace("{{NOTE_HTML}}", note_html)
            .replace("{{VENUE_HTML}}", venue_html)
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
        .replace("{{MONO_L}}", esc(mono_l))
        .replace("{{MONO_R}}", esc(mono_r))
        .replace("{{SALUTATION}}", "Dear friends and family,")
        .replace("{{GREETING}}", "friends and family")
        .replace("{{MESSAGE_HTML}}", paragraphs(message, "friends and family"))
        .replace("{{NOTE_HTML}}", "")
        .replace("{{VENUE_HTML}}", venue_html)
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
