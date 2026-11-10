# -*- coding: utf-8 -*-
"""Сборка машинных наборов из файлов разметки заказчика (итерация 4 / V3).

Источники:
  ИТЕРАЦИЯ_2/КОРПУС_52_для_разбивки.md      -> bench/sets/corpus52_v3.jsonl
  ИТЕРАЦИЯ_3/heldout_51_150_part1.md        -> bench/sets/heldout_51.jsonl

Почему отдельный парсер: заказчик размечает в markdown, причём
  * в 52-м корпусе последние 8 предложений размечены слэшами В САМОЙ СТРОКЕ
    предложения, а строка «→» осталась пустой (нужно понимать оба варианта);
  * кириллица/латиница в одном строке — границу «немецкий | русский» ищем
    по первому кириллическому символу;
  * слэш бывает частью слова (CDU/CSU, Bündnis 90/Die Grünen) — разделителем
    считаем только слэш, у которого есть пробел слева или справа.

Проверка: склеенные блоки должны дать исходное предложение символ в символ
(после нормализации пробелов). Всё, что не сходится, печатается как ОШИБКА.
"""
import json
import os
import re
import sys

ROOT = r"E:\KI_WORK"
SRC52 = os.path.join(ROOT, "ИТЕРАЦИЯ_2", "КОРПУС_52_для_разбивки.md")
SRC51 = os.path.join(ROOT, "ИТЕРАЦИЯ_3", "heldout_51_150_part1.md")
OUT52 = os.path.join(ROOT, "bench", "sets", "corpus52_v3.jsonl")
OUT51 = os.path.join(ROOT, "bench", "sets", "heldout_51.jsonl")

CYR = re.compile(r"[А-Яа-яЁё]")
SEP = re.compile(r"(?<=\s)/\s*|\s*/(?=\s)")


def unescape(s):
    return re.sub(r"\\([()\[\].\,\-–—])", r"\1", s)


def norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def split_blocks(split_text):
    """Разбить строку разметки на блоки.

    Разделитель — слэш с пробелом хотя бы с одной стороны (CDU/CSU — не разделитель).
    «/ ?» и «/?» (сомнительное место) считаем обычным резом.
    """
    t = norm_ws(unescape(split_text))
    parts = SEP.split(t)
    out = []
    for p in parts:
        p = norm_ws(p)
        if p in ("?", ""):
            continue
        out.append(p)
    return out


def split_de_ru(s):
    """Граница немецкого и русского текста — первый кириллический символ.

    Перед ним может оказаться латиница из русского перевода (W29: «Safety bicycle»,
    N09: Ramelow), поэтому отступаем к последнему концу предложения перед кириллицей.
    """
    m = CYR.search(s)
    if not m:
        return norm_ws(s), ""
    i = m.start()
    prefix = s[:i]
    ends = list(re.finditer(r'[.!?]["“”»„\')]?(?=\s|$)', prefix))
    cut = ends[-1].end() if ends else i
    return norm_ws(s[:cut]), norm_ws(s[cut:])


def fix_leading_punct(blocks):
    """Блок не может начинаться с пунктуации: «von Briefen | , Ansprechen» -> «von Briefen, | Ansprechen»."""
    out, fixed = [], []
    for b in blocks:
        if out and re.match(r'^[,;:.!?]', b):
            m = re.match(r'^([,;:.!?]+)\s*(.*)$', b)
            out[-1] = out[-1] + m.group(1)
            b = m.group(2).strip()
            fixed.append((out[-1], b))
            if not b:
                continue
        out.append(b)
    return out, fixed


