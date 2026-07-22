# Wedding Thank-You Pages

A personal thank-you page for every family, each at its own unguessable link, hosted free on GitHub Pages. You edit two files — a spreadsheet of families and one shared message — and every page regenerates automatically.

## The files you'll actually touch

**`families.csv`** — one row per family. Open it in Excel, Numbers, or Google Sheets (keep it saved as CSV).

| column | what it does |
|---|---|
| `slug` | The URL for their page. **Leave it blank** — the build invents an unguessable one (like `jones-family-1f15`) and writes it back into this file. Don't change a slug after you've sent someone their link. |
| `display_name` | The big heading: "The Jones Family" |
| `greeting` | How they're addressed in the letter: "Bob, Carol, Emma & Jack" |
| `photo` | Optional. A filename from `photos-original/` to use for this family. Blank = the default couple photo. |
| `photo_caption` | Optional caption under their photo. |
| `note` | Optional extra personal paragraph, shown in an accented block just for them. |
| `sent` | Yours to use as a checklist — put an ✓ or a date when you've sent their link. |

**`message.md`** — the shared heartfelt message everyone receives. Blank lines separate paragraphs. You can write `{{greeting}}` anywhere to weave their names into the middle of the message.

**`config.json`** — your names, initials for the wax-seal monogram, the wedding date (both the pretty text and `date_iso`, which drives the countdown and the calendar file), your site's URL once you have it, and the shared photo gallery: a list of `{ "file", "caption" }` entries shown as "A few of our favorite moments" on every page.

**`photos-original/`** — drop full-size photos here with filenames matching the gallery list (currently `chicago.jpg`, `fountain.jpg`, `shesaidyes.jpg`, `timessquare.jpg`, `sunset.jpg`, `flower.jpg`). The build resizes and compresses them automatically; you never need to prepare images. A gallery entry whose file is missing is simply skipped.

## One-time setup (about 15 minutes)

1. Create a free account at github.com, then create a **public** repository named `wedding-thanks`.
2. Upload everything in this folder to the repository (GitHub Desktop is the easiest way, or drag-and-drop on the GitHub website — make sure the `.github` folder comes along).
3. In the repository: **Settings → Pages → Build and deployment → Source → "GitHub Actions"**.
4. That's it. Every push now rebuilds and publishes the site automatically, usually in under a minute.
5. Your pages live at `https://YOUR-USERNAME.github.io/wedding-thanks/jones-family-1f15/` etc. Put that base URL into `site_url` in `config.json` (e.g. `https://YOUR-USERNAME.github.io/wedding-thanks`) so link previews and QR codes use full URLs.

After setup, your routine is just: edit `families.csv` or `message.md` → commit/push (or edit the file directly on github.com and press "Commit changes") → done. If a new family had a blank slug, the robot fills it in and you'll find their finished link in `links.csv` a minute later.

## Building on your own computer (optional)

If you'd like to preview before publishing:

```
pip install pillow
python build.py
```

Then open `site/index.html` in a browser (or run `python -m http.server -d site` and visit localhost:8000). Add `--qr` to also generate a QR-code image per family into `qr-codes/` (requires `pip install qrcode`, and `site_url` set in config).

## Sending the links

`links.csv` always holds the current list: family, greeting, full URL, and your `sent` checklist column. Text each family their link, or mail-merge from the CSV. The pages include link-preview tags, so texted links show "A note for The Jones Family" with your photo.

## Privacy notes

The repository and pages are public (that's what makes hosting free), so the protection is that links are unguessable — a random suffix means nobody can find another family's page by guessing names. Search engines are told to stay away (`noindex` on every page plus `robots.txt`), and no page anywhere links to the family pages, including the landing page at the site root. This is the same privacy model as a private-link photo album. Just avoid putting anything on a page you'd be uncomfortable with in the unlikely event a link gets forwarded.

## Changing the look

Everything visual lives in `template.html` — colors are defined once at the top in `:root` (ivory, ink, gold), so a whole different palette is a three-line change. Animations automatically switch off for guests who have "reduce motion" enabled on their phone.
