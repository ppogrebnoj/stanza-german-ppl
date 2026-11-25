# -*- coding: utf-8 -*-
"""Нормализация «битого» текста перед нарезкой (Q13: чинить автоматически).

ЧТО ЧИНИМ. Только технический мусор, который появляется при копировании из PDF/Word
и который ломает разбор или подсчёт слов. Видимые слова, пунктуация и порядок слов
НЕ меняются.

| Что | Пример | Почему |
|---|---|---|
| неразрывные и «тонкие» пробелы (U+00A0, U+202F, U+2009 …) | `bei\u00a0der` | Stanza склеивает или рвёт блок при подсчёте символов |
| мягкий перенос (U+00AD) | `gear\u00adbeitet` | невидим, но попадает в слово |
| нулевой ширины (U+200B, U+FEFF) | `habe\u200b` | приклеивается к слову |
| неразрывный дефис (U+2011), типографский (U+2010), минус (U+2212) | `Sanit\u2011är` | Stanza режет `Sanit‑är` на три токена |
| лигатуры (ﬁ ﬂ ﬀ …) | `ef\ufb01zient` | слово перестаёт быть словом |
| прямые кавычки `"` (если их чётное число) | `"…"` → `„…“` | немецкие кавычки: иначе запрет «рез после открывающей» не работает |
| апостроф `'` | `geht's` → `geht’s` | типографика |
| переводы строк внутри абзаца, табы, двойные пробелы | `Firma\n  gearbeitet` | из PDF: каждая строка = предложение |
| пробел перед знаком `, . ; : ! ?` | `Firma , gearbeitet` | знак должен прилипать к слову |

ЧЕГО НЕ ДЕЛАЕМ. Не правим слова, опечатки, порядок слов, `–`/`—` (это настоящая
пунктуация), не меняем стиль кавычек `«…»`, `„…“`, не трогаем `...`.

  python rule/normalize.py --text "Ich habe\u00a0bei der Firma gearbeitet."
  python rule/normalize.py --file страница.txt --show
  python rule/normalize.py --self-test
"""
import argparse
import json
import os
import re
import sys

# неразрывные и «тонкие» пробелы -> обычный пробел
SPACES = {
    "\u00a0": " ", "\u1680": " ", "\u2000": " ", "\u2001": " ", "\u2002": " ",
    "\u2003": " ", "\u2004": " ", "\u2005": " ", "\u2006": " ", "\u2007": " ",
    "\u2008": " ", "\u2009": " ", "\u200a": " ", "\u202f": " ", "\u205f": " ",
    "\u3000": " ",
}
# невидимые символы -> удалить
DROP = {"\u00ad", "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}
# дефисы/минусы, которые Stanza не понимает -> обычный дефис
HYPHENS = {"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2212": "-"}
# лигатуры -> буквы
LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
             "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st"}
APOSTROPHES = {"\u2018": "\u2019", "\u02bc": "\u2019", "'": "\u2019"}

RULES = [
    ("nbsp", "неразрывные/тонкие пробелы"),
    ("invisible", "невидимые символы (мягкий перенос, нулевой ширины, BOM)"),
    ("hyphen", "неразрывный дефис / типографский дефис / минус"),
    ("ligature", "лигатуры"),
    ("quotes", "прямые кавычки -> немецкие „ “"),
    ("apostrophe", "прямой апостроф -> ’"),
    ("newline", "переводы строк и табы внутри абзаца"),
    ("spaces", "двойные пробелы"),
    ("punct_space", "пробел перед знаком препинания"),
]


