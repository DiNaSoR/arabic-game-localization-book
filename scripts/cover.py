"""
Cover for «بيان الضاد في ممالك الخيال»: an antique brown leather binding.

The leather, its wear and its worn gold tooling (ruled frame with a band of pixel-like squares,
stepped pixel corner pieces, an eight-pointed star medallion with pendants, raised spine bands) are
AI-generated artwork kept in scripts/cover-art/ and made by scripts/generate_cover_art.py. The art
contains no writing: image models cannot be trusted with vocalised Arabic, so every letter on the
cover is live type set here, in the Thmanyah typeface when it is installed.

The three pieces (front board, spine, back board) are assembled into one sheet and printed three
ways: the full wrap for the printer (the front is on the LEFT because the book opens right-to-left),
and the front and back boards alone for the reading edition.
"""

from __future__ import annotations

import base64
import html
import io
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageStat

SCRIPTS = Path(__file__).resolve().parent
PRIVATE_FONTS = SCRIPTS / "fonts" / "private"
COVER_FONT_DIR = PRIVATE_FONTS / "cover"   # a font dropped here is used for the cover lettering only
COVER_FONT_SCALE = 1.27                    # tuned for Milan Display Black, which draws small on its em
ART_DIR = SCRIPTS / "cover-art"

PANEL_W, PANEL_H = 170.0, 240.0
BLEED_MM = 3.0
PRINT_DPI = 300
SCREEN_DPI = 170

GOLD = "#dfbb72"
CREAM = "#ecdcb6"

TITLE_1 = "بَيَانُ الضَّادِ"
TITLE_2 = "فِي مَمَالِكِ الخَيَال"
SUBTITLE = ("سيرةُ تعريبِ الألعابِ من وهجِ البداياتِ وشغفِ الروّادِ", "إلى شجونِ الخلافاتِ وعصرِ الذكاءِ الاصطناعي")
AUTHOR = "ص - شبكة ترس"
SPINE_TITLE = "بيان الضاد في ممالك الخيال"
YEAR_FROM, YEAR_TO = "١٩٩٣", "٢٠٢٦"

# Both passages are taken verbatim from the book's own preface (book/00-preface-and-gratitude.md).
BLURB = [
    "هنالك، في العتمةِ الصامتةِ خلفَ الشاشات، وُلدتْ حكايةٌ من أنبلِ حكاياتِ الشغفِ في فضائنا الرقميِّ العربي؛ "
    "حكايةُ رجالٍ وشبابٍ نفروا فُرادى وجماعاتٍ، لا يبتغونَ جاهاً ولا ينتظرونَ جزاءً، فطوّعوا أعسرَ الشيفراتِ المغلقة، "
    "ورسموا حروفَ الضادِ نقطةً نقطةً في جداولَ ضيّقةٍ لم تُصنعْ لها، وقلبوا سريانَ الواجهاتِ من اليسارِ إلى اليمينِ "
    "ليأنسَ الحرفُ العربيُّ في غربتِه.",
    "ليسَ هذا الكتابُ قاضياً يحكمُ لطرفٍ على طرف، ولا خصماً ينتصرُ لمدرسةٍ دونَ أختِها، وإنّما وُضعَ غايةً واحدةً "
    "خالصة: أنْ ينقلَ القصةَ الكاملةَ لتعريبِ الألعابِ من فجرِ بداياتِها الأولى في مطلعِ التسعينياتِ حتى نوفمبر ٢٠٢٦ "
    "بحيادٍ تامٍّ، وأمانةٍ تاريخيةٍ صارمة، وميزانٍ واحدٍ لا يميلُ مع هوىً ولا يجورُ على ذي حقّ.",
]
BLURB_SOURCE = "من فاتحةِ الكتاب"

# Where things sit in the artwork, as fractions of each image (measured on scripts/cover-art/*.jpg).
# Re-measure these if the artwork is regenerated.
FRONT_ART = {
    "medallion": (0.499, 0.556),      # centre of the star medallion
    "medallion_r": 0.238,             # outer ring radius, as a fraction of the image width
    "title_zone": (0.085, 0.315),     # plain leather above the upper pendant (top, bottom)
    "foot_zone": (0.805, 0.945),      # plain leather below the lower pendant
    "frame_inner": 0.105,             # inner edge of the gilt frame from the left/right edge
}
SPINE_ART = {
    "title_zone": (0.29, 0.70),       # long plain panel between the second and third raised band
    "imprint_zone": (0.765, 0.835),   # short panel between the third and fourth band
}


