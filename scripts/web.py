"""
Web edition of «بيان الضاد في ممالك الخيال» for GitHub Pages.

The site is built from the very same rendered chapters and the same stylesheet as the printed book
(scripts/book.css, converted from print units to screen units), so the two editions cannot drift
apart: same typefaces, same chapter openings, same headings, tables, plates and colours.

  site/index.html         cover, the invitation to correct the book, table of contents, book card
  site/<section>.html     one page per part, chapter and appendix, with previous/next links
  site/assets, fonts, plates, cover images and the PDF

Fonts on the web:
  - IBM Plex Sans Arabic is served as files (OFL).
  - Thmanyah (headings) may be used on websites but its files may not be hosted for download, so it
    is embedded inside a stylesheet rather than published as font files, and never committed to the
    main branch (site/ is git-ignored; only the deployed gh-pages branch carries it).
  - The cover's display face is never shipped: the cover appears as an image.
"""

from __future__ import annotations

import base64
import html
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image

SCREEN_SCALE = 1.22          # print points/millimetres -> screen pixels, so 10.4 pt text reads at ~17 px
PDF_NAME = "arabic-game-localization-book.pdf"

FILE_FOR = {
    "preface": "preface", "sec_part1": "part-1", "sec_part2": "part-2",
    "app1": "plates", "app2": "timeline", "app3": "people", "refs": "references",
}

WEB_CSS = """
/* ==========================================================================
   Screen layout around the book's own styles
   ========================================================================== */
html { background: #e7e0d3; scroll-behavior: smooth; }
body.web { background: none; margin: 0; }
img { max-width: 100%; height: auto; }
a:hover { color: var(--accent); }

.topbar {
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 10px 22px;
  background: #3a2110; color: #e9cd90;
  border-bottom: 2px solid #b98f4a;
  font-family: var(--head);
}
.topbar a { color: inherit; }
.topbar a:hover { color: #fff3d6; }
.topbar .brand { font-weight: 900; font-size: 17px; }
.topbar nav { display: flex; gap: 20px; font-size: 14px; font-weight: 500; white-space: nowrap; }

.sheet {
  max-width: 860px; margin: 34px auto 0; padding: 30px 84px 70px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(40, 20, 5, 0.18), 0 18px 50px rgba(60, 30, 10, 0.14);
}
.book-section, .part-page, .fm-page { break-before: auto; break-after: auto; }
.part-page { height: auto; padding: 70px 0 50px; }
.part-page .part-kicker { margin-top: 0; }
.honor-roll-heading { margin-top: 56px; }
.table-wrap { overflow-x: auto; margin: 0 -8px; padding: 0 8px; }
.table-wrap table { min-width: 620px; }
.plate-img img { max-height: none; }
.toc-dots, .toc-page { display: none; }
h2[id], .ref-card, section[id] { scroll-margin-top: 72px; }
.ref-card:target, h2:target { background: #fbf2de; box-shadow: 0 0 0 6px #fbf2de; }
.cite-ref:hover { text-decoration: underline; }

.pager {
  max-width: 860px; margin: 0 auto; padding: 24px 84px 0;
  display: flex; justify-content: space-between; gap: 16px;
  font-family: var(--head);
}
.pager a { display: block; max-width: 47%; color: #3a2110; }
.pager .dir { display: block; font-size: 12px; font-weight: 500; color: var(--accent); }
.pager .ttl { font-weight: 700; font-size: 15px; line-height: 1.6; }
.pager .next { text-align: left; margin-right: auto; }
.site-foot {
  max-width: 860px; margin: 0 auto; padding: 26px 84px 56px;
  font-size: 13px; line-height: 1.9; color: #6b5a48;
}
.site-foot a { color: var(--accent); font-weight: 600; }

/* ---------- home page ---------- */
.hero { display: grid; grid-template-columns: minmax(0, 270px) 1fr; gap: 40px; align-items: center; padding: 26px 0 44px; }
.hero img { width: 100%; display: block; border-radius: 2px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3), 0 20px 44px rgba(50, 25, 8, 0.35); }
.hero .kicker { font-family: var(--head); font-size: 14px; font-weight: 500; color: var(--accent); }
.hero h1 { font-family: var(--head); font-weight: 900; font-size: 46px; line-height: 1.6; margin: 6px 0 0; }
.hero h1 span { display: block; }
.hero h1 .l2 { font-size: 34px; }
.hero .sub { font-size: 17px; line-height: 2; font-weight: 300; color: var(--ink-soft); margin: 14px 0 0; }
.hero .by { margin-top: 18px; font-family: var(--head); font-weight: 700; font-size: 18px; }
.hero .when { font-size: 13px; color: var(--ink-mute); }
.actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; font-family: var(--head); }
.btn { display: inline-block; padding: 9px 16px; border: 1.5px solid #3a2110; font-weight: 700; font-size: 14px; color: #3a2110; }
.btn.primary { background: #3a2110; color: #ecd39a; }
.btn:hover { background: #5a3317; color: #fff3d6; border-color: #5a3317; }
.web .colophon-note { margin: 6px 0 50px; }
.web .colophon-page { display: block; height: auto; text-align: right; }
#toc { margin-bottom: 56px; }
#toc .opener { padding-top: 0; }

@media (max-width: 760px) {
  .sheet { margin-top: 0; padding: 18px 20px 46px; box-shadow: none; }
  .pager, .site-foot { padding-left: 20px; padding-right: 20px; }
  .topbar { padding: 9px 14px; }
  .topbar .brand { font-size: 15px; }
  .topbar nav { gap: 14px; font-size: 13px; }
  .topbar nav .opt { display: none; }
  .hero { grid-template-columns: 1fr; gap: 26px; text-align: center; padding-top: 14px; }
  .hero img { max-width: 230px; margin: 0 auto; }
  .hero h1 { font-size: 36px; }
  .hero h1 .l2 { font-size: 27px; }
  .actions { justify-content: center; }
  .opener { padding-top: 26px; }
  .opener h1 { font-size: 26px; }
  .toc-sub { padding-right: 14px; }
  .toc-badge { min-width: 72px; }
  ul, ol { padding-right: 20px; }
}
"""