def normalize(text: str):
    """(чистый текст, список правок). Правки: [{"rule": id, "count": n}, …]."""
    fixes = []

    def note(rule, n):
        if n:
            fixes.append({"rule": rule, "count": n})

    t = text
    n = sum(t.count(ch) for ch in SPACES)
    for ch, to in SPACES.items():
        t = t.replace(ch, to)
    note("nbsp", n)

    n = sum(t.count(ch) for ch in DROP)
    for ch in DROP:
        t = t.replace(ch, "")
    note("invisible", n)

    n = sum(t.count(ch) for ch in HYPHENS)
    for ch, to in HYPHENS.items():
        t = t.replace(ch, to)
    note("hyphen", n)

    n = sum(t.count(ch) for ch in LIGATURES)
    for ch, to in LIGATURES.items():
        t = t.replace(ch, to)
    note("ligature", n)

    # прямые кавычки: превращаем в „…“ только если их чётное число
    q = t.count('"')
    if q and q % 2 == 0:
        out, open_q = [], True
        for ch in t:
            if ch == '"':
                out.append("\u201e" if open_q else "\u201c")
                open_q = not open_q
            else:
                out.append(ch)
        t = "".join(out)
        note("quotes", q)

    n = sum(t.count(ch) for ch in APOSTROPHES)
    for ch, to in APOSTROPHES.items():
        t = t.replace(ch, to)
    note("apostrophe", n)

    before = t
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\t", " ")
    t = re.sub(r"[ ]*\n[ ]*", " ", t)          # перенос строки внутри абзаца -> пробел
    t = re.sub(r" {2,}", " ", t)               # двойные пробелы
    note("newline", 0 if t == before else 1)

    before = t
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)     # «Firma ,» -> «Firma,»
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r"\s+\)", ")", t)
    t = t.strip()
    note("punct_space", 0 if t == before else 1)
    return t, fixes


def describe(fixes) -> str:
    """Человекочитаемо: «неразрывные пробелы ×2, мягкий перенос ×1»."""
    if not fixes:
        return "правок нет"
    name = dict(RULES)
    return ", ".join(f"{name.get(f['rule'], f['rule'])} ×{f['count']}" for f in fixes)


# ------------------------------------------------------------------ самопроверка

CASES = [
    ("Ich habe\u00a0bei der Firma gearbeitet.",
     "Ich habe bei der Firma gearbeitet."),
    ("Ich habe bei der Firma gear\u00adbeitet.",
     "Ich habe bei der Firma gearbeitet."),
    ("Ich habe\u200b bei der Firma gearbeitet.",
     "Ich habe bei der Firma gearbeitet."),
    ("Bereich Sanit\u2011är- und Heizungstechnik.",
     "Bereich Sanit-är- und Heizungstechnik."),
    ("Die Firma ist ef\ufb01zient.", "Die Firma ist effizient."),
    ('"Wer mehr Geld will, muss mehr arbeiten", sagte er.',
     "\u201eWer mehr Geld will, muss mehr arbeiten\u201c, sagte er."),
    ('"Wer mehr Geld will, sagte er.', '"Wer mehr Geld will, sagte er.'),
    ("Er sagt, geht's nicht.", "Er sagt, geht\u2019s nicht."),
    ("Ich  habe   bei der Firma  gearbeitet.", "Ich habe bei der Firma gearbeitet."),
    ("Ich habe bei der Firma , gearbeitet.", "Ich habe bei der Firma, gearbeitet."),
    ("Zeile eins\nZeile zwei\tEnde.", "Zeile eins Zeile zwei Ende."),
    ("Das ist \u2013 wie gesagt \u2013 wichtig.", "Das ist \u2013 wie gesagt \u2013 wichtig."),
    ("\ufeffIch hei\u00dfe Tom.", "Ich heiße Tom."),
]


def self_test(verbose=True) -> int:
    bad = 0
    for src, want in CASES:
        got, _fixes = normalize(src)
        if got != want:
            bad += 1
            if verbose:
                print(f"  FAIL: {src!r}\n        получилось {got!r}\n        ожидалось  {want!r}")
    if verbose:
        print(f"  нормализация: {len(CASES) - bad}/{len(CASES)} кейсов")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--show", action="store_true", help="напечатать очищенный текст")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 1 if self_test() else 0
    text = a.text or (open(a.file, encoding="utf-8").read() if a.file else None)
    if not text:
        ap.print_help()
        return 2
    clean, fixes = normalize(text)
    if a.json:
        print(json.dumps({"clean": clean, "fixes": fixes}, ensure_ascii=False, indent=1))
    else:
        print(f"правок: {describe(fixes)}")
        if a.show:
            print(clean)
    return 0


if __name__ == "__main__":
    sys.exit(main())