# --------------------------------------------------------------------------- fonts


def find_cover_fonts() -> dict:
    """Finds the privately licensed typefaces (never committed):
    Thmanyah, used for the titles and headings inside the book, and, when a font file is present in
    scripts/fonts/private/cover/, a separate display face used only on the front cover, back cover
    and spine. Without that file the cover is lettered in Thmanyah as well."""
    dirs = [PRIVATE_FONTS]
    if os.environ.get("THMANYAH_FONT_DIR"):
        dirs.append(Path(os.environ["THMANYAH_FONT_DIR"]))
    home = Path.home()
    dirs += [home / "Library/Fonts", Path("/Library/Fonts"), home / ".fonts", home / ".local/share/fonts"]

    fmt_rank = {".otf": 0, ".ttf": 1, ".woff2": 2, ".woff": 3}
    fmt_name = {".otf": "opentype", ".ttf": "truetype", ".woff2": "woff2", ".woff": "woff"}
    weights = [("extralight", 200), ("light", 300), ("regular", 400), ("medium", 500),
               ("semibold", 600), ("extrabold", 800), ("bold", 700), ("black", 900), ("heavy", 900)]
    found: dict[tuple[str, int], Path] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for path in sorted(d.rglob("*")):
            low = path.name.lower()
            if "thmanyah" not in low or path.suffix.lower() not in fmt_rank:
                continue
            family = "display" if "display" in low else "sans" if "sans" in low else "text"
            weight = next((w for key, w in weights if key in low), 400)
            cur = found.get((family, weight))
            if cur is None or fmt_rank[path.suffix.lower()] < fmt_rank[cur.suffix.lower()]:
                found[(family, weight)] = path

    families = {fam for fam, _ in found}
    cover_file = None
    if COVER_FONT_DIR.is_dir():
        cover_file = next((p for p in sorted(COVER_FONT_DIR.iterdir()) if p.suffix.lower() in fmt_rank), None)
    cover_css = cover_name = ""
    if cover_file:
        import pymupdf
        cover_name = pymupdf.Font(fontfile=str(cover_file)).name
        # One file serves every weight the cover asks for, so the browser never fakes a bold.
        cover_css = (
            f'@font-face {{ font-family: "Cover custom"; font-weight: 100 900; font-style: normal; '
            f'src: url("{cover_file.resolve().as_uri()}") format("{fmt_name[cover_file.suffix.lower()]}"); }}\n'
        )
    css = cover_css + "\n".join(
        f'@font-face {{ font-family: "Cover {fam}"; font-weight: {w}; font-style: normal; '
        f'src: url("{p.resolve().as_uri()}") format("{fmt_name[p.suffix.lower()]}"); }}'
        for (fam, w), p in sorted(found.items())
    )
    pick = lambda order: next((f'"Cover {fam}"' for fam in order if fam in families), '"IBM Plex Sans Arabic"')
    thmanyah_title = pick(["display", "text", "sans"])
    thmanyah_text = pick(["text", "sans", "display"])
    # The sans has no display cut, so its heaviest weight carries the title.
    thmanyah_weight = 900 if families == {"sans"} else 700
    return {
        "thmanyah": bool(found),
        "cover_font": cover_name,
        "css": css,
        # inside the book
        "head": thmanyah_title,
        # on the cover: headline lettering and the smaller lines
        "title": '"Cover custom"' if cover_file else thmanyah_title,
        "title_weight": 900 if cover_file else thmanyah_weight,
        "text": '"Cover custom"' if cover_file else thmanyah_text,
        # long reading text on the back board stays in a text face
        "reading": thmanyah_text,
        # Display faces differ in how large they draw at a given point size; this evens them out.
        "scale": COVER_FONT_SCALE if cover_file else 1.0,
        "files": sorted(str(p) for p in found.values()) + ([str(cover_file)] if cover_file else []),
    }


# --------------------------------------------------------------------------- geometry


class Layout:
    def __init__(self, spine_mm: float):
        self.spine = spine_mm
        self.W = 2 * PANEL_W + spine_mm + 2 * BLEED_MM
        self.H = PANEL_H + 2 * BLEED_MM
        self.front_x = BLEED_MM                      # trim edge of the front board (left panel)
        self.spine_x = BLEED_MM + PANEL_W
        self.back_x = BLEED_MM + PANEL_W + spine_mm
        self.top = BLEED_MM
        self.has_spine_text = spine_mm >= 7.0
        # Each board's artwork also covers the bleed on its three outer sides.
        self.board_w = PANEL_W + BLEED_MM

    def front_xy(self, fx: float, fy: float) -> tuple[float, float]:
        """Artwork fraction -> millimetres on the wrap, for the front board."""
        return fx * self.board_w, fy * self.H