def to_screen_css(css: str, k: float = SCREEN_SCALE) -> str:
    """Print stylesheet -> screen: drops @page rules and converts pt/mm to px at one common scale."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)   # comments first: one of them mentions "@page"
    css = re.sub(r"@page\b[\w\s:-]*\{(?:[^{}]|\{[^{}]*\})*\}", "", css)

    def conv(m: re.Match) -> str:
        value = float(m.group(1))
        px = value * (96 / 72 if m.group(2) == "pt" else 96 / 25.4) * k
        if 0 < px < 1:
            px = 1.0  # hairlines must still show on ordinary screens
        return f"{px:.2f}px"

    return re.sub(r"(?<![\w.#])(-?\d*\.?\d+)(pt|mm)\b", conv, css)


def _display_font_css(fonts: dict) -> str:
    """Thmanyah faces for headings, embedded in the stylesheet (see the module note)."""
    rules = []
    for m in re.finditer(r'@font-face \{ font-family: "(Cover (?:sans|text|display))"; font-weight: (\d+);[^}]*?url\("(file://[^"]+)"\) format\("([^"]+)"\)', fonts["css"]):
        family, weight, uri, fmt = m.groups()
        if f'"{family}"' != fonts["head"] or int(weight) not in (500, 700, 900):
            continue
        data = Path(_unquote(uri)).read_bytes()
        mime = {"opentype": "font/otf", "truetype": "font/ttf", "woff2": "font/woff2", "woff": "font/woff"}[fmt]
        rules.append(
            f'@font-face{{font-family:"{family}";font-weight:{weight};font-style:normal;font-display:swap;'
            f'src:url(data:{mime};base64,{base64.b64encode(data).decode("ascii")}) format("{fmt}");}}'
        )
    return "\n".join(rules)


def _unquote(uri: str) -> str:
    from urllib.parse import unquote, urlparse
    return unquote(urlparse(uri).path)


def _page(title: str, body: str, bp, description: str, pager: str = "") -> str:
    issues = bp.REPO_URL + "/issues/new"
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:image" content="cover-front.jpg">
<meta property="og:type" content="book">
<link rel="icon" href="assets/mark.svg">
<link rel="stylesheet" href="assets/display.css">
<link rel="stylesheet" href="assets/book.css">
</head>
<body class="web">
<header class="topbar">
  <a class="brand" href="index.html">{bp.BOOK_TITLE_PLAIN}</a>
  <nav>
    <a href="index.html#toc">الفهرس</a>
    <a class="opt" href="{PDF_NAME}">نسخة PDF</a>
    <a href="{issues}">اقترحْ تصويباً</a>
  </nav>
</header>
<main class="sheet">
{body}
</main>
{pager}
<footer class="site-foot">
  {bp.BOOK_TITLE_PLAIN} — {bp.BOOK_AUTHOR_AR}. كتابٌ حيٌّ قيدَ التحرير: إنْ وجدتَ خطأً أو غابتْ عنّا معلومة،
  <a href="{issues}">فافتحْ بلاغاً</a> أو قدِّمْ طلبَ دمجٍ في <a href="{bp.REPO_URL}">مستودعِ الكتاب</a> لنُصلحَه معاً.
</footer>
</body>
</html>
"""


