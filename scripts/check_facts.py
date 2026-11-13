#!/usr/bin/env python3
"""
Guards the settled facts of the book (see FACTS.md).

Every fact the author has corrected is recorded here with the wordings that must never come back.
The build runs this first and stops, naming the file and line, if any of them reappears.

  .venv/bin/python scripts/check_facts.py

To record a new correction: add it to FACTS.md, then add an entry below whose `forbidden` patterns
match the old, wrong wording (regular expressions; tashkeel is ignored when matching).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Everything a reader can see: chapters, appendices, README, the evidence notes written for the
# book, and the text hard-coded in the build scripts. Archived third-party pages are not checked.
SOURCES = [
    "book/*.md", "people-and-teams.md", "timeline.md", "references.md", "README.md",
    "evidence/INDEX.md", "evidence/posts/*.md", "evidence/pages/*.md",
    "scripts/build_pdf.py", "scripts/cover.py", "scripts/web.py",
]

FACTS = [
    {
        "id": "ح١",
        "fact": "عذبي هو مؤسس «شبكة ترس» القديمة (TersNetwork)، و«ص» أعاد تأسيسها عام ٢٠٢٢ ولم يؤسس طورها القديم.",
        "forbidden": [
            r"sbalhatlani[^\n|]{0,80}مؤسس[^\n|]{0,6}TersNetwork",
            r"بقيادة مؤسسه \*\*ص",
            r"اعلن \*\*ص\*\*[^\n]{0,90}الافتتاح",
            r"\*\*ص\*\* \(`TersNetwork`\)",
            r"`@sbalhatlani` / `TersNetwork`",
        ],
    },
    {
        "id": "ح٢",
        "fact": "كل ما صدر باسم TersNetwork قبل عام ٢٠٢٢ يعود إلى عذبي، وهو شخص واحد عُرف بالأسماء q8fft و Juza و 2dq8 و TersNetwork و AthbiStudio.",
        "forbidden": [
            r"بواكير اعماله التقنية",          # the 2013–2015 tools were once credited to ص
            r"`TersNetwork` 2012 ← `Ters\.co` 2026",
        ],
    },
    {
        "id": "ح٣",
        "fact": "تبدأ سيرة الكتاب والباب الأول والفصل الأول عام ١٩٩٣ (بدء العمل على «الكابتن ماجد ٢»). أما ١٩٩٥ فهو طرح الخرطوشة، ومنه يبدأ الباب الثاني وفصله الخامس.",
        "forbidden": [
            r"\((?:١٩٩٥|1995)\s*[–-]\s*(?:٢٠٢٦|2026)\)",          # Part Two (١٩٩٥ – ١٢ نوفمبر ٢٠٢٦) is allowed
            r"ارشيف الكتاب \((?:١٩٩٥|1995)",
            r"الباب الثاني[^\n|]{0,60}\((?:٢٠٠٦|2006)\s*[–-]",   # Part Two and chapter 5 start in 1995
            r"الجذور الاولى للخصام[^\n|)]{0,140}\((?:٢٠٠٦|2006)[–-]",
            r"\((?:١٩٩٥|1995)\s*[–-]\s*(?:٢٠١٠|2010)\)",
            r"من عام (?:١٩٩٥|1995) حتى",
            r"خط عام ١٩٩٥",
            r"واحد وثلاثين عاما",                # the span to 2026 is counted from 1993: thirty-three years
            r"تسعة وعشرين عاما \((?:١٩٩٥|1995)",
        ],
    },
    {
        "id": "ح٥",
        "fact": "مطالبة Blizzard بتعريب World of Warcraft في BlizzCon 2016 هي لـ«ص» نفسه من حسابه الشخصي، لا لعذبي ولا لشبكة ترس القديمة.",
        "forbidden": [
            r"(?:خاطب|طالب) عذبي[^\n]{0,90}Blizzard",
            r"مطالبة عذبي[^\n]{0,60}(?:Blizzard|BlizzCon)",
        ],
    },
    {
        "id": "ح٦",
        "fact": "«ص» هو نفسه Dragonarab؛ لا يُكتب @Dragonarab كأنه طرف آخر، وإضافة WoWvo يملكها Platine وص شريك فيها.",
        "forbidden": [
            r"بالتكامل مع (?:حساب )?`@Dragonarab`",
            r"اتبعها باضافة \*\*`WoWvo`",
        ],
    },
    {
        "id": "ح٤",
        "fact": "لا يُسمّى الكتاب ولا ملفاته ولا مستودعه بكلمة disputes.",
        "forbidden": [r"disputes"],
        "sources": ["README.md", "scripts/*.py", "scripts/*.css"],
    },
]

_TASHKEEL = re.compile(r"[ً-ْٰـ]")


def _plain(text: str) -> str:
    """Drops tashkeel and unifies alef/hamza forms so a pattern matches however the line is vocalised."""
    text = _TASHKEEL.sub("", text)
    return text.translate(str.maketrans("أإآ", "ااا"))


def check_reference_count() -> list[str]:
    """Fact ح٧: every stated number of references equals the number of entries in references.md."""
    actual = len(re.findall(r"^\d+\. \*\*\[\d+\]\*\*", (ROOT / "references.md").read_text(encoding="utf-8"), flags=re.M))
    to_int = lambda s: int(s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
    stated = re.compile(r"`?([0-9٠-٩]{2,3})`? مرجعا|\[1\]`? (?:الى|–) `?\[([0-9]{2,3})\]")
    problems = []
    for path in sorted({p for g in SOURCES for p in ROOT.glob(g)}):
        if path.name == "check_facts.py":
            continue
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for m in stated.finditer(_plain(line)):
                number = to_int(m.group(1) or m.group(2))
                if number != actual and number > 100:   # smaller numbers are counts of other things
                    problems.append(f"{path.relative_to(ROOT)}:{no}  يخالف ح٧: يذكر {number} مرجعاً والعدد الفعلي {actual}.")
    return problems


def run_checks() -> list[str]:
    problems = check_reference_count()
    for fact in FACTS:
        files = sorted({p for g in fact.get("sources", SOURCES) for p in ROOT.glob(g)})
        patterns = [re.compile(_plain(pat)) for pat in fact["forbidden"]]
        for path in files:
            if path.name == "check_facts.py":
                continue
            for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                plain = _plain(line)
                for pat in patterns:
                    m = pat.search(plain)
                    if m:
                        problems.append(
                            f"{path.relative_to(ROOT)}:{no}  يخالف {fact['id']}: «{m.group(0)[:70]}»\n"
                            f"      الحقيقة المعتمدة: {fact['fact']}"
                        )
    return problems


if __name__ == "__main__":
    found = run_checks()
    if found:
        print("\n".join(found))
        sys.exit(f"\n{len(found)} موضع يخالف سجل الحقائق (FACTS.md).")
    print(f"سجل الحقائق: {len(FACTS) + 1} حقائق، لا مخالفات.")
