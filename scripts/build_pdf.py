#!/usr/bin/env python3
"""
Builds «بيان الضاد في ممالك الخيال» as a print-ready book.

Outputs
  arabic-game-localization-book.pdf      reading edition: front cover + interior + back cover
  print/interior-170x240mm.pdf               interior only, trim size, mirrored margins, page count padded to x4
  print/cover-wrap.pdf                       back + spine + front in one sheet, 3 mm bleed, TrimBox/BleedBox set
  site/                                      web edition for GitHub Pages (same chapters, same stylesheet)

Design
  - Trim 170 x 240 mm (القطع الوزيري). Every part, chapter and appendix opens on a recto page.
  - Interior text in IBM Plex Sans Arabic (scripts/fonts/ibm-plex, OFL); titles, headings and running
    heads in the Thmanyah typeface when it is installed (otherwise Plex as well).
  - Cover: AI-generated antique leather artwork (scripts/cover-art/, made by
    scripts/generate_cover_art.py) with all lettering typeset on top by scripts/cover.py.
  - Cover lettering (front, back, spine) uses the font in scripts/fonts/private/cover/ when there is one;
    otherwise the Thmanyah typeface when its files are present in scripts/fonts/private/
    (or $THMANYAH_FONT_DIR). The Thmanyah licence forbids redistribution, so those files are
    never committed; download them from https://font.thmanyah.com/ . Without them the cover
    falls back to IBM Plex Sans Arabic and the build says so.

Usage
  python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt
  .venv/bin/python scripts/build_pdf.py [--spine-mm 11] [--paper-mm-per-page 0.06]
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

import markdown
import pymupdf
import websocket
from PIL import Image

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
FONTS_DIR = SCRIPTS / "fonts"
PLEX_DIR = FONTS_DIR / "ibm-plex"
OUTPUT_PDF = ROOT / "arabic-game-localization-book.pdf"
PRINT_DIR = ROOT / "print"
PRINT_INTERIOR = PRINT_DIR / "interior-170x240mm.pdf"
PRINT_COVER = PRINT_DIR / "cover-wrap.pdf"
SITE_DIR = ROOT / "site"   # web edition; git-ignored, published with --deploy
# Identity on the published site's commits: the GitHub account, not a personal name or address.
DEPLOY_NAME, DEPLOY_EMAIL = "DiNaSoR", "8531014+DiNaSoR@users.noreply.github.com"

TRIM_W_MM, TRIM_H_MM = 170.0, 240.0
TOP_MARGIN_MM = 22.0
INNER_MARGIN_MM, OUTER_MARGIN_MM = 24.0, 18.0
MM = 72 / 25.4  # PDF points per millimetre

BOOK_TITLE_AR = "بَيَانُ الضَّادِ فِي مَمَالِكِ الخَيَال"
BOOK_TITLE_PLAIN = "بيان الضاد في ممالك الخيال"
BOOK_SUBTITLE_AR = "سيرةُ تعريبِ الألعابِ من وهجِ البداياتِ وشغفِ الروّادِ إلى شجونِ الخلافاتِ وعصرِ الذكاءِ الاصطناعي"
BOOK_AUTHOR_AR = "ص - شبكة ترس"
# Where readers report mistakes and propose fixes; printed on the colophon page.
REPO_URL = "https://github.com/DiNaSoR/arabic-game-localization-book"

PLEX_WEIGHTS = {300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold"}

CHAPTER_SPEC = [
    ("ch00", "مدخل الكتاب", "مدخل الكتاب: بوصلة القارئ والأركان الهندسية", ROOT / "book/00-introduction.md"),
    ("ch01", "الفصل الأول", "الباب الأول · الفصل الأول: فجر الدهشة الأولى", ROOT / "book/01-origins-and-rom-hacking-era.md"),
    ("ch02", "الفصل الثاني", "الباب الأول · الفصل الثاني: نهضة الومض وأوكارينا الزمن", ROOT / "book/02-zelda-n64-and-early-2010s-pioneers.md"),
    ("ch03", "الفصل الثالث", "الباب الأول · الفصل الثالث: العصر الذهبي للصنعة البشرية", ROOT / "book/03-golden-age-teams-and-open-tools.md"),
    ("ch04", "الفصل الرابع", "الباب الأول · الفصل الرابع: فجر الآلة الناطقة", ROOT / "book/04-ai-revolution-and-dubbing-era.md"),
    ("ch05", "الفصل الخامس", "الباب الثاني · الفصل الخامس: الجذور الأولى للخصام", ROOT / "book/05-roots-of-disagreement-credit-and-style.md"),
    ("ch06", "الفصل السادس", "الباب الثاني · الفصل السادس: معضلة المال والاحتكار", ROOT / "book/06-monetization-vip-and-silent-hill-f.md"),
    ("ch07", "الفصل السابع", "الباب الثاني · الفصل السابع: عودة أوكارينا الزمن للعاصفة", ROOT / "book/07-ocarina-of-time-2026-crisis.md"),
    ("ch08", "الفصل الثامن", "الباب الثاني · الفصل الثامن: الساعات الـ ٧٢ الفاصلة", ROOT / "book/08-november-2026-confrontation.md"),
    ("ch09", "الفصل التاسع", "الباب الثاني · الفصل التاسع: خاتمة المطاف وميثاق المستقبل", ROOT / "book/09-ethics-credit-and-future-charter.md"),
]

PART_DIVIDERS = {
    "ch01": {
        "id": "sec_part1",
        "badge": "البابُ الأوّل",
        "title": "سِيرَةُ البِنَاءِ وَالشَّغَف",
        "subtitle": "قصّةُ تعريبِ الألعابِ كاملةً من البذرةِ الأولى مطلعَ التسعينياتِ (١٩٩٣–١٩٩٥) إلى فجرِ الذكاءِ الاصطناعيِّ والدبلجةِ الآليةِ عامَ ٢٠٢٦",
        "desc": "في هذا البابِ الأوّلِ نصحبُ القارئَ في رحلةٍ زمنيةٍ صافيةٍ عبرَ الفصولِ الأربعةِ الأولى، ليعرفَ كيفَ بُنيتْ ساحةُ التعريبِ العربيِّ جِيلاً بعدَ جيل، ومَن هم روّادُها وفرقُها ومطوّرو أدواتِها، دونَ أنْ تقطعَ حبلَ الحكايةِ خصوماتٌ متأخّرة.",
        "toc_title": "البابُ الأوّل: سيرةُ البناءِ والشغف — قصّةُ التعريباتِ من البداية (١٩٩٣–٢٠٢٦)",
        "bookmark": "الباب الأول: سيرة البناء والشغف (قصة التعريبات 1993–2026)",
    },
    "ch05": {
        "id": "sec_part2",
        "badge": "البابُ الثاني",
        "title": "شُجُونُ المَسِيرَةِ وَمِيزَانُ الخِلَافَات",
        "subtitle": "توثيقٌ محايدٌ لمنازعاتِ النسبةِ والأسلوبِ والتربّحِ ومواجهةِ نوفمبر ٢٠٢٦ الكبرى في ضوءِ الوثائقِ والأرقام",
        "desc": "بعدَ أنِ اكتملتْ في البابِ الأوّلِ معرفةُ القارئِ بجميعِ الأجيالِ والمدارسِ والأعلام، يفتحُ هذا البابُ الثاني عبرَ الفصولِ الخامسِ حتى التاسعِ ملفَّ الخلافاتِ مرتَّباً من جذورِه الأولى إلى الساعاتِ الاثنتينِ والسبعينَ الفاصلةِ بميزانِ العدلِ والفصلِ الصارمِ بينَ الوقائعِ والادّعاءات.",
        "toc_title": "البابُ الثاني: شجونُ المسيرةِ وميزانُ الخلافات (١٩٩٥ – ١٢ نوفمبر ٢٠٢٦)",
        "bookmark": "الباب الثاني: شجون المسيرة وميزان الخلافات",
    },
}

INTERNAL_LINK_MAP = {
    "00-preface-and-gratitude.md": "#sec_preface",
    "00-introduction.md": "#sec_ch00",
    "01-origins-and-rom-hacking-era.md": "#sec_ch01",
    "02-zelda-n64-and-early-2010s-pioneers.md": "#sec_ch02",
    "03-golden-age-teams-and-open-tools.md": "#sec_ch03",
    "04-ai-revolution-and-dubbing-era.md": "#sec_ch04",
    "05-roots-of-disagreement-credit-and-style.md": "#sec_ch05",
    "06-monetization-vip-and-silent-hill-f.md": "#sec_ch06",
    "07-ocarina-of-time-2026-crisis.md": "#sec_ch07",
    "08-november-2026-confrontation.md": "#sec_ch08",
    "09-ethics-credit-and-future-charter.md": "#sec_ch09",
    "timeline.md": "#sec_timeline",
    "people-and-teams.md": "#sec_people",
    "references.md": "#sec_references",
    "evidence/INDEX.md": "#sec_plates",
}

ARCHIVAL_PLATES = [
    {
        "num": "لوحة ١",
        "file": "mansour-part1-photo1-oot3ds-reddit.jpg",
        "title": "مقارنة مجتمع r/Arabic_Games بين تعريبَي Ocarina of Time 3DS (28 مارس 2026)",
        "caption": "لقطة أرشيفية أرفقها منصور بالجزء الأول من مقاله (12 نوفمبر 2026)، توثق منشور ريديت الذي فضّل فيه كاتبه بساطة لغة نسخة إبراهيم أموجوغا مقارنةً بنسخة فريق «الحلم المتجدد» [48][68].",
    },
    {
        "num": "لوحة ٢",
        "file": "mansour-part1-photo2-oot-ingo-line.jpg",
        "title": "عبارة «فاحمد حظك» في حوار شخصية «إنغو» — ريميك Ocarina of Time (نوفمبر 2026)",
        "caption": "اللقطة التي بنى عليها منصور فرضيته حول تأثر صياغات التعريب الآلي بنصوص سابقة مع استبدال حرفي لكلمة Luck، في حين تبرز القراءة المقابلة شيوع هذا التركيب في مخرجات النماذج اللغوية المباشرة [53][68].",
    },
    {
        "num": "لوحة ٣",
        "file": "mansour-part2-photo1-tp-overflow.jpg",
        "title": "عيوب تدفق النص الأولية في النسخة الآلية الأولى لـ Twilight Princess (1 سبتمبر 2026)",
        "caption": "لقطة من محادثات فريق الحلم المتجدد تقارن ضبط صندوق الحوار بفيضان النصوص خارج الإطار في الإصدار الآلي الأولي قبل تحديثات أكتوبر اللاحقة [50][69].",
    },
    {
        "num": "لوحة ٤",
        "file": "mansour-part2-photo4-hesham-oct2-update.png",
        "title": "إعلان هشام (@Arabic_Hesham) عن تحديث المحاذاة والكيبورد العربي (2 أكتوبر 2026)",
        "caption": "تغريدة تحديث تعريبَي دموع المملكة وأميرة الشفق المجانيين على موقع هشام؛ وهي الترقية التقنية التي تنازع الطرفان حول ما إذا كانت هندسةً عكسية مستقلة أم مقتبسةً من إصدار الحلم المتجدد [50][69].",
    },
    {
        "num": "لوحة ٥",
        "file": "eternaldream-nov11-photo1-asmar-wuwa.jpg",
        "title": "إعلان «مكتبة أسمر» (@AsmarGamesAR) عن تعريب Wuthering Waves (10 نوفمبر 2026)",
        "caption": "الملصق الإعلاني الذي فجّر احتجاج المشرفين على المشروع البشري التعاوني المشترك بين أربع فرق بعد رصدهم استخدام ملفاتهم وخط آدم سعيد دون استئذان [56][57].",
    },
    {
        "num": "لوحة ٦",
        "file": "allenwouka-nov11-asmar-block.jpg",
        "title": "توثيق حظر حساب @AllenWouka قبل صدور الاعتذار العلني من @AsmarGamesAR (11 نوفمبر 2026)",
        "caption": "لقطة شاشة نشرها علان ووكا ظهر 11 نوفمبر عقب اعتراضه؛ وقد تلاها بساعات تراجع حساب «أسمر» ونشره اعتذاراً رسمياً يقرّ بأخذ أحد أعضائه للملفات دون علم الإدارة ويتعهد بإزالتها [57][58].",
    },
    {
        "num": "لوحة ٧",
        "file": "eternaldream-nov11-photo2-elassl-balatro.jpg",
        "title": "صفحة تعريب Balatro في موقع «فريق الأصل» (@ELASSLTEAM) المرفقة ببيان 11 نوفمبر",
        "caption": "تظهر فيها الإشارات الحمراء التي وضعها فريق الحلم المتجدد تحت تبويب «القرآن الكريم» وزر «ادعم الفريق»، علماً أن الموقع يعتمد رابطَي اختصار إعلانيين لتحقيق الدخل [59][61][62].",
    },
    {
        "num": "لوحة ٨",
        "file": "eternaldream-nov11-photo4-asmar-ban-replies.jpg",
        "title": "سجال مخاطر الحظر (Ban) في الأونلاين ووصف التعريب بأنه «تعريب خارجي» (10–11 نوفمبر 2026)",
        "caption": "المرفق الرابع من بيان تحذير @EternalDreamAR، ويوثق ردود @AsmarGamesAR المطمئنة للاعبين بشأن عدم وقوع حظر في الأونلاين مقابل تحذيرات الفرق الأصلية [61].",
    },
    {
        "num": "لوحة ٩",
        "file": "mansour-addendum2-photo2-hesham-omori-tweet.png",
        "title": "ردّ هشام (@Arabic_Hesham) وإطلاقه موقع المقارنة البرمجية لـ OMORI بنسبة 6.95% (11 نوفمبر 2026)",
        "caption": "الردّ الذي نقل السجال من الاتهام المرسل إلى المقارنة الإحصائية الشاملة عبر نشر 13,162 مدخلاً نصياً للفحص العلني على omori-comparison.pages.dev [63][64].",
    },
    {
        "num": "لوحة ١٠",
        "file": "mansour-addendum2-photo1-hesham-hk-tweet.png",
        "title": "إطلاق هشام لموقع مقارنة أخطاء وركاكة Hollow Knight (12 نوفمبر 2026)",
        "caption": "التغريدة التي أعلن فيها هشام جمع 28 مثالاً موثقاً من نصوص تعريب Hollow Knight للرد على حجة أن صعوبة النص راجعة لبلاغته الأدبية فحسب [67][72].",
    },
    {
        "num": "لوحة ١١",
        "file": "hesham-may31-greek-modder-credit.jpg",
        "title": "رسالة المترجم اليوناني Yiannis لاستئذان هشام في استخدام حزمة أدواته مفتوحة المصدر (31 مايو 2026)",
        "caption": "وثيقة استشهد بها هشام لإبراز التباين بين احترام المعدلين الأجانب لحقوق أدواته التقنية مفتوحة المصدر في لعبة 007 First Light وبين سرقة تعريباته المجانية وبيعها محلياً [40][66].",
    },
    {
        "num": "لوحة ١٢",
        "file": "l3btk-nov11-ters-oot-guide-thumb.jpg",
        "title": "الواجهة الفنية لتعريب ودبلجة «ص» (@sbalhatlani) الفردية بالذكاء الاصطناعي لريميك أوكارينا الزمن (نوفمبر 2026)",
        "caption": "غلاف الشرح المرئي لقناة «لوعبتك» حول الإصدار الذي أنتجه «ص» (@sbalhatlani، Ters.co) بمفرده كصانع فردي بالاعتماد الكامل على الذكاء الاصطناعي نصاً ودبلجةً لـ 681 مقطعاً صوتياً [42][54][55].",
    },
    {
        "num": "لوحة ١٣",
        "file": "athbistudio-nov11-notice.jpg",
        "title": "بيان «تنويه مهم» الصادر عن عذبي (AthbiStudio) ضد منتحلي اسمه وبائعي تعريباته المجانية (11 نوفمبر 2026)",
        "caption": "وثيقة رسمية نشرها عذبي (@athbistudio، مؤسس عالم ثنائي الأبعاد 2dq8 سابقاً) مساء 11 نوفمبر 2026 تؤكد مجانية أعماله وتحذر من المواقع المنتحلة لاسمه أو المطالبة بالمال مقابل رقع تعريباته [75][78].",
    },
]

ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

# Small eight-pointed star (two squares) with a single "pixel" at its heart:
# the book's recurring mark, shared with the cover medallion.
STAR_MARK = (
    '<svg width="{s}mm" height="{s}mm" viewBox="-10 -10 20 20" xmlns="http://www.w3.org/2000/svg">'
    '<g fill="none" stroke="#7a4a21" stroke-width="0.8">'
    '<rect x="-6.3" y="-6.3" width="12.6" height="12.6"/>'
    '<rect x="-6.3" y="-6.3" width="12.6" height="12.6" transform="rotate(45)"/></g>'
    '<rect x="-1.7" y="-1.7" width="3.4" height="3.4" fill="#7a4a21"/></svg>'
)


def to_arabic_num(n: int | str) -> str:
    return str(n).translate(ARABIC_DIGITS)


def has_arabic(text: str) -> bool:
    return bool(re.search(r"[؀-ۿ]", text))


# --------------------------------------------------------------------------- Chrome


def find_chrome() -> str:
    candidates = [
        os.environ.get("CHROME_BIN"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    raise SystemExit("Google Chrome / Chromium not found. Install it or set CHROME_BIN.")


class Chrome:
    """One headless Chrome driven over the DevTools protocol for every render in the build."""

    def __enter__(self) -> "Chrome":
        self.profile = tempfile.mkdtemp(prefix="book-chrome-")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        args = [
            find_chrome(),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={self.profile}",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            "about:blank",
        ]
        if sys.platform.startswith("linux"):
            args.insert(1, "--no-sandbox")
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pages = []
        for _ in range(200):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json") as r:
                    pages = [t for t in json.loads(r.read().decode()) if t.get("type") == "page"]
                if pages:
                    break
            except Exception:
                pass
            time.sleep(0.1)
        if not pages:
            self.__exit__(None, None, None)
            raise RuntimeError("Could not connect to headless Chrome")
        self.ws = websocket.create_connection(pages[0]["webSocketDebuggerUrl"], timeout=1200, suppress_origin=True)
        self._id = 0
        self.send("Page.enable")
        return self

    def __exit__(self, *exc) -> None:
        try:
            self.ws.close()
        except Exception:
            pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)

    def send(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        while True:
            resp = json.loads(self.ws.recv())
            if resp.get("id") == self._id:
                if "error" in resp:
                    raise RuntimeError(f"CDP error in {method}: {resp['error']}")
                return resp["result"]

    def evaluate(self, expression: str, await_promise: bool = False):
        res = self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": await_promise},
        )
        return res.get("result", {}).get("value")

    def load(self, html_path: Path) -> None:
        self.send("Page.navigate", {"url": html_path.resolve().as_uri()})
        name = json.dumps(html_path.name)
        for _ in range(1200):
            if self.evaluate(f"document.readyState === 'complete' && location.href.endsWith({name})"):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError(f"Timed out loading {html_path}")
        self.evaluate("document.fonts.ready.then(() => true)", await_promise=True)
        time.sleep(0.3)

    def pdf(self, html_path: Path, pdf_path: Path) -> None:
        self.load(html_path)
        res = self.send(
            "Page.printToPDF",
            {
                "printBackground": True,
                "preferCSSPageSize": True,
                "displayHeaderFooter": False,
                "generateDocumentOutline": False,
                "generateTaggedPDF": True,
            },
        )
        pdf_path.write_bytes(base64.b64decode(res["data"]))

    def screenshot(self, html_path: Path, width_px: int, height_px: int, scale: float) -> bytes:
        self.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": width_px, "height": height_px, "deviceScaleFactor": scale, "mobile": False},
        )
        try:
            self.load(html_path)
            res = self.send("Page.captureScreenshot", {"format": "png"})
        finally:
            self.send("Emulation.clearDeviceMetricsOverride")
        return base64.b64decode(res["data"])


# --------------------------------------------------------------------------- Fonts


def ensure_plex_fonts() -> None:
    PLEX_DIR.mkdir(parents=True, exist_ok=True)
    base = "https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexsansarabic/"
    for name in [f"IBMPlexSansArabic-{w}.ttf" for w in PLEX_WEIGHTS.values()] + ["OFL.txt"]:
        dest = PLEX_DIR / name
        if not dest.exists():
            print(f"      downloading {name} ...")
            with urllib.request.urlopen(base + name) as r:
                dest.write_bytes(r.read())


def plex_font_face_css() -> str:
    rules = []
    for weight, name in PLEX_WEIGHTS.items():
        uri = (PLEX_DIR / f"IBMPlexSansArabic-{name}.ttf").resolve().as_uri()
        rules.append(
            f'@font-face {{ font-family: "IBM Plex Sans Arabic"; font-weight: {weight}; '
            f'font-style: normal; src: url("{uri}") format("truetype"); }}'
        )
        # Plex's Latin letters and European digits are drawn larger than its Arabic; this alias
        # sets them slightly smaller so mixed lines keep an even colour.
        rules.append(
            f'@font-face {{ font-family: "Plex Latin"; font-weight: {weight}; font-style: normal; '
            f'src: url("{uri}") format("truetype"); size-adjust: 91%; '
            f'unicode-range: U+0030-0039, U+0040-005A, U+005F, U+0061-007A, U+00C0-024F; }}'
        )
    return "\n".join(rules)


# --------------------------------------------------------------------------- Markdown → HTML


def image_to_data_uri(path: Path, max_width: int = 1500, quality: int = 88) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > max_width:
            new_h = int(im.height * (max_width / im.width))
            im = im.resize((max_width, new_h), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")


def fix_tight_lists(md_text: str) -> str:
    """Markdown needs a blank line between a paragraph and the list that follows it;
    the manuscript often omits it, which used to glue whole lists into one paragraph."""
    out: list[str] = []
    prev = ""
    for line in md_text.splitlines():
        if (
            _LIST_ITEM.match(line)
            and prev.strip()
            and not _LIST_ITEM.match(prev)
            and not prev.startswith((" ", "\t"))
            and not prev.lstrip().startswith(("|", ">"))
        ):
            out.append("")
        out.append(line)
        prev = line
    return "\n".join(out)


def strip_nav_lines(md_text: str) -> str:
    # Replace repository file mentions in the prose with natural book cross-references
    md_text = md_text.replace("في ملف [`references.md`](../references.md)", "في [قائمة المراجع والمصادر الموثقة](#sec_references)")
    md_text = md_text.replace("قائمة [`references.md`](references.md)", "[قائمة المراجع والمصادر الموثقة](#sec_references)")
    md_text = md_text.replace("في [`references.md`](references.md)", "في [قائمة المراجع والمصادر الموثقة](#sec_references)")
    md_text = md_text.replace("داخل مجلد [`evidence/`](../evidence/INDEX.md)", "ضمن [ملحق الوثائق المصوَّرة](#sec_plates) وأرشيف الأدلة")
    md_text = md_text.replace("داخل مجلد [`evidence/`](evidence/INDEX.md)", "ضمن [ملحق الوثائق المصوَّرة](#sec_plates) وأرشيف الأدلة")
    md_text = md_text.replace("(`timeline.md`)، ودليل الفاعلين والفرق (`people-and-teams.md`)", "ومعجم الشخصيات والفرق")

    cleaned = []
    for line in md_text.splitlines():
        s = line.strip()
        if (s.startswith("[→") or s.startswith("[←") or s.startswith("[الفهرس الرئيسي")) and "|" in s:
            continue
        cleaned.append(line)
    while cleaned and cleaned[-1].strip() == "":
        cleaned.pop()
    if cleaned and cleaned[-1].strip() == "---":
        cleaned.pop()
    return "\n".join(cleaned)


def readable_url_label(url: str) -> str:
    decoded = urllib.parse.unquote(url)
    if len(decoded) > 88:
        decoded = decoded[:85] + "…"
    return html.escape(decoded)


def postprocess_html_fragment(frag: str, link_citations: bool = True) -> str:
    # 1. Point repository-relative markdown links at their place in the book
    def repl_href(m: re.Match) -> str:
        href = m.group(1)
        key = href.removeprefix("../").removeprefix("book/")
        if key in INTERNAL_LINK_MAP:
            return f'href="{INTERNAL_LINK_MAP[key]}"'
        if key.startswith("evidence/"):
            return 'href="#sec_plates"'
        return m.group(0)

    frag = re.sub(r'href="([^"]+)"', repl_href, frag)

    # 2. Code spans become isolated Latin (or Arabic) terms so BiDi never scrambles them
    def repl_code(m: re.Match) -> str:
        inner = m.group(1)
        if has_arabic(inner):
            return f'<span class="code-ar" dir="rtl">{inner}</span>'
        return f'<span class="code-ltr" dir="ltr">{inner}</span>'

    frag = re.sub(r"<code>(.*?)</code>", repl_code, frag, flags=re.S)

    # 3. Auto-link bare URLs and [n] citations that sit in text nodes
    parts = re.split(r"(<[^>]+>)", frag)
    in_anchor = False
    for i, part in enumerate(parts):
        if part.startswith("<"):
            low = part.lower()
            if low.startswith("<a ") or low == "<a>":
                in_anchor = True
            elif low.startswith("</a"):
                in_anchor = False
            continue
        if not in_anchor:
            def repl_bare_url(um: re.Match) -> str:
                raw_url = html.unescape(um.group(1))
                trail = ""
                while raw_url and raw_url[-1] in ".,;:)]»،":
                    trail = raw_url[-1] + trail
                    raw_url = raw_url[:-1]
                safe_href = html.escape(raw_url, quote=True)
                return f'<a href="{safe_href}" class="url-link" dir="ltr">{readable_url_label(raw_url)}</a>{trail}'

            part = re.sub(r"(https?://[^\s<>\"']+)", repl_bare_url, part)
            if link_citations:
                part = re.sub(
                    r"\[(\d{1,3})\]",
                    lambda cm: (
                        f'<a class="cite-ref" dir="ltr" href="#ref-{cm.group(1)}">[{cm.group(1)}]</a>'
                        if 1 <= int(cm.group(1)) <= 130
                        else cm.group(0)
                    ),
                    part,
                )
            parts[i] = part
    frag = "".join(parts)

    # 4. External links whose text is itself a URL are shown decoded and left-to-right
    def repl_url_anchor(m: re.Match) -> str:
        href, text = m.group(1), m.group(2)
        if text.strip().startswith(("http://", "https://")):
            return f'<a href="{href}" class="url-link" dir="ltr">{readable_url_label(html.unescape(text.strip()))}</a>'
        return m.group(0)

    return re.sub(r'<a href="(https?://[^"]+)">(.*?)</a>', repl_url_anchor, frag, flags=re.S)


SECTION_BREAK = '<div class="section-break"><i></i><i></i><i></i></div>'


def render_md_body(md_text: str, section_prefix: str, link_citations: bool = True):
    """Returns (h1_title, body_html, [(h2_id, h2_title), ...])."""
    md_text = fix_tight_lists(strip_nav_lines(md_text))
    h1_title = ""
    rest_lines = []
    for line in md_text.splitlines():
        if not h1_title and line.startswith("# "):
            h1_title = line[2:].strip()
            continue
        if re.match(r"^   - ", line):  # 3-space nested bullets → 4 spaces for Python-Markdown
            line = "    - " + line[5:]
        rest_lines.append(line)

    body = markdown.markdown("\n".join(rest_lines), extensions=["tables", "fenced_code", "sane_lists"])
    body = postprocess_html_fragment(body, link_citations=link_citations)

    # A rule directly before a heading is redundant in print; any other rule becomes an ornament.
    body = re.sub(r"<hr\s*/?>\s*(?=<h[23])", "", body)
    body = re.sub(r"(<hr\s*/?>\s*)+$", "", body.strip())
    body = re.sub(r"<hr\s*/?>", SECTION_BREAK, body)

    h2_entries: list[tuple[str, str]] = []

    def repl_h2(m: re.Match) -> str:
        h2_id = f"sub_{section_prefix}_{len(h2_entries) + 1}"
        h2_entries.append((h2_id, re.sub(r"<[^>]+>", "", m.group(1)).strip()))
        return f'<h2 id="{h2_id}">{m.group(1)}</h2>'

    body = re.sub(r"<h2>(.*?)</h2>", repl_h2, body, flags=re.S)
    return h1_title, body, h2_entries


def style_timeline_badges(timeline_html: str) -> str:
    def repl_td(m: re.Match) -> str:
        content = m.group(1).strip()
        plain = re.sub(r"<[^>]+>", "", content).strip()
        if plain.startswith(("واقعة موثقة", "واقعة وبيانات", "واقعة وأمثلة")) or plain == "الرسالة وشكوى هشام موثقتان":
            return f'<td><span class="badge-verified">{content}</span></td>'
        if "ادعاء" in plain:
            return f'<td><span class="badge-mixed">{content}</span></td>'
        return m.group(0)

    return re.sub(r"<td>(.*?)</td>", repl_td, timeline_html, flags=re.S)


def format_references_html(refs_html: str) -> str:
    """Turns `1. **[1]** ...` items into anchored hanging-number entries."""
    refs_html = re.sub(r"<ol(?:\s+start=\"\d+\")?>", '<div class="ref-list">', refs_html)
    refs_html = refs_html.replace("</ol>", "</div>")

    def repl_li_ref(m: re.Match) -> str:
        body = m.group(1).strip()
        num_match = re.search(r"<strong>\[(\d{1,3})\]</strong>", body)
        if num_match:
            rnum = num_match.group(1)
            body = re.sub(
                r"<strong>\[" + rnum + r"\]</strong>",
                f'<span class="ref-badge" dir="ltr">[{rnum}]</span>',
                body,
                count=1,
            )
            return f'<div id="ref-{rnum}" class="ref-card">{body}</div>'
        return f'<div class="ref-subitem">{body}</div>'

    ul_blocks: list[str] = []

    def stash_ul(um: re.Match) -> str:
        ul_blocks.append(um.group(0))
        return f"@@UL_BLOCK_{len(ul_blocks) - 1}@@"

    # Only the first list on the page is the introduction; nested <ul> blocks are stashed so the
    # top-level <li> regex cannot match inside them.
    head, sep, tail = refs_html.partition('<div class="ref-list">')
    tail = re.sub(r"<ul>.*?</ul>", stash_ul, tail, flags=re.S)
    tail = re.sub(r"<li>(.*?)</li>", repl_li_ref, tail, flags=re.S)
    for idx, blk in enumerate(ul_blocks):
        tail = tail.replace(f"@@UL_BLOCK_{idx}@@", blk)
    return head + sep + tail


def split_title_subtitle(h1_title: str, fallback_title: str) -> tuple[str, str]:
    h1_title = h1_title.replace("`", "")
    cleaned = re.sub(r"^(المقدمة والمنهجية|مدخل[ُ\s]*الكتاب|فاتحة[ُ\s]*الكتاب|الفصل[ُ\s]*\S+)\s*:\s*", "", h1_title).strip()
    if "—" in cleaned:
        main, sub = cleaned.split("—", 1)
        return main.strip(), sub.strip()
    if ":" in cleaned and not cleaned.endswith(")"):
        main, sub = cleaned.split(":", 1)
        return main.strip(), sub.strip()
    return cleaned or fallback_title, ""


def build_plates_html(src_for=None) -> str:
    """src_for(plate) gives the image address for the web edition; print embeds the image itself."""
    cards = []
    for p in ARCHIVAL_PLATES:
        data_uri = src_for(p) if src_for else image_to_data_uri(ROOT / "evidence/media" / p["file"])
        cap_html = postprocess_html_fragment(html.escape(p["caption"]), link_citations=True)
        cards.append(
            f"""
            <figure class="plate">
              <div class="plate-head">
                <span class="plate-num">{p["num"]}</span>
                <span class="plate-title">{html.escape(p["title"])}</span>
              </div>
              <div class="plate-img"><img src="{data_uri}" alt="{html.escape(p['title'])}" /></div>
              <figcaption>{cap_html}</figcaption>
            </figure>
            """
        )
    return "\n".join(cards)


# --------------------------------------------------------------------------- Interior document


def opener_html(label: str, title: str, subtitle: str) -> str:
    sub = f'<p class="opener-sub">{html.escape(subtitle)}</p>' if subtitle else ""
    return f"""
      <header class="opener">
        <div class="opener-label">{label}</div>
        <h1>{html.escape(title)}</h1>
        {sub}
        <div class="opener-end"><i></i><i></i><i></i></div>
      </header>"""


def text_section(key: str, sec_id: str, label: str, title: str, subtitle: str, body: str, extra_class: str = "") -> str:
    return f"""
    <section id="{sec_id}" class="book-section page-{key} {extra_class}">
      {opener_html(label, title, subtitle)}
      <div class="chapter-body">
        {body}
      </div>
    </section>"""


def living_note_html() -> str:
    """The standing invitation to correct the book (colophon page and web edition)."""
    return f"""<div class="colophon-note">
      <div class="note-kicker">طبعةٌ قيدَ التحرير</div>
      <h2>كتابٌ حيٌّ ما زالَ يُكتَب</h2>
      <p>هذا السِّفرُ لم يُغلَقْ بعدُ، وما زالَ مِدادُه رطباً. نكتبُه على مرأىً من أهلِ الدارِ وشهودِ الحكاية، ونعلمُ أنَّ ذاكرةَ ثلاثةِ عقودٍ أوسعُ من أنْ يحيطَ بها قلمٌ واحد.</p>
      <p>فإنْ وقعتَ فيه على خطأٍ في اسمٍ أو تاريخ، أو واقعةٍ غابتْ، أو فضلٍ نُسبَ إلى غيرِ أهلِه، فلا تطوِ الصفحةَ ساكتاً: افتحْ بلاغاً (<span class="code-ltr" dir="ltr">Issue</span>) أو قدِّمْ طلبَ دمجٍ (<span class="code-ltr" dir="ltr">Pull Request</span>) في مستودعِ الكتابِ على <span class="code-ltr" dir="ltr">GitHub</span>، لنتحاورَ فيه بالدليلِ ونُصلحَه معاً. فكلُّ تصويبٍ منك أمانةٌ تُردُّ إلى أهلِها، وسطرٌ جديدٌ يُضافُ إلى هذه السيرة.</p>
      <a class="note-repo" dir="ltr" href="{REPO_URL}">{REPO_URL.removeprefix("https://")}</a>
    </div>"""


def colophon_card_html(cover_font_note: str) -> str:
    return f"""<div class="colophon-card">
    <h2>بطاقة الكتاب والضوابط المنهجية</h2>
    <ul>
      <li><strong>رسالة الوفاء والحياد:</strong> يفتتح هذا الكتاب أبوابه بفاتحة شكر وعرفان لجميع المعرِّبين العرب عبر أكثر من ثلاثة عقود (١٩٩٣ – ١٢ نوفمبر ٢٠٢٦)، ملتزماً بنقل القصة الكاملة لتعريب الألعاب وخلافاتها بحيادٍ تامٍّ دون انتصار لطرف على طرف.</li>
      <li><strong>البناء السردي الواضح:</strong> يسير الكتاب في بابين مستقلين: <strong>الباب الأول لرواية قصة البناء والمنجزات أولاً</strong> بتسلسلها الزمني الطبيعي، يليه <strong>الباب الثاني لتشريح الخلافات والإشكالات</strong> في سياقها التاريخي حتى لا يضلَّ القارئ في تشابك الأحداث.</li>
      <li><strong>الفصل الصارم بين الوقائع والادعاءات:</strong> تُسند كل معلومة إلى مرجعها المرقَّم <span class="code-ltr" dir="ltr">[n]</span> في الثبت الببليوغرافي المكوَّن من ١٣٠ مرجعاً، مع التمييز الصريح بين <strong>الوقائع الثابتة بالوثائق الأولية</strong> و<strong>الادعاءات المنسوبة لأصحابها</strong>.</li>
      <li><strong>دقة التوصيف:</strong> التزم الكتاب بتحرير طبيعة كل فاعل بدقة (التمييز بين الفرق الجماعية البشرية مثل «الحلم المتجدد» و«خارقو العادة» و«آفاق التعريب»، والصنّاع الأفراد في المنهج الهجين مثل عذبي <span class="code-ltr" dir="ltr">@athbistudio</span> مؤسس <span class="code-ltr" dir="ltr">2dq8</span> و<span class="code-ltr" dir="ltr">AthbiStudio</span>، والمطورين الأفراد العاملين بالذكاء الاصطناعي الكامل مثل هشام <span class="code-ltr" dir="ltr">@Arabic_Hesham</span> و«ص» <span class="code-ltr" dir="ltr">@sbalhatlani</span> الذي أعاد عام ٢٠٢٢ تأسيس «شبكة ترس» في طورها الحديث <span class="code-ltr" dir="ltr">Ters.co</span> بعد أن أسّس عذبي طورها القديم <span class="code-ltr" dir="ltr">TersNetwork</span>).</li>
    </ul>
    <dl class="colophon-facts">
      <dt>العنوان</dt><dd>{BOOK_TITLE_PLAIN}</dd>
      <dt>تأليف وتوثيق</dt><dd>{BOOK_AUTHOR_AR}</dd>
      <dt>الطبعة</dt><dd>الطبعة التوثيقية الموسَّعة — محرَّرة حتى مساء ١٢ نوفمبر ٢٠٢٦</dd>
      <dt>القطع</dt><dd>١٧ × ٢٤ سم</dd>
      <dt>الخطوط</dt><dd>{cover_font_note}</dd>
      <dt>المستودع</dt><dd><a class="code-ltr" dir="ltr" href="{REPO_URL}">{REPO_URL.removeprefix("https://")}</a></dd>
    </dl>
    </div>"""


def collect_book_parts(plate_src=None):
    """Renders every part of the book once, for the print and the web edition alike.
    Returns (sections, outline, chunks): sections is the ordered list of {key, id, kind, running},
    outline feeds the table of contents and the bookmarks, chunks is [(section id, html)]."""
    sections: list[dict] = []
    outline: list[dict] = []
    chunks: list[tuple[str, str]] = []  # (section id, html)

    def add(key, sec_id, kind, running, html_str, badge, toc_title, bookmark, children):
        sections.append({"key": key, "id": sec_id, "kind": kind, "running": running})
        outline.append(
            {"id": sec_id, "badge": badge, "title": toc_title, "full_bookmark": bookmark, "children": children, "kind": kind}
        )
        chunks.append((sec_id, html_str))

    # Preface and roll of honour
    pref_h1, pref_body, pref_h2 = render_md_body(
        (ROOT / "book/00-preface-and-gratitude.md").read_text(encoding="utf-8"), "preface", link_citations=False
    )
    pref_body = pref_body.replace(
        "<p><strong>التوقيع:</strong><br />\n<strong>شبكة ترس - الحديثة</strong></p>",
        '<div class="signature"><div class="sig-label">التوقيع</div><div class="sig-name">شبكة ترس - الحديثة</div></div>',
    )
    if len(pref_h2) >= 2:
        pref_body = pref_body.replace(f'<h2 id="{pref_h2[1][0]}">', f'<h2 id="{pref_h2[1][0]}" class="honor-roll-heading">', 1)
    pref_main, pref_sub = split_title_subtitle(pref_h1, "كلمة وفاء وبيان")
    add(
        "preface", "sec_preface", "preface", "فاتحة الكتاب: كلمة وفاء وديوان العرفان",
        text_section("preface", "sec_preface", "فاتحةُ الكتاب", pref_main, pref_sub, pref_body, "preface-section"),
        "الفاتحة", "كلمةُ وفاءٍ وبيان، وديوانُ العرفانِ لجميعِ المعرِّبين", "فاتحة الكتاب: كلمة وفاء وديوان العرفان", pref_h2,
    )

    # Table of contents placeholder (filled in below once every entry is known)
    sections.append({"key": "toc", "id": "sec_toc", "kind": "toc", "running": "فهرس المحتويات"})
    chunks.append(("sec_toc", "@@TOC@@"))

    # Chapters, with the two part dividers
    for ch_key, badge, running_short, path in CHAPTER_SPEC:
        if ch_key in PART_DIVIDERS:
            p = PART_DIVIDERS[ch_key]
            part_html = f"""
            <section id="{p['id']}" class="part-page">
              <div class="part-kicker">{p['badge']}</div>
              <div class="part-mark">{STAR_MARK.format(s=11)}</div>
              <h1 class="part-title">{html.escape(p['title'])}</h1>
              <div class="part-rule"></div>
              <p class="part-subtitle">{html.escape(p['subtitle'])}</p>
              <p class="part-desc">{html.escape(p['desc'])}</p>
            </section>"""
            add(p["id"], p["id"], "part", "", part_html, p["badge"], p["toc_title"], p["bookmark"], [])

        h1_raw, body_html, h2_list = render_md_body(path.read_text(encoding="utf-8"), ch_key)
        main_title, sub_title = split_title_subtitle(h1_raw, running_short)
        sec_id = f"sec_{ch_key}"
        add(
            ch_key, sec_id, "chapter", running_short,
            text_section(ch_key, sec_id, badge, main_title, sub_title, body_html),
            badge,
            f"{main_title} — {sub_title}" if (badge == "مدخل الكتاب" and sub_title) else main_title,
            f"{badge}: {main_title}", h2_list,
        )

    # Appendix 1: archival plates
    add(
        "app1", "sec_plates", "appendix", "الملحق الأول: الوثائق المصوَّرة",
        text_section(
            "app1", "sec_plates", "الملحق التوثيقي الأول", "الوثائق واللوحات الأرشيفية المصوَّرة",
            "نماذج مصوَّرة منتقاة من المنشورات والمقارنات والشواهد المحفوظة في أرشيف الكتاب (١٩٩٣ – ١٢ نوفمبر ٢٠٢٦)",
            build_plates_html(plate_src), "plates-section",
        ),
        "الملحق الأول", "الوثائق واللوحات الأرشيفية المصوَّرة (13 لوحة)", "الملحق الأول: الوثائق واللوحات المصوَّرة", [],
    )

    # Appendix 2: timeline
    _, tl_body, tl_h2 = render_md_body((ROOT / "timeline.md").read_text(encoding="utf-8"), "timeline")
    add(
        "app2", "sec_timeline", "appendix", "الملحق الثاني: السجل الزمني الشامل",
        text_section(
            "app2", "sec_timeline", "الملحق التوثيقي الثاني", "السجل الزمني الشامل للأحداث والخلافات",
            "جدول كرونولوجي مؤرخ من عام ١٩٩٣ حتى مساء ١٢ نوفمبر ٢٠٢٦ مع بيان درجة التوثيق",
            style_timeline_badges(tl_body), "timeline-section",
        ),
        "الملحق الثاني", "السجل الزمني الشامل للأحداث والخلافات (1993–2026)", "الملحق الثاني: السجل الزمني الشامل", tl_h2,
    )

    # Appendix 3: people and teams
    _, pt_body, pt_h2 = render_md_body((ROOT / "people-and-teams.md").read_text(encoding="utf-8"), "people")
    add(
        "app3", "sec_people", "appendix", "الملحق الثالث: معجم الشخصيات والفرق",
        text_section(
            "app3", "sec_people", "الملحق التوثيقي الثالث", "معجم الشخصيات والفرق والمبادرات",
            "بطاقات تعريفية محايدة للرواد والفرق التطوعية ومطوري الذكاء الاصطناعي والمنصات",
            pt_body, "people-section",
        ),
        "الملحق الثالث", "معجم الشخصيات والفرق والمبادرات", "الملحق الثالث: معجم الشخصيات والفرق", pt_h2,
    )

    # Bibliography
    _, ref_body, ref_h2 = render_md_body((ROOT / "references.md").read_text(encoding="utf-8"), "refs", link_citations=False)
    add(
        "refs", "sec_references", "appendix", "قائمة المراجع والمصادر الموثقة",
        text_section(
            "refs", "sec_references", "الثبت الببليوغرافي", "قائمة المراجع والمصادر الموثقة",
            "١٣٠ مرجعاً أولياً وثانوياً مع الروابط الكاملة ونسخ الأرشيف وتاريخ التحقق (١٢ نوفمبر ٢٠٢٦)",
            format_references_html(ref_body), "references-section",
        ),
        "المراجع", "قائمة المراجع والمصادر الموثقة ([1] – [130])", "قائمة المراجع والمصادر الموثقة", ref_h2,
    )

    return sections, outline, chunks


def build_interior_html(page_map: dict[str, int] | None, blanks: set[str], cover_font_note: str, fonts: dict):
    """Returns (html, outline_spec, sections) for the print interior; every section opens on a recto page."""
    sections, outline, chunks = collect_book_parts()

    # Table of contents
    def page_of(dest: str) -> str:
        if not page_map:
            return "••"
        return to_arabic_num(page_map[dest]) if dest in page_map else ""

    toc_rows = []
    for item in outline:
        row_cls = {"part": "toc-part", "appendix": "toc-appendix"}.get(item["kind"], "toc-chapter")
        toc_rows.append(
            f"""<div class="toc-entry {row_cls}"><a href="#{item['id']}" class="toc-link">
                  <span class="toc-badge">{item['badge']}</span>
                  <span class="toc-title">{html.escape(item['title'])}</span>
                  <span class="toc-dots"></span><span class="toc-page">{page_of(item['id'])}</span></a></div>"""
        )
        for sub_id, sub_title in item["children"]:
            toc_rows.append(
                f"""<div class="toc-entry toc-sub"><a href="#{sub_id}" class="toc-link">
                      <span class="toc-title">{html.escape(sub_title)}</span>
                      <span class="toc-dots"></span><span class="toc-page">{page_of(sub_id)}</span></a></div>"""
            )
    toc_html = f"""
    <section id="sec_toc" class="book-section page-toc toc-section">
      {opener_html("دليلُ القراءة", "فهرس المحتويات", "")}
      <div class="toc-list">{''.join(toc_rows)}</div>
    </section>"""

    blank = '<div class="blank-page">&nbsp;</div>'
    body_html = "\n".join(
        (blank if sec_id in blanks else "") + (toc_html if chunk == "@@TOC@@" else chunk) for sec_id, chunk in chunks
    )

    # Running heads and folios: book title on verso (right-hand) pages, section title on
    # recto (left-hand) pages, folio centred at the foot.
    # Titles, headings and running heads use the display face (Thmanyah when installed); text stays in Plex.
    head_family = f'{fonts["head"]}, "Plex Latin", "IBM Plex Sans Arabic", sans-serif'
    head_style = f'font-family: {head_family}; font-size: 7.8pt; font-weight: 400; color: #6b6b6b; vertical-align: bottom; padding-bottom: 6.5mm;'
    page_rules = []
    for s in sections:
        if s["kind"] == "part":
            continue
        running = s["running"].replace("\\", "\\\\").replace('"', '\\"')
        page_rules.append(
            f"""
            @page page_{s['key']} {{
              @bottom-center {{ content: counter(page, arabic-indic); font-family: "IBM Plex Sans Arabic"; font-size: 9pt; font-weight: 500; color: #000; vertical-align: top; padding-top: 8mm; }}
            }}
            @page page_{s['key']}:left {{ @top-left {{ content: "{running}"; {head_style} }} }}
            @page page_{s['key']}:right {{ @top-right {{ content: "{BOOK_TITLE_PLAIN}"; {head_style} }} }}
            .page-{s['key']} {{ page: page_{s['key']}; }}"""
        )

    css = (
        plex_font_face_css() + "\n" + fonts["css"] + "\n"
        + f":root {{ --head: {head_family}; }}\n"
        + (SCRIPTS / "book.css").read_text(encoding="utf-8")
        + "\n".join(page_rules)
    )

    t1, t2 = "بَيَانُ الضَّادِ", "فِي مَمَالِكِ الخَيَال"
    doc = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="utf-8" />
<title>{BOOK_TITLE_PLAIN} — {BOOK_AUTHOR_AR}</title>
<style>
{css}
</style>
</head>
<body>

  <section class="fm-page half-title">
    <div class="ht-title">{BOOK_TITLE_AR}</div>
    <div class="ht-mark">{STAR_MARK.format(s=8)}</div>
  </section>

  <!-- The link gives the contents page a named destination, which is how its page number is found. -->
  <div class="blank-page"><a href="#sec_toc">&nbsp;</a></div>

  <section class="fm-page title-page">
    <div class="tp-series">سلسلة التوثيق الرقمي لذاكرة الألعاب في العالم العربي</div>
    <div class="tp-main">
      <div class="tp-kicker">سِفْرٌ تاريخيٌّ وتوثيقيٌّ محقَّق</div>
      <h1><span>{t1}</span><span class="tp-l2">{t2}</span></h1>
      <div class="tp-mark">{STAR_MARK.format(s=11)}</div>
      <p class="tp-sub">{BOOK_SUBTITLE_AR}</p>
      <div class="tp-author-label">تأليف وتوثيق</div>
      <div class="tp-author">{BOOK_AUTHOR_AR}</div>
    </div>
    <div class="tp-foot">
      <div class="tp-imprint">١٩٩٣ م — ١٢ نوفمبر ٢٠٢٦ م</div>
      <div>الطبعة التوثيقية الموسَّعة</div>
    </div>
  </section>

  <section class="fm-page colophon-page">
    {living_note_html()}
    {colophon_card_html(cover_font_note)}
  </section>

  {body_html}

</body>
</html>
"""
    return doc, outline, sections


def extract_page_map(pdf_path: Path) -> dict[str, int]:
    doc = pymupdf.open(pdf_path)
    page_map = {k: int(v["page"]) + 1 for k, v in doc.resolve_names().items() if "page" in v}
    doc.close()
    return page_map


def render_interior(chrome: Chrome, tmp: Path, cover_font_note: str, fonts: dict):
    """Lays the interior out until page numbers settle and every section opens on a recto page."""
    page_map: dict[str, int] | None = None
    blanks: set[str] = set()
    for attempt in range(1, 8):
        doc_html, outline, sections = build_interior_html(page_map, blanks, cover_font_note, fonts)
        html_path = tmp / f"interior_{attempt}.html"
        pdf_path = tmp / f"interior_{attempt}.pdf"
        html_path.write_text(doc_html, encoding="utf-8")
        chrome.pdf(html_path, pdf_path)
        new_map = extract_page_map(pdf_path)
        missing = [s["id"] for s in sections if s["id"] not in new_map]
        if missing:
            raise RuntimeError(f"Sections missing from the rendered PDF: {missing}")
        # Recto pages are the odd ones; a section that would land on an even page gets a blank verso
        # first. Each blank pushes everything after it, so walk the sections in order from where they
        # would start with no blanks at all.
        new_blanks: set[str] = set()
        seen_blanks = 0
        for s in sections:
            seen_blanks += s["id"] in blanks
            natural_start = new_map[s["id"]] - seen_blanks
            if (natural_start + len(new_blanks)) % 2 == 0:
                new_blanks.add(s["id"])
        print(f"      pass {attempt}: {pymupdf.open(pdf_path).page_count} pages, {len(new_blanks)} blank versos")
        if new_map == page_map and new_blanks == blanks:
            return pdf_path, html_path, new_map, outline, sections
        page_map, blanks = new_map, new_blanks
    raise RuntimeError("Interior layout did not converge")


def check_binding_side(doc: pymupdf.Document, page_no: int) -> None:
    """Guards the mirrored margins: on an odd (recto, left-hand) page the wide margin must be on the right."""
    page = doc[page_no - 1]
    h = page.rect.height
    words = [w for w in page.get_text("words") if 0.25 * h < w[1] < 0.8 * h]
    if not words:
        return
    left = min(w[0] for w in words) / MM
    right = (page.rect.width - max(w[2] for w in words)) / MM
    gutter_on_right = right > left
    if abs(right - left) < 2 or gutter_on_right != (page_no % 2 == 1):
        raise RuntimeError(
            f"Binding margin is on the wrong side on page {page_no} (left {left:.1f} mm, right {right:.1f} mm). "
            "This Chrome version maps @page :left/:right differently; swap them in scripts/book.css."
        )


def finish_interior(raw_pdf: Path, page_map: dict[str, int], sections: list[dict]) -> pymupdf.Document:
    doc = pymupdf.open(raw_pdf)
    check_binding_side(doc, page_map["sec_ch01"] + 1)
    check_binding_side(doc, page_map["sec_ch01"] + 2)
    # Chapter-opening pages carry no running head (CSS cannot address "first page of a section").
    for s in sections:
        if s["kind"] == "part":
            continue
        page = doc[page_map[s["id"]] - 1]
        page.add_redact_annot(pymupdf.Rect(0, 0, page.rect.width, (TOP_MARGIN_MM - 1) * MM), fill=(1, 1, 1))
        page.apply_redactions()
    return doc


def build_bookmarks(page_map: dict[str, int], outline: list[dict], offset: int, with_cover: bool) -> list[list]:
    toc = []
    if with_cover:
        toc.append([1, "الغلاف", 1])
    toc.append([1, "صفحة العنوان", 3 + offset])
    toc.append([1, "بطاقة الكتاب والضوابط المنهجية", 4 + offset])
    in_part = False
    for item in outline:
        pnum = page_map[item["id"]] + offset
        if item["kind"] == "part":
            in_part = True
            toc.append([1, item["full_bookmark"], pnum])
            continue
        if item["kind"] == "appendix":
            in_part = False
        lvl = 2 if in_part else 1
        toc.append([lvl, item["full_bookmark"], pnum])
        for sub_id, sub_title in item["children"]:
            if sub_id in page_map:
                toc.append([lvl + 1, sub_title, page_map[sub_id] + offset])
        if item["kind"] == "preface":
            toc.append([1, "فهرس المحتويات", page_map["sec_toc"] + offset])
    return toc


def set_document_info(doc: pymupdf.Document) -> None:
    doc.set_metadata(
        {
            "title": f"{BOOK_TITLE_AR} — {BOOK_SUBTITLE_AR}",
            "author": BOOK_AUTHOR_AR,
            "subject": "سيرة تاريخية وتوثيقية محايدة لتعريب الألعاب غير الرسمي وخلافاته في العالم العربي من 1993 إلى 12 نوفمبر 2026",
            "keywords": "بيان الضاد في ممالك الخيال, تعريب الألعاب, تاريخ التعريب, شبكة ترس",
            "creator": "شبكة ترس - الحديثة",
            "producer": "Chromium + PyMuPDF",
        }
    )
    cat = doc.pdf_catalog()
    doc.xref_set_key(cat, "Lang", "(ar)")
    doc.xref_set_key(cat, "ViewerPreferences", "<</DisplayDocTitle true /Direction /R2L>>")


# --------------------------------------------------------------------------- Main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paper-mm-per-page", type=float, default=0.06,
                    help="paper thickness per page used for the spine width (default 0.06 ≈ 80 g/m² book paper)")
    ap.add_argument("--spine-mm", type=float, default=None, help="spine width from your printer; overrides the estimate")
    ap.add_argument("--keep-html", type=Path, default=None, help="directory to keep the intermediate HTML/PDF files in")
    ap.add_argument("--deploy", action="store_true", help="publish the web edition to the gh-pages branch (GitHub Pages)")
    args = ap.parse_args()

    import check_facts  # scripts/check_facts.py
    import cover        # scripts/cover.py
    import web          # scripts/web.py

    problems = check_facts.run_checks()
    if problems:
        print("\n".join(problems))
        raise SystemExit(f"\n{len(problems)} موضع يخالف سجل الحقائق (FACTS.md). صحّحها ثم أعد البناء.")

    ensure_plex_fonts()
    cover_fonts = cover.find_cover_fonts()
    if cover_fonts["thmanyah"] and cover_fonts["cover_font"]:
        family = cover_fonts["cover_font"].removesuffix(" Black").removesuffix(" Bold").removesuffix(" Regular")
        cover_font_note = (
            f'IBM Plex Sans Arabic للمتن، وخط ثمانية للعناوين، وخط <span class="code-ltr" dir="ltr">{family}</span> للغلاف'
        )
    elif cover_fonts["thmanyah"]:
        cover_font_note = "IBM Plex Sans Arabic للمتن، وخط ثمانية للعناوين والغلاف"
    else:
        cover_font_note = "IBM Plex Sans Arabic"

    with tempfile.TemporaryDirectory() as tmpdir, Chrome() as chrome:
        tmp = Path(tmpdir)
        print("[1/5] Laying out the interior ...")
        raw_pdf, _, page_map, outline, sections = render_interior(chrome, tmp, cover_font_note, cover_fonts)
        interior = finish_interior(raw_pdf, page_map, sections)
        n_pages = interior.page_count
        interior_pdf = tmp / "interior.pdf"
        interior.save(interior_pdf, garbage=4, deflate=True)
        interior.close()

        print("[2/5] Writing the print interior ...")
        PRINT_DIR.mkdir(exist_ok=True)
        printed = pymupdf.open(interior_pdf)
        padded = math.ceil(n_pages / 4) * 4
        for _ in range(padded - n_pages):
            printed.new_page(-1, width=TRIM_W_MM * MM, height=TRIM_H_MM * MM)
        printed.set_toc(build_bookmarks(page_map, outline, offset=0, with_cover=False))
        set_document_info(printed)
        printed.save(PRINT_INTERIOR, garbage=4, deflate=True)
        printed.close()

        spine_mm = args.spine_mm if args.spine_mm is not None else round(padded * args.paper_mm_per_page, 1)
        print(f"[3/5] Building the cover (spine {spine_mm} mm for {padded} pages) ...")
        wrap_pdf, front_pdf, back_pdf = cover.build_cover(chrome, tmp, spine_mm, cover_fonts, plex_font_face_css())

        wrap = pymupdf.open(wrap_pdf)
        page = wrap[0]
        b = cover.BLEED_MM * MM
        trim = pymupdf.Rect(b, b, page.rect.width - b, page.rect.height - b)
        page.set_bleedbox(page.rect)
        page.set_trimbox(trim)
        wrap.set_metadata({"title": f"{BOOK_TITLE_PLAIN} — الغلاف", "author": BOOK_AUTHOR_AR})
        wrap.save(PRINT_COVER, garbage=4, deflate=True)
        wrap.close()

        print("[4/5] Assembling the reading edition ...")
        book = pymupdf.open(interior_pdf)
        front, back = pymupdf.open(front_pdf), pymupdf.open(back_pdf)
        book.insert_pdf(front, start_at=0)
        book.insert_pdf(back)
        book.set_toc(build_bookmarks(page_map, outline, offset=1, with_cover=True))
        set_document_info(book)
        book.save(OUTPUT_PDF, garbage=4, deflate=True)
        total = book.page_count
        book.close()

        print("[5/5] Building the web edition ...")
        web_pages = web.build_site(sys.modules[__name__], cover_fonts, cover_font_note, front_pdf, back_pdf, SITE_DIR)
        if args.deploy:
            remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
            web.deploy(SITE_DIR, remote, DEPLOY_NAME, DEPLOY_EMAIL)
            print(f"      published to the gh-pages branch of {remote}")

        if args.keep_html:
            args.keep_html.mkdir(parents=True, exist_ok=True)
            for f in tmp.iterdir():
                if f.is_file():
                    shutil.copy(f, args.keep_html / f.name)

    mb = lambda p: p.stat().st_size / (1024 * 1024)
    print()
    print(f"Reading edition  {OUTPUT_PDF.relative_to(ROOT)}  ({total} pages, {mb(OUTPUT_PDF):.1f} MB)")
    print(f"Print interior   {PRINT_INTERIOR.relative_to(ROOT)}  ({padded} pages incl. {padded - n_pages} blank at the end, {mb(PRINT_INTERIOR):.1f} MB)")
    print(f"Print cover      {PRINT_COVER.relative_to(ROOT)}  "
          f"({2 * TRIM_W_MM + spine_mm:.1f} x {TRIM_H_MM:.0f} mm trim + {cover.BLEED_MM:.0f} mm bleed, spine {spine_mm} mm, {mb(PRINT_COVER):.1f} MB)")
    print(f"Web edition      {SITE_DIR.relative_to(ROOT)}/index.html  ({web_pages} pages)")
    if not cover_fonts["thmanyah"]:
        print()
        print("NOTE: the Thmanyah typeface was not found, so the cover uses IBM Plex Sans Arabic as a stand-in.")
        print(f"      Download it from https://font.thmanyah.com/ and put the font files in {cover.PRIVATE_FONTS.relative_to(ROOT)}/")
        print("      (or set THMANYAH_FONT_DIR), then run this script again.")


if __name__ == "__main__":
    sys.path.insert(0, str(SCRIPTS))
    main()