def build_site(bp, fonts: dict, cover_font_note: str, front_pdf: Path, back_pdf: Path, out: Path) -> int:
    """bp is the build_pdf module. Returns the number of pages written."""
    if out.exists():
        shutil.rmtree(out)
    for d in ("assets", "fonts", "plates"):
        (out / d).mkdir(parents=True)

    # ----- images: archival plates as files, the cover boards as pictures
    plate_files = {}
    for i, plate in enumerate(bp.ARCHIVAL_PLATES, 1):
        name = f"plates/{i:02d}.jpg"
        with Image.open(bp.ROOT / "evidence/media" / plate["file"]) as im:
            im = im.convert("RGB")
            if im.width > 1400:
                im = im.resize((1400, round(im.height * 1400 / im.width)), Image.Resampling.LANCZOS)
            im.save(out / name, quality=84, optimize=True)
        plate_files[plate["file"]] = name
    for pdf, name in ((front_pdf, "cover-front.jpg"), (back_pdf, "cover-back.jpg")):
        pix = pymupdf.open(pdf)[0].get_pixmap(dpi=150)
        Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(out / name, quality=86, optimize=True)
    shutil.copy(bp.OUTPUT_PDF, out / PDF_NAME)
    (out / "assets/mark.svg").write_text(bp.STAR_MARK.format(s=8).replace('width="8mm" height="8mm"', 'width="64" height="64"'), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")

    # ----- the book itself, rendered once by the same code as the print edition
    sections, outline, chunks = bp.collect_book_parts(lambda plate: plate_files[plate["file"]])
    chunk_of = dict(chunks)
    item_of = {item["id"]: item for item in outline}
    pages = [s for s in sections if s["kind"] != "toc"]
    file_of = {s["id"]: FILE_FOR.get(s["key"], s["key"]) + ".html" for s in pages}
    id_file = {}
    for s in pages:
        for found in re.findall(r'\bid="([^"]+)"', chunk_of[s["id"]]):
            id_file[found] = file_of[s["id"]]

    def relink(fragment: str, current: str) -> str:
        def repl(m: re.Match) -> str:
            target = m.group(1)
            if target == "sec_toc":
                return 'href="index.html#toc"'
            dest = id_file.get(target)
            if dest is None:
                return m.group(0)
            if dest == current:
                return f'href="#{target}"'
            return f'href="{dest}"' if target in file_of else f'href="{dest}#{target}"'
        return re.sub(r'href="#([^"]+)"', repl, fragment)

    # ----- styles and fonts
    faces = []
    for weight, name in bp.PLEX_WEIGHTS.items():
        shutil.copy(bp.PLEX_DIR / f"IBMPlexSansArabic-{name}.ttf", out / "fonts")
        src = f'url("../fonts/IBMPlexSansArabic-{name}.ttf") format("truetype")'
        faces.append(f'@font-face {{ font-family: "IBM Plex Sans Arabic"; font-weight: {weight}; font-style: normal; font-display: swap; src: {src}; }}')
        faces.append(f'@font-face {{ font-family: "Plex Latin"; font-weight: {weight}; font-style: normal; font-display: swap; src: {src}; '
                     f'size-adjust: 91%; unicode-range: U+0030-0039, U+0040-005A, U+005F, U+0061-007A, U+00C0-024F; }}')
    shutil.copy(bp.PLEX_DIR / "OFL.txt", out / "fonts/OFL.txt")
    head_family = f'{fonts["head"]}, "Plex Latin", "IBM Plex Sans Arabic", sans-serif'
    css = (
        "\n".join(faces) + f"\n:root {{ --head: {head_family}; }}\n"
        + to_screen_css((bp.SCRIPTS / "book.css").read_text(encoding="utf-8"))
        + WEB_CSS
    )
    (out / "assets/book.css").write_text(css, encoding="utf-8")
    (out / "assets/display.css").write_text(_display_font_css(fonts), encoding="utf-8")

    description = "سيرةُ تعريبِ الألعابِ من وهجِ البداياتِ وشغفِ الروّادِ إلى شجونِ الخلافاتِ وعصرِ الذكاءِ الاصطناعي (١٩٩٣ – ٢٠٢٦)."

    # ----- one page per part, chapter and appendix
    for i, s in enumerate(pages):
        item = item_of[s["id"]]
        body = relink(chunk_of[s["id"]], file_of[s["id"]])
        body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
        body = body.replace("<img ", '<img loading="lazy" ')
        links = []
        if i > 0:
            prev = item_of[pages[i - 1]["id"]]
            links.append(f'<a class="prev" href="{file_of[pages[i - 1]["id"]]}"><span class="dir">→ السابق</span><span class="ttl">{html.escape(prev["title"])}</span></a>')
        else:
            links.append('<a class="prev" href="index.html"><span class="dir">→ البداية</span><span class="ttl">الغلاف والفهرس</span></a>')
        if i + 1 < len(pages):
            nxt = item_of[pages[i + 1]["id"]]
            links.append(f'<a class="next" href="{file_of[pages[i + 1]["id"]]}"><span class="dir">التالي ←</span><span class="ttl">{html.escape(nxt["title"])}</span></a>')
        title = f'{item["title"]} — {bp.BOOK_TITLE_PLAIN}'
        (out / file_of[s["id"]]).write_text(
            _page(title, body, bp, description, f'<nav class="pager">{"".join(links)}</nav>'), encoding="utf-8"
        )

    # ----- home page: cover, invitation, contents, book card
    rows = []
    for item in outline:
        cls = {"part": "toc-part", "appendix": "toc-appendix"}.get(item["kind"], "toc-chapter")
        rows.append(
            f'<div class="toc-entry {cls}"><a href="{file_of[item["id"]]}" class="toc-link">'
            f'<span class="toc-badge">{item["badge"]}</span><span class="toc-title">{html.escape(item["title"])}</span></a></div>'
        )
        for sub_id, sub_title in item["children"]:
            rows.append(
                f'<div class="toc-entry toc-sub"><a href="{file_of[item["id"]]}#{sub_id}" class="toc-link">'
                f'<span class="toc-title">{html.escape(sub_title)}</span></a></div>'
            )
    first = file_of[pages[0]["id"]]
    t1, t2 = bp.BOOK_TITLE_AR.split(" فِي ")
    home = f"""
<section class="hero">
  <a href="{first}"><img src="cover-front.jpg" alt="غلاف كتاب {bp.BOOK_TITLE_PLAIN}"></a>
  <div>
    <div class="kicker">سِفْرٌ تاريخيٌّ وتوثيقيٌّ محقَّق</div>
    <h1><span>{t1}</span><span class="l2">فِي {t2}</span></h1>
    <p class="sub">{bp.BOOK_SUBTITLE_AR}</p>
    <div class="by">{bp.BOOK_AUTHOR_AR}</div>
    <div class="when">١٩٩٣ م — ١٢ نوفمبر ٢٠٢٦ م · الطبعة التوثيقية الموسَّعة</div>
    <div class="actions">
      <a class="btn primary" href="{first}">ابدأِ القراءة</a>
      <a class="btn" href="#toc">فهرس المحتويات</a>
      <a class="btn" href="{PDF_NAME}">تحميل PDF</a>
    </div>
  </div>
</section>
{bp.living_note_html()}
<section id="toc">
  {bp.opener_html("دليلُ القراءة", "فهرس المحتويات", "")}
  <div class="toc-list">{"".join(rows)}</div>
</section>
<section class="colophon-page">
  {bp.colophon_card_html(cover_font_note)}
</section>
"""
    (out / "index.html").write_text(_page(f"{bp.BOOK_TITLE_PLAIN} — {bp.BOOK_AUTHOR_AR}", home, bp, description), encoding="utf-8")
    return len(pages) + 1


def deploy(out: Path, remote: str, name: str, email: str) -> None:
    """Publishes the built site as the only commit on the gh-pages branch."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "site"
        shutil.copytree(out, work)
        run = lambda *a: subprocess.run(["git", *a], cwd=work, check=True, capture_output=True, text=True)
        run("init", "-q", "-b", "gh-pages")
        run("add", "-A")
        run("-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "-q", "-m", "Publish the web edition")
        run("push", "-q", "-f", remote, "gh-pages")