def parse_51(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        m = re.match(r"^\*\*\\\[([A-Za-z0-9\-]+)\\\]\*\*\s*(.*)$", line)
        if not m:
            continue
        rid, rest = m.group(1), m.group(2)
        nwords = None
        # признаки — только строчная латиница/запятые/тире; немецкий текст начинается с заглавной
        m2 = re.match(r"^(\d+)\s+слов\s*·\s*признаки:\s*([^A-ZА-ЯЁÜÖÄ]*)(.*)$", rest)
        if not m2:
            raise ValueError(f"{rid}: не разобрал заголовок: {rest[:80]}")
        nwords = int(m2.group(1))
        flags_raw = m2.group(2)
        rest = m2.group(3)
        flags = [] if flags_raw.strip() in ("—", "", "-") else [x.strip() for x in flags_raw.split(",") if x.strip()]
        if "→" not in rest:
            raise ValueError(f"{rid}: нет стрелки")
        left, split_raw = rest.rsplit("→", 1)
        de, ru = split_de_ru(unescape(left))
        blocks, fixed = fix_leading_punct(split_blocks(split_raw))
        rows.append({
            "id": rid,
            "sentence": de,
            "blocks": blocks,
            "translation": ru,
            "flags": flags,
            "n_words_declared": nwords,
            "source": "heldout51",
            "fixed_typos": [f"{a!r} + {b!r}" for a, b in fixed],
        })
    return rows


def parse_52(path):
    rows = []
    text = open(path, encoding="utf-8").read()
    text = text.split("## Приложение")[0]
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^\*\*\[([^\]]+)\]\*\*\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        rid, meta = m.group(1), m.group(2)
        sent_line = lines[i + 1] if i + 1 < len(lines) else ""
        arrow_line = lines[i + 2] if i + 2 < len(lines) else ""
        i += 3
        if rid == "ПРИМЕР":
            continue
        arrow = arrow_line[1:].strip() if arrow_line.startswith("→") else ""
        # два способа разметки: строка «→» или слэши в самом предложении
        if arrow:
            blocks = split_blocks(arrow)
            sentence = unescape(norm_ws(sent_line))
        else:
            blocks = split_blocks(sent_line)
            sentence = norm_ws(SEP.sub(" ", unescape(norm_ws(sent_line))))
            if " / " in sent_line or SEP.search(sent_line):
                sentence = norm_ws(unescape(sent_line))
                # убираем слэши-разделители из текста предложения
                sentence = norm_ws(SEP.sub(" ", sentence))
        rows.append({
            "id": rid,
            "sentence": sentence,
            "blocks": blocks,
            "meta": norm_ws(meta),
            "source": "new",
        })
    return rows


def qa(rows, label):
    print(f"\n=== {label}: {len(rows)} предложений ===")
    bad = 0
    for r in rows:
        joined = norm_ws(" ".join(r["blocks"]))
        sent = norm_ws(r["sentence"])
        if not r["blocks"]:
            print(f"  [пусто] {r['id']}")
            bad += 1
            continue
        if joined != sent:
            bad += 1
            print(f"  [не сходится] {r['id']}")
            # первое расхождение
            k = 0
            while k < min(len(joined), len(sent)) and joined[k] == sent[k]:
                k += 1
            print(f"      предл: ...{sent[max(0,k-25):k+35]!r}")
            print(f"      блоки: ...{joined[max(0,k-25):k+35]!r}")
        if r.get("n_words_declared"):
            from_blocks = len(joined.split())
            from_sent = len(sent.split())
            if from_blocks != from_sent:
                print(f"  [слов не столько] {r['id']}: заявлено {r['n_words_declared']}, "
                      f"в предложении {from_sent}, в блоках {from_blocks}")
    print(f"  проблем: {bad}")
    return bad


def main():
    r51 = parse_51(SRC51)
    r52 = parse_52(SRC52)
    bad = qa(r51, "heldout_51") + qa(r52, "corpus52_v3")
    os.makedirs(os.path.dirname(OUT51), exist_ok=True)
    with open(OUT51, "w", encoding="utf-8") as f:
        for r in r51:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT52, "w", encoding="utf-8") as f:
        for r in r52:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nзаписано: {OUT51} ({len(r51)}), {OUT52} ({len(r52)})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