def f(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- leather sheet


def _cover_fit(im: Image.Image, w: int, h: int) -> Image.Image:
    """Scales and centre-crops the artwork to exactly w x h pixels."""
    scale = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * scale)), max(h, round(im.height * scale))), Image.Resampling.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _match_tone(im: Image.Image, sample: tuple[float, float, float, float], target_mean, target_std) -> Image.Image:
    """Brings a separately generated piece of leather to the front board's colour and contrast."""
    box = (round(sample[0] * im.width), round(sample[1] * im.height), round(sample[2] * im.width), round(sample[3] * im.height))
    stat = ImageStat.Stat(im.crop(box))
    bands = []
    for band, m, s, tm, ts in zip(im.split(), stat.mean, stat.stddev, target_mean, target_std):
        gain = min(1.25, max(0.8, ts / s if s else 1.0))
        bands.append(band.point(lambda v, m=m, gain=gain, tm=tm: max(0, min(255, round((v - m) * gain + tm)))))
    return Image.merge("RGB", bands)


def compose_leather(L: Layout) -> Image.Image:
    k = PRINT_DPI / 25.4
    W, H = round(L.W * k), round(L.H * k)
    board_w = round(L.board_w * k)
    spine_w = W - 2 * board_w

    front = _cover_fit(Image.open(ART_DIR / "front.jpg").convert("RGB"), board_w, H)
    back = _cover_fit(Image.open(ART_DIR / "back.jpg").convert("RGB"), board_w, H)
    spine_art = Image.open(ART_DIR / "spine.jpg").convert("RGB")

    # The front board's plain upper field sets the colour for the other two pieces.
    ref = ImageStat.Stat(front.crop((round(0.2 * board_w), round(0.1 * H), round(0.8 * board_w), round(0.3 * H))))
    back = _match_tone(back, (0.2, 0.2, 0.8, 0.8), ref.mean, ref.stddev)
    spine_art = _match_tone(spine_art, (0.3, 0.35, 0.7, 0.65), ref.mean, ref.stddev)

    # Only the evenly lit middle of the generated spine is used, at its native scale, so the raised
    # bands cross the real spine width without the leather grain being squeezed.
    spine_art = spine_art.resize((round(spine_art.width * H / spine_art.height), H), Image.Resampling.LANCZOS)
    x0 = (spine_art.width - spine_w) // 2
    spine = spine_art.crop((x0, 0, x0 + spine_w, H))

    sheet = Image.new("RGB", (W, H))
    sheet.paste(front, (0, 0))
    sheet.paste(spine, (board_w, 0))
    sheet.paste(back, (board_w + spine_w, 0))

    # Joints: a soft dark groove where each board meets the spine, which also hides the seams.
    shade = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(shade)
    for jx in (board_w, board_w + spine_w):
        draw.rectangle((jx - round(0.5 * k), 0, jx + round(0.5 * k), H), fill=215)
    shade = shade.filter(ImageFilter.GaussianBlur(1.0 * k))
    dark = Image.new("RGB", (W, H), (24, 11, 4))
    return Image.composite(dark, sheet, shade)


# --------------------------------------------------------------------------- lettering


