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

import hashlib
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
        "fact": "DragonArab («التنين العربي»، @Dragonarab) هو الاسم القديم لـ«ص» نفسه؛ فـ«ص» و @sbalhatlani و DragonArab و DiNaSoR شخص واحد، لا شريكان.",
        "forbidden": [
            r"بالتكامل مع (?:حساب )?`@Dragonarab`",   # @Dragonarab was once written up as a separate partner account
        ],
    },
    {
        "id": "ح٧",
        "fact": "برنامج «المعرب» (Alm3rb، 2009) لموقع 2DQ8 من صنع «ص» (DragonArab) فكرةً وبرمجةً، لا من عمل عذبي؛ وإنما رفعه عذبي (q8fft) إلى ROMhacking.net ثم GitHub.",
        "forbidden": [
            r"اداته الشهيرة[^\n]{0,30}Alm3rb",
            r"لاداته القديمة `?Alm3rb",
            r"برمجة «اداة المعرب»",
            r"عذبي[^\n|]{0,40}(?:اداته|برمجته|برمجة)[^\n|]{0,40}(?:Alm3rb|المعرب)",
            r"اصدار عذبي[^\n|]{0,160}Alm3rb",
            r"واداة \*\*`Alm3rb Convert Script`",  # the old [74] and evidence-note wording
            r"و\*\*«اداة المعرب» \(`Alm3rb`\)\*\* \(ابريل 2009",
            r"(?:Alm3rb|«المعرب»|اداة المعرب)[^\n|]{0,40}(?:لعذبي|من عمل عذبي|من صنع عذبي|من برمجة عذبي)",
        ],
    },
    {
        "id": "ح٨",
        "fact": "لا يُذكر الاسم الحقيقي لـ«ص» ولا بريده الشخصي في الكتاب ولا ملفاته؛ يُشار إليه بـ ص أو DragonArab / التنين العربي أو @sbalhatlani أو DiNaSoR.",
        # The forbidden words are stored only as SHA-256 hashes of their normalised form, so that this
        # public file does not itself spell out the name it protects. Every word of every line is hashed
        # (also joined with the next word, and without a leading و/ب/ل) and compared with this list.
        "forbidden": [r"(?i)dragonarab@"],
        "forbidden_word_hashes": [
            "04f51914fbe18cc20c7c5002374ab9f2ccd8977c4ae41ccf2621d08446268424",
            "055654e9d79b0bfaf0532c668e6b03c11677a6c060b1fdbc94f14f5a83cda574",
            "0f69068de7512d062100d3478787fd6573eb3598a122f031c1d882c48879617a",
            "635edbbb626c094043ebbed7188d7ba99ca8e2afdc8b5ad633bb071cbde9623b",
            "87b07b9dfa92a509662ca0fbf8684b80686b11f6edc3bc30357a08fcb55d2c17",
            "97ac634bbca613400e2360fa0c14fa51a4443fe72ea11076b115389eb132d0fe",
            "d106f86e1421d0d02cacdd43f69d590ec6973ae454572e0bc7f4cdc3dd3aed25",
            "e6ffaf6194e9f0bb760e2d4c7eecb7b146a6da78b1b2e27842879f6c7fb5d17e",
            "e8951bed3ade9fa87ef6ad8b1d3d5731d0d7e47d719c5b5f254374caa78785b5",
        ],
        "sources": SOURCES + ["FACTS.md", "evidence/screenshots/INDEX.md", "evidence/screenshots/index.json", "scripts/*.css"],
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


_WORD = re.compile(r"[0-9A-Za-z\u0621-\u064a]+")


def _hashed_word_hit(plain: str, hashes: set[str]) -> bool:
    """True when a word of the line (lower-cased, also joined with the next word, and without a
    leading و/ب/ل) hashes to one of the protected words."""
    words = [w.lower() for w in _WORD.findall(plain)]
    for i, w in enumerate(words):
        forms = {w, w + words[i + 1] if i + 1 < len(words) else w}
        forms |= {f[1:] for f in forms if len(f) > 3 and f[0] in "وبل"}
        if any(hashlib.sha256(f.encode()).hexdigest() in hashes for f in forms):
            return True
    return False


def run_checks() -> list[str]:
    problems = []
    for fact in FACTS:
        files = sorted({p for g in fact.get("sources", SOURCES) for p in ROOT.glob(g)})
        patterns = [re.compile(_plain(pat)) for pat in fact["forbidden"]]
        hashes = set(fact.get("forbidden_word_hashes", []))
        for path in files:
            if path.name == "check_facts.py":
                continue
            for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                plain = _plain(line)
                if hashes and _hashed_word_hit(plain, hashes):
                    problems.append(
                        f"{path.relative_to(ROOT)}:{no}  يخالف {fact['id']}: «اسم أو بريد محجوب»\n"
                        f"      الحقيقة المعتمدة: {fact['fact']}"
                    )
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
    print(f"سجل الحقائق: {len(FACTS)} حقائق، لا مخالفات.")