def cover_html(L: Layout, fonts: dict, plex_css: str, texture_uri: str, view: str) -> str:
    """view: 'wrap' (whole sheet with bleed), 'front' or 'back' (one trimmed board)."""
    if view == "wrap":
        vw, vh, ox, oy = L.W, L.H, 0.0, 0.0
        tex = f'<img class="leather" style="left:0;top:0;width:{f(L.W)}mm;height:{f(L.H)}mm" src="{texture_uri}">'
    else:
        vw, vh = PANEL_W, PANEL_H
        ox, oy = (L.front_x if view == "front" else L.back_x), L.top
        tex = f'<img class="leather" style="left:{f(ox)}mm;top:{f(oy)}mm;width:{f(PANEL_W)}mm;height:{f(PANEL_H)}mm" src="{texture_uri}">'

    # ----- front board: everything is positioned from the artwork's own geometry
    mx, my = L.front_xy(*FRONT_ART["medallion"])
    ring = FRONT_ART["medallion_r"] * L.board_w
    _, t0 = L.front_xy(0, FRONT_ART["title_zone"][0])
    _, t1 = L.front_xy(0, FRONT_ART["title_zone"][1])
    _, b0 = L.front_xy(0, FRONT_ART["foot_zone"][0])
    _, b1 = L.front_xy(0, FRONT_ART["foot_zone"][1])
    frame_l = FRONT_ART["frame_inner"] * L.board_w
    frame_r = L.board_w * (1 - FRONT_ART["frame_inner"])
    text_l, text_w = mx - 62, 124.0
    glyph_box = ring * 0.98
    k = fonts.get("scale", 1.0)
    pt = lambda size: f(size * k)
    tight = k > 1.0   # the scaled display face needs less leading to stay inside the artwork's fields

    # ----- back board: centred on its artwork
    bcx = L.back_x + L.board_w / 2
    blurb = "".join(f"<p>{html.escape(p)}</p>" for p in BLURB)

    spine_html = ""
    if L.has_spine_text:
        size = min(13.0, L.spine * 1.25) * fonts.get("scale", 1.0)  # pt
        sxm = L.spine_x + L.spine / 2
        z0, z1 = SPINE_ART["title_zone"]
        i0, i1 = SPINE_ART["imprint_zone"]
        # Arabic spine lettering reads from the head of the book to its foot, tops towards the front board.
        spine_html = f"""
  <div class="spine-text" style="left:{f(sxm - (z1 - z0) * L.H / 2)}mm; top:{f((z0 + z1) / 2 * L.H - L.spine / 2)}mm; width:{f((z1 - z0) * L.H)}mm; height:{f(L.spine)}mm; font-size:{f(size)}pt">
    <span class="gilt">{SPINE_TITLE}</span></div>
  <div class="spine-text small" style="left:{f(sxm - (i1 - i0) * L.H / 2)}mm; top:{f((i0 + i1) / 2 * L.H - L.spine / 2)}mm; width:{f((i1 - i0) * L.H)}mm; height:{f(L.spine)}mm; font-size:{f(size * 0.6)}pt">
    <span class="gilt">شبكة ترس</span></div>"""

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>{SPINE_TITLE} — الغلاف</title>
<style>
{plex_css}
{fonts["css"]}
@page {{ size: {f(vw)}mm {f(vh)}mm; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #2a1608; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
.view {{ position: relative; width: {f(vw)}mm; height: {f(vh - 0.15)}mm; overflow: hidden; }}
.canvas {{ position: absolute; left: {f(-ox)}mm; top: {f(-oy)}mm; width: {f(L.W)}mm; height: {f(L.H)}mm; }}
.leather {{ position: absolute; display: block; }}

.box {{ position: absolute; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; }}
/* Gold leaf pressed into leather: a dark edge below-right where the tool bit in, a faint light edge above-left. */
.gilt {{
  color: {GOLD};
  text-shadow: 0.17mm 0.21mm 0 rgba(14, 6, 2, 0.82), -0.07mm -0.08mm 0 rgba(255, 236, 190, 0.20);
}}
.t-title {{ font-family: {fonts["title"]}, "IBM Plex Sans Arabic"; font-weight: {fonts["title_weight"]}; white-space: nowrap; }}
.t-text {{ font-family: {fonts["text"]}, "IBM Plex Sans Arabic"; font-weight: 500; }}

.kicker {{ font-size: {pt(10)}pt; line-height: 1.5; margin-bottom: 1.5mm; }}
.title-1 {{ font-size: {pt(46)}pt; line-height: {1.26 if tight else 1.42}; }}
.title-2 {{ font-size: {pt(32)}pt; line-height: {1.3 if tight else 1.42}; }}
.glyph {{ font-size: {f(glyph_box * 1.86 * (k * 1.1 if tight else 1))}pt; line-height: 1; padding-bottom: {f(glyph_box * 0.07)}mm; }}
.year {{ font-size: {pt(11)}pt; line-height: 1; font-feature-settings: "tnum"; }}
.subtitle {{ font-size: {pt(10.4)}pt; line-height: {1.6 if tight else 1.8}; color: {CREAM}; }}
.author-label {{ font-size: {pt(7.6)}pt; line-height: 1.4; margin-top: {1.2 if tight else 2.2}mm; }}
.author {{ font-size: {pt(15.5)}pt; line-height: {1.3 if tight else 1.45}; }}

.blurb p {{
  margin: 0 0 6mm; font-size: {pt(12)}pt; line-height: {1.95 if tight else 2.1}; text-align: justify; text-align-last: center;
  color: {CREAM}; text-shadow: 0.13mm 0.17mm 0 rgba(14, 6, 2, 0.8);
}}
.blurb .source {{ font-size: {pt(9.4)}pt; margin-top: 1mm; }}
.back-foot {{ font-size: {pt(10.5)}pt; line-height: 1.6; }}

.spine-text {{
  position: absolute; display: flex; align-items: center; justify-content: center;
  transform: rotate(-90deg); white-space: nowrap; line-height: 1;
  font-family: {fonts["title"]}, "IBM Plex Sans Arabic"; font-weight: {fonts["title_weight"]};
}}
.spine-text.small {{ font-family: {fonts["text"]}, "IBM Plex Sans Arabic"; font-weight: 500; }}
</style></head>
<body>
<div class="view"><div class="canvas">
  {tex}

  <!-- front board -->
  <div class="box" style="left:{f(text_l)}mm; top:{f(t0)}mm; width:{f(text_w)}mm; height:{f(t1 - t0)}mm">
    <div class="kicker t-text gilt">سِفْرٌ تاريخيٌّ وتوثيقيٌّ محقَّق</div>
    <div class="title-1 t-title gilt">{TITLE_1}</div>
    <div class="title-2 t-title gilt">{TITLE_2}</div></div>
  <div class="box" style="left:{f(mx - glyph_box / 2)}mm; top:{f(my - glyph_box / 2)}mm; width:{f(glyph_box)}mm; height:{f(glyph_box)}mm">
    <div class="glyph t-title gilt">ض</div></div>
  <div class="box" style="left:{f(mx + ring)}mm; top:{f(my - 5)}mm; width:{f(frame_r - mx - ring)}mm; height:10mm">
    <div class="year t-text gilt">{YEAR_FROM}</div></div>
  <div class="box" style="left:{f(frame_l)}mm; top:{f(my - 5)}mm; width:{f(mx - ring - frame_l)}mm; height:10mm">
    <div class="year t-text gilt">{YEAR_TO}</div></div>
  <div class="box" style="left:{f(text_l)}mm; top:{f(b0)}mm; width:{f(text_w)}mm; height:{f(b1 - b0)}mm">
    <div class="subtitle t-text gilt">{SUBTITLE[0]}<br>{SUBTITLE[1]}</div>
    <div class="author-label t-text gilt">تأليف وتوثيق</div>
    <div class="author t-title gilt">{AUTHOR}</div></div>

  <!-- back board -->
  <div class="box blurb t-text" style="left:{f(bcx - 59)}mm; top:{f(L.top + 30)}mm; width:118mm; height:166mm">
    {blurb}
    <div class="source gilt">— {BLURB_SOURCE} —</div></div>
  <div class="box" style="left:{f(bcx - 45)}mm; top:{f(L.top + PANEL_H - 40)}mm; width:90mm; height:9mm">
    <div class="back-foot t-text gilt">{AUTHOR}</div></div>
  {spine_html}
</div></div>
</body></html>"""


# --------------------------------------------------------------------------- build


def _jpeg_uri(im: Image.Image, quality: int) -> str:
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def build_cover(chrome, tmp: Path, spine_mm: float, fonts: dict, plex_css: str) -> tuple[Path, Path, Path]:
    missing = [n for n in ("front.jpg", "back.jpg", "spine.jpg") if not (ART_DIR / n).exists()]
    if missing:
        raise SystemExit(f"Cover artwork missing in {ART_DIR}: {missing}. Run scripts/generate_cover_art.py.")
    L = Layout(spine_mm)
    leather = compose_leather(L)
    leather.save(tmp / "cover_leather.jpg", quality=90)
    kx, ky = leather.width / L.W, leather.height / L.H

    def board(x_mm: float) -> str:
        crop = leather.crop((round(x_mm * kx), round(L.top * ky), round((x_mm + PANEL_W) * kx), round((L.top + PANEL_H) * ky)))
        scale = SCREEN_DPI / PRINT_DPI
        crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
        return _jpeg_uri(crop, 86)

    out = {}
    for view, uri in (("wrap", _jpeg_uri(leather, 91)), ("front", board(L.front_x)), ("back", board(L.back_x))):
        html_path = tmp / f"cover_{view}.html"
        pdf_path = tmp / f"cover_{view}.pdf"
        html_path.write_text(cover_html(L, fonts, plex_css, uri, view), encoding="utf-8")
        chrome.pdf(html_path, pdf_path)
        out[view] = pdf_path
    return out["wrap"], out["front"], out["back"]
