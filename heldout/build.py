#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборка отложенной выборки (150 немецких предложений) для оценки сегментации.

Разбиение исходных текстов на предложения делает сам Stanza-токенизатор
(тот же, что в проекте) — поэтому каждое предложение набора гарантированно
воспринимается пайплайном как одно предложение.

Источники (открытые лицензии, кроме написанных вручную):
  * de.wikipedia.org       — энциклопедический (CC BY-SA)
  * de.wikinews.org        — новостной (CC BY 2.5)
  * de.wikisource.org      — литературный (Kafka, «Превращение»; PD)
  * de.wikibooks.org       — инструкции/рецепты (CC BY-SA)
  * gesetze-im-internet.de — юридический/официальный (amtliches Werk, § 5 UrhG)
  * StaGE 2024 (локальная) — простая речь (CC BY-SA)
  * вручную                — заявление/резюме и разговорный/чат

Запуск:  python heldout/build.py [--from-cache]
Выход:   heldout_150.jsonl, heldout_150.md, coverage.md, hard_inputs.md
"""
import csv
import html
import json
import os
import random
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RULE = os.path.join(ROOT, "MCP-stanza-german-RULE")
sys.path.insert(0, os.path.join(RULE, "reference"))

MODEL_DIR = os.environ.get(
    "STANZA_MODEL_RESOURCES",
    r"C:/Users/BIGTER/AppData/Local/StanfordNLP/stanza/Cache/1.15.0/resources",
)
CACHE = os.path.join(tempfile.gettempdir(), "heldout_pool.json")
SEED = 11
UA = {"User-Agent": "heldout-corpus-builder/1.0 (evaluation set)"}


# ---------------------------------------------------------------- helpers
def _raw(url, tries=3):
    for k in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(3)


def _wm(url):
    time.sleep(1.5)  # Wikimedia rate limit
    return _raw(url)


def _strip(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"[ \t\r\f\v]+", " ", html.unescape(h))


BAD = re.compile(
    r"(==|\{\{|\}\}|\||\[|\]|https?:|www\.|Bitte keine|Veröffentlicht\s*:"
    r"|Datei:|Kategorie:|&#|\\\\|Wikinews|Hauptseite)"
)
MONTH_YEAR = re.compile(
    r"\b(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)"
    r"\s+\d{4}\b"
)
CITE = re.compile(r"(Zugleich|ISBN|Hrsg\.|Aufl\.|Bd\.\s|M\.Dv|L\.Dv|DIN\s?\d|Nr\.\s?\d|S\.\s?\d{1,3}\b|Katalog der Deutschen Nationalbibliothek|deutsche Übersetzung|Originaltitel|Literatur von und über)")


def _clean(s):
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[-\u2013\u2014]\s*", "", s)
    return s.strip()


def _ok(s, lo=8, hi=50):
    if not s or BAD.search(s):
        return False
    if not (lo <= len(s.split()) <= hi):
        return False
    if not re.search(r"[.!?]$", s):
        return False
    if len(re.findall(r"[A-Za-zÄÖÜäöüß]", s)) < 20:
        return False
    if re.search(r"\s[.,;:!?)]", s):          # пробел перед знаком
        return False
    if re.search(r"\w\s+-\w", s):            # «FDP -Innenexperte»
        return False
    if re.search(r"\d\.$", s):               # обрыв на дате: «... vom 3.»
        return False
    if "•" in s or "In:" in s:               # остатки списков
        return False
    if "  " in s:
        return False
    if MONTH_YEAR.search(s):                 # заголовки/даты из шапки
        return False
    if re.search(r"\b(Dr|Prof|Nr|Abs|Art|bzw|usw|ca|vgl)\.$", s):  # обрезано на сокращении
        return False
    if s[:1].islower():                        # обрывок
        return False
    if re.search(r"\w\.\w", s):                # нет пробела после точки
        return False
    if s.count("„") != s.count("“") or s.count("«") != s.count("»") or s.count('"') % 2:
        return False                           # непарные кавычки
    if CITE.search(s):                         # ссылки/библиография
        return False
    return True


# ---------------------------------------------------------------- sources: raw bodies
def body_wikipedia():
    out = []
    for t in ["Sprachwissenschaft", "Fahrrad", "Klimawandel", "Buchdruck"]:
        q = urllib.parse.urlencode({"action": "query", "prop": "extracts", "explaintext": 1,
                                    "format": "json", "titles": t})
        d = json.loads(_wm("https://de.wikipedia.org/w/api.php?" + q).decode("utf-8"))
        ex = next(iter(d["query"]["pages"].values())).get("extract", "") or ""
        # отрезать хвост статьи: литература/ссылки (там библиография, а не проза)
        ex = re.split(r"\n(?:Literatur|Einzelnachweise|Weblinks|Belege|Quellen|Anmerkungen|Fußnoten|Siehe auch|Literaturhinweise)\n", ex)[0]
        if len(ex) > 500:
            out.append(("wiki", "de.wikipedia.org: " + t, ex))
    return out


def body_kafka():
    q = urllib.parse.urlencode({"action": "parse", "page": "Die Verwandlung (Franz Kafka)",
                                "prop": "text", "format": "json", "formatversion": 2})
    d = json.loads(_wm("https://de.wikisource.org/w/api.php?" + q).decode("utf-8"))
    t = _strip(d["parse"]["text"])
    i = t.find("Als Gregor Samsa eines Morgens")
    return [("kafka", "de.wikisource.org: Die Verwandlung", t[i:] if i > 0 else t)]


def body_wikinews():
    titles = []
    for term in ["Deutschland Beschluss", "Bundesregierung Gesetz"]:
        q = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": term,
                                    "format": "json", "srlimit": 8, "srnamespace": 0})
        d = json.loads(_wm("https://de.wikinews.org/w/api.php?" + q).decode("utf-8"))
        titles += [x["title"] for x in d["query"]["search"]]
    out = []
    for t in dict.fromkeys(titles):
        q = urllib.parse.urlencode({"action": "parse", "page": t, "prop": "text",
                                    "format": "json", "formatversion": 2})
        try:
            d = json.loads(_wm("https://de.wikinews.org/w/api.php?" + q).decode("utf-8"))
        except Exception:
            continue
        paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", d["parse"]["text"])
        body = " ".join(_strip(p) for p in paras)
        body = re.sub(r"\s+", " ", body).strip()
        m = re.search(r"\d{1,2}\.\d{1,2}\.\d{4}\s*[\u2013-]", body)
        if not m or len(body) < 300:
            continue  # не статья (портал/шапка)
        out.append(("news", "de.wikinews.org: " + t, body[m.end():]))
    return out


def body_wikibooks():
    out = []
    for title in ["Kochbuch/ Kartoffelsalat", "Kochbuch/ Gulasch", "Kochbuch/ Kartoffelpüree",
                  "Kochbuch/ Rührei", "Kochbuch/ Apfelkuchen"]:
        q = urllib.parse.urlencode({"action": "query", "prop": "extracts", "explaintext": 1,
                                    "format": "json", "titles": title})
        try:
            d = json.loads(_wm("https://de.wikibooks.org/w/api.php?" + q).decode("utf-8"))
        except Exception:
            continue
        ex = next(iter(d["query"]["pages"].values())).get("extract", "") or ""
        if len(ex) > 300:
            out.append(("instruction", "de.wikibooks.org: " + title, ex))
    return out


def body_legal():
    paras = ["242", "241", "280", "311", "433", "434", "535", "536", "611", "622", "626",
             "631", "632", "633", "823", "826", "985", "1004", "138", "119", "123", "157",
             "133", "305", "307", "320", "323", "346"]
    out = []
    for n in paras:
        try:
            s = _raw(f"https://www.gesetze-im-internet.de/bgb/__{n}.html").decode("cp1252", "replace")
        except Exception:
            continue
        body = s.split('<div class="jnheader">', 1)
        body = body[1] if len(body) > 1 else s
        absaetze = re.findall(r'<div class="jurAbsatz">(.*?)</div>', body, flags=re.S)
        txt = re.sub(r"\s+", " ", " ".join(_strip(a) for a in absaetze)).strip()
        if len(txt) > 80:
            out.append(("legal", f"gesetze-im-internet.de: BGB § {n}", txt))
        time.sleep(0.2)
    return out


def body_easy():
    path = "C:/tmp/pi-github-repos/german-easy-to-read/statements/data/train.csv"
    out = []
    if not os.path.exists(path):
        return out
    texts = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        s = r["phrase"]
        s = re.sub(r"\\+newline", " ", s)
        s = s.replace("\\n", " ")
        texts.append(s)
    return [("easy", "StaGE 2024 (CC BY-SA)", "\n".join(texts))]


# ---------------------------------------------------------------- manual
HAND_JOB = [
    "Seit fünf Jahren betreue ich Kunden im Außendienst und habe dabei gelernt, auch in schwierigen Situationen ruhig zu bleiben.",
    "Ich bewerbe mich um die Stelle als Projektleiter, weil ich meine Erfahrung im Anlagenbau gerne in Ihr Team einbringen möchte.",
    "Zu meinen Stärken gehören die strukturierte Arbeitsweise, die schnelle Auffassungsgabe und der sichere Umgang mit Excel.",
    "In meiner letzten Position war ich für die Disposition von zwölf Monteuren verantwortlich.",
    "Die von Ihnen ausgeschriebene Stelle entspricht genau meinem Profil.",
    "Ich habe die Möglichkeit genutzt, mich berufsbegleitend zum Techniker weiterzubilden.",
    "Bitte senden Sie Ihre vollständigen Unterlagen bis zum 15. März an die Personalabteilung.",
    "Wir suchen zum nächstmöglichen Zeitpunkt eine engagierte Mitarbeiterin für unsere Buchhaltung.",
    "Neben der Projektierung übernehme ich die Abstimmung mit Lieferanten und die Abrechnung der Baustellen.",
    "Durch meine Tätigkeit als Servicetechniker kenne ich die Anforderungen der Kunden aus erster Hand.",
    "Ich arbeite selbstständig und zuverlässig und bin es gewohnt, Termine auch unter Zeitdruck einzuhalten.",
    "Für Rückfragen stehe ich Ihnen gerne zur Verfügung.",
    "Die Einarbeitung neuer Kollegen gehörte ebenso zu meinen Aufgaben wie die Pflege der Kundendaten.",
    "Ich habe mich entschieden, mich zu verändern, weil ich mich fachlich weiterentwickeln möchte.",
    "Erfahrungen mit SAP und DATEV runden mein Profil ab.",
    "Zum 1. September suche ich eine neue Herausforderung im Bereich Gebäudetechnik.",
    "Meine Gehaltsvorstellung liegt bei 52.000 Euro brutto jährlich.",
    "Im Anhang finden Sie meinen Lebenslauf sowie die wichtigsten Zeugnisse.",
    "Ich freue mich auf ein persönliches Gespräch und verbleibe mit freundlichen Grüßen.",
    "Die Stelle erfordert Reisebereitschaft, Flexibilität und ein sicheres Auftreten beim Kunden.",
    "In den vergangenen Jahren habe ich zahlreiche Projekte im Bereich der Gebäudetechnik begleitet und dabei sowohl die technische Planung als auch die Abstimmung mit den ausführenden Firmen verantwortet.",
    "Da ich sowohl kaufmännische als auch technische Zusammenhänge schnell erfasse, fiel mir der Wechsel von der Werkstatt in die Projektleitung nicht schwer.",
    "Wenn Sie einen Mitarbeiter suchen, der selbstständig arbeitet, Verantwortung übernimmt und sich schnell in neue Aufgabengebiete einarbeitet, freue ich mich auf Ihre Rückmeldung.",
]
HAND_COLL = [
    "Also, ich hab das gestern schon probiert, aber es hat halt nicht funktioniert.",
    "Kannst du mir bitte kurz sagen, wo die Datei liegt, die du gestern geschickt hast?",
    "Das ist echt ärgerlich – ich hatte extra alles doppelt gespeichert.",
    "Ich versteh das nicht: Warum dauert das so lange?",
    "Ja, klar, mach ich, aber erst nach der Mittagspause.",
    "Hat jemand von euch schon mal so was gesehen?",
    "Sorry, ich bin gerade unterwegs, ich melde mich später.",
    "Wenn du willst, können wir das morgen zusammen anschauen.",
    "Das war echt ein Ding – keiner hat damit gerechnet.",
    "Meld dich einfach, wenn du Hilfe brauchst.",
    "Ich hab die Datei gestern noch mal neu gemacht, weil die alte Version ständig Fehler hatte.",
    "Kannst du mir bitte sagen, ob du das Paket schon abgeschickt hast oder ob es noch hier liegt?",
    "Das mit dem Termin am Freitag wird bei mir leider nichts, weil ich da schon unterwegs bin.",
    "Ich hab jetzt dreimal versucht, dich anzurufen, aber es geht immer nur die Mailbox dran.",
]

# Easy Language: только отобранные вручную чистые предложения (в исходном корпусе много обрывков)
EASY_PINNED = [
    "Mit Einfacher Sprache können viele Menschen Texte verstehen.",
    "Im Jahr 1969 ist David Bowie bekannt geworden.",
    "Ich muss der Bank auch etwas dafür bezahlen, wenn sie mir Geld borgt.",
    "Menschen mit viel Kreativität haben Spaß daran, Lösungen für Probleme zu finden.",
    "Manche Christen gehen an Allerheiligen auf den Friedhof.",
    "Anarchismus hat es früher in vielen Ländern gegeben.",
    "Der größte Streit hat im Jahr 1950 angefangen.",
    "Er ist auf einen sehr großen Berg geklettert.",
    'Das Wahrzeichen von Altenburg sind die "Roten Spitzen".',
    "Frankreich hat gesagt: Gustave Eiffel soll den Turm bauen.",
]


def apply_easy_pin(pool):
    rest = [p for p in pool if p["register"] != "easy"]
    rest += [{"register": "easy", "source": "StaGE 2024 (CC BY-SA)", "text": s}
             for s in EASY_PINNED]
    return rest


# (регистр, корзина длины, сколько) — сумма = 150
MATRIX = [
    ("wiki", "S", 4), ("wiki", "M", 15), ("wiki", "L", 9), ("wiki", "XL", 2),
    ("news", "S", 2), ("news", "M", 10), ("news", "L", 7), ("news", "XL", 1),
    ("kafka", "S", 0), ("kafka", "M", 4), ("kafka", "L", 10), ("kafka", "XL", 11),
    ("instruction", "S", 7), ("instruction", "M", 7), ("instruction", "L", 1), ("instruction", "XL", 0),
    ("legal", "S", 0), ("legal", "M", 3), ("legal", "L", 17), ("legal", "XL", 0),
    ("easy", "S", 9), ("easy", "M", 1), ("easy", "L", 0), ("easy", "XL", 0),
    ("job", "S", 7), ("job", "M", 10), ("job", "L", 3), ("job", "XL", 0),
    ("colloquial", "S", 4), ("colloquial", "M", 6), ("colloquial", "L", 0), ("colloquial", "XL", 0),
]
ORDER = ["wiki", "news", "kafka", "instruction", "legal", "easy", "job", "colloquial"]
PREFIX = {"wiki": "W", "news": "N", "kafka": "K", "instruction": "I",
          "legal": "L", "easy": "E", "job": "J", "colloquial": "C"}
REGISTER_RU = {
    "wiki": "энциклопедический (Wikipedia)",
    "news": "новостной (Wikinews)",
    "kafka": "литературный (Kafka, «Превращение»)",
    "instruction": "инструкция/рецепт (Wikibooks)",
    "legal": "юридический/официальный (BGB)",
    "easy": "простая речь (StaGE, Leichte Sprache)",
    "job": "заявление/резюме (вручную)",
    "colloquial": "разговорный/чат (вручную)",
}


def bucket(s):
    n = len(s.split())
    return "S" if n <= 12 else "M" if n <= 20 else "L" if n <= 35 else "XL"


def norm(s):
    return re.sub(r"\W+", " ", s.lower()).strip()


def grams(s, k=5):
    w = re.findall(r"\w+", s.lower())
    return set(tuple(w[i:i + k]) for i in range(max(0, len(w) - k + 1)))


ABBR = re.compile(r"\b(z\.\s?B|d\.\s?h|u\.\s?a|bzw|ca|usw|Dr|Prof|Nr|Abs|Art|Mio|Mrd|EU|USA|km|kg)\b\.?")


def tags(text, words, tokens):
    t = set()
    dep = {w["deprel"] for w in words}
    xpos = {w["xpos"] for w in words}
    lem = {w["lemma"].lower() for w in words}
    if "PRELS" in xpos:
        t.add("relcl")
    if "KOUS" in xpos:
        t.add("subcl")
    if "PTKZU" in xpos:
        t.add("zuinf")
    if "aux:pass" in dep:
        t.add("passive")
    if "cc" in dep:
        t.add("conj")
    if "appos" in dep:
        t.add("appos")
    if any("Case=Gen" in (w.get("feats") or "") for w in words):
        t.add("genitive")
    if any(w["upos"] == "NUM" or w["deprel"] == "nummod" for w in words):
        t.add("nummod")
    if any(len(tk["word_ids"]) > 1 for tk in tokens):
        t.add("mwt")
    if lem & {"nicht", "kein", "keine", "keinen", "keiner", "keinem", "nichts"}:
        t.add("neg")
    if "(" in text or ")" in text:
        t.add("paren")
    if re.search(r"[„“«»\"]", text):
        t.add("quote")
    if ":" in text:
        t.add("colon")
    if ";" in text:
        t.add("semicolon")
    if re.search(r"[\u2013\u2014]", text):
        t.add("dash")
    if ABBR.search(text):
        t.add("abbrev")
    if text.endswith("?"):
        t.add("question")
    if text.endswith("!"):
        t.add("exclam")
    return t


def tidy(s):
    s = re.sub(r"^\s*\(\d+\)\s*", "", s)
    s = re.sub(r"^\s*\d+\.\s+", "", s)
    s = re.sub(r"^\s*[a-z]\)\s*", "", s)
    return s.strip()


def syll(text):
    return sum(max(1, len(re.findall(r"[aeiouäöy]+", w.lower()))) for w in re.findall(r"[A-Za-zÄÖÜäöüß]+", text))


PUNCT = {
    "quote": lambda s: bool(re.search(r"[„“«»\"]", s)),
    "colon": lambda s: ":" in s,
    "semicolon": lambda s: ";" in s,
    "dash": lambda s: bool(re.search(r"[\u2013\u2014]", s)),
    "paren": lambda s: "(" in s or ")" in s,
    "question": lambda s: s.rstrip().endswith("?"),
    "exclam": lambda s: s.rstrip().endswith("!"),
    "abbrev": lambda s: bool(ABBR.search(s)),
}
BOOST = {"quote": 10, "colon": 10, "semicolon": 6, "dash": 8, "paren": 12,
         "question": 8, "exclam": 3, "abbrev": 8}


def build_pool():
    import stanza

    os.environ.setdefault("STANZA_RESOURCES_DIR", MODEL_DIR)
    nlp = stanza.Pipeline(lang="de", processors="tokenize", dir=MODEL_DIR,
                          download_method=None, verbose="ERROR", tokenize_batch_size=64)

    out = []
    for fn in (body_wikipedia, body_kafka, body_wikinews, body_wikibooks, body_legal, body_easy):
        try:
            bodies = fn()
        except Exception as e:  # noqa: BLE001
            print("SKIP", fn.__name__, type(e).__name__, e)
            continue
        print(fn.__name__, "bodies:", len(bodies))
        for reg, src, body in bodies:
            try:
                doc = nlp(body)
            except Exception as e:  # noqa: BLE001
                print("  split fail", src[:50], type(e).__name__)
                continue
            n0 = len(out)
            for s in doc.sentences:
                t = _clean(s.text)
                if _ok(t):
                    out.append({"register": reg, "source": src, "text": t})
            print("  ", src[:60], "+", len(out) - n0)
    for s in HAND_JOB:
        out.append({"register": "job", "source": "вручную (регистр заявления)", "text": s})
    for s in HAND_COLL:
        out.append({"register": "colloquial", "source": "вручную (разговорный/чат)", "text": s})
    return out

def main():
    from_cache = "--from-cache" in sys.argv
    if from_cache and os.path.exists(CACHE):
        pool = json.load(open(CACHE, encoding="utf-8"))
        pool = [p for p in pool if _ok(p["text"], 6 if p["register"] == "kafka" else 8,
                                      26 if p["register"] == "easy" else 50)
                and not (p["register"] == "easy" and re.search(r"\w-\w", p["text"]))]
        print("pool from cache:", len(pool))
    else:
        pool = build_pool()
        json.dump(pool, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)

    pool = apply_easy_pin(pool)

    corpus_path = os.path.join(RULE, "CORPUS", "verified.jsonl")
    corpus = [json.loads(l) for l in open(corpus_path, encoding="utf-8") if l.strip()]
    cg_all = [grams(r["sentence"]) for r in corpus]

    seen, clean = set(), []
    for p in pool:
        n = norm(p["text"])
        if n in seen:
            continue
        g = grams(p["text"])
        if any(len(g & c) / len(g | c) > 0.35 for c in cg_all if g):
            continue
        seen.add(n)
        clean.append(p)
    print("candidates after dedup/leak filter:", len(clean))

    random.seed(SEED)
    by = defaultdict(list)
    for p in clean:
        by[(p["register"], bucket(p["text"]))].append(p)
    for k in by:
        random.shuffle(by[k])

    import rule as R  # noqa: N812

    selected, fails, used = [], [], set()

    def make(reg, text, src):
        text = tidy(text)
        if not text or "|" in text or text in used:
            return None
        try:
            words, tokens, _ = R.parse_sentence(text)
        except ValueError as e:
            if "got " in str(e) and len(fails) < 12:
                fails.append({"register": reg, "source": src, "text": text})
            return None
        except Exception:  # noqa: BLE001
            return None
        # полное предложение должно иметь финитный глагол (кроме инструкций: инфинитив/императив)
        if reg != "instruction" and not any(w["xpos"] in ("VAFIN", "VVFIN", "VMFIN") for w in words):
            return None
        used.add(text)
        return {"register": reg, "source": src, "text": text,
                "words": len(text.split()), "syllables": syll(text),
                "tags": sorted(tags(text, words, tokens)), "blocks": []}

    for reg, bk, need in MATRIX:
        got = 0
        for p in by.get((reg, bk), []):
            if got >= need:
                break
            if bucket(tidy(p["text"])) != bk:
                continue
            row = make(reg, p["text"], p["source"])
            if row:
                selected.append(row)
                got += 1
        if got < need:
            print("SHORT", reg, bk, need, got)

    if len(selected) < 150:
        for reg, bk, need in MATRIX:
            have = sum(1 for r in selected if r["register"] == reg)
            for p in by.get((reg, bk), []):
                if have >= need or len(selected) >= 150:
                    break
                row = make(reg, p["text"], p["source"])
                if row:
                    selected.append(row)
                    have += 1
    if len(selected) < 150:
        rest = [p for p in clean if p["text"] not in used]
        random.shuffle(rest)
        for p in rest:
            if len(selected) >= 150:
                break
            row = make(p["register"], p["text"], p["source"])
            if row:
                selected.append(row)

    def count(kind):
        return sum(1 for r in selected if PUNCT[kind](r["text"]))

    for kind, target in BOOST.items():
        if count(kind) >= target:
            continue
        cands = [p for p in clean if p["text"] not in used and PUNCT[kind](p["text"])]
        random.shuffle(cands)
        for p in cands:
            if count(kind) >= target:
                break
            victims = [r for r in selected
                       if r["register"] == p["register"]
                       and not any(PUNCT[k](r["text"]) for k in BOOST)]
            if not victims:
                victims = [r for r in selected
                           if not any(PUNCT[k](r["text"]) for k in BOOST)]
            if not victims:
                break
            row = make(p["register"], p["text"], p["source"])
            if not row:
                continue
            v = random.choice(victims)
            selected.remove(v)
            used.discard(v["text"])
            selected.append(row)
        if count(kind) < target:
            print("BOOST SHORT", kind, count(kind), target)

    print("selected:", len(selected))

    idx = defaultdict(int)
    for reg in ORDER:
        for r in [x for x in selected if x["register"] == reg]:
            idx[reg] += 1
            r["id"] = f"{PREFIX[reg]}{idx[reg]:02d}"
    rows = [r for reg in ORDER for r in selected if r["register"] == reg]

    with open(os.path.join(HERE, "heldout_150.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    lines = ["# Отложенная выборка: 150 немецких предложений", "",
             "**Назначение:** честная оценка разбивки на смысловые блоки.",
             "**Эти предложения нельзя использовать для написания правил** — только для измерения.",
             "Источники: открытые (Wikipedia/Wikinews/Wikisource/Wikibooks/BGB/StaGE) и написанные вручную.",
             "Ни одно предложение не пересекается с корпусом verified (проверено по 5-граммам).", "",
             "## Как размечать", "",
             "1. Читайте **вслух**. Там, где вы делаете паузу для вдоха или смыслового ударения,",
             "   вставьте ` / ` (пробел, косая черта, пробел) и запишите результат в строку `→`.",
             "2. Ничего не исправляйте: ни порядок слов, ни орфографию, ни кавычки.",
             "   Косую черту внутри слов (CDU/CSU, 90/Die) не трогайте — она не граница.",
             "3. Если пауза не нужна — предложение остаётся без `/` (один блок).",
             "4. Если место спорное — поставьте ` /? ` и вернитесь позже.",
             "",
             "**Пример:**", "",
             "```",
             "[W01] 18 слов · relcl, conj",
             "Die Bundesregierung hat am Mittwoch beschlossen, dass die Förderung verlängert wird.",
             "→ Die Bundesregierung hat / am Mittwoch beschlossen, / dass die Förderung verlängert wird.",
             "```", "",
             "Ориентир: 150 предложений ≈ 2–3 часа; можно частями (по регистру).", "",
             "---", ""]
    for reg in ORDER:
        sub = [r for r in rows if r["register"] == reg]
        if not sub:
            continue
        lines.append(f"## {REGISTER_RU[reg]} — {len(sub)} шт.")
        srcs = sorted({r["source"].split(":")[0] for r in sub})
        lines += [f"*Источники: {', '.join(srcs)}*", ""]
        for r in sub:
            tg = ", ".join(r["tags"]) if r["tags"] else "—"
            lines += [f"**[{r['id']}]** {r['words']} слов · признаки: {tg}", r["text"], "→ ", ""]
        lines += ["---", ""]
    open(os.path.join(HERE, "heldout_150.md"), "w", encoding="utf-8").write("\n".join(lines))

    bks = ["S", "M", "L", "XL"]
    m = [["регистр"] + bks + ["итого"]]
    for reg in ORDER:
        sub = [r for r in rows if r["register"] == reg]
        m.append([reg] + [sum(1 for r in sub if bucket(r["text"]) == b) for b in bks] + [len(sub)])
    m.append(["**итого**"] + [sum(1 for r in rows if bucket(r["text"]) == b) for b in bks] + [len(rows)])

    tc = Counter()
    for r in rows:
        tc.update(r["tags"])
    tag_names = ["relcl", "subcl", "zuinf", "passive", "conj", "appos", "genitive", "nummod",
                 "mwt", "neg", "paren", "quote", "colon", "semicolon", "dash", "abbrev",
                 "question", "exclam"]
    cov = ["# Покрытие отложенной выборки", "",
           f"Предложений: {len(rows)}. Слов: {sum(r['words'] for r in rows)} "
           f"(медиана {sorted(r['words'] for r in rows)[len(rows) // 2]}). "
           f"Слогов в предложении: медиана {sorted(r['syllables'] for r in rows)[len(rows) // 2]} "
           f"(мин. {min(r['syllables'] for r in rows)}, макс. {max(r['syllables'] for r in rows)}).", "",
           "## Регистр × длина", "", "| | " + " | ".join(bks) + " | итого |", "|---|---|---|---|---|"]
    for row in m[1:]:
        cov.append("| " + " | ".join(str(x) for x in row) + " |")
    cov += ["", "Корзины: S = 8–12 слов, M = 13–20, L = 21–35, XL = 36–50.", "",
            "## Синтаксические/пунктуационные признаки", "", "| признак | предложений |", "|---|---|"]
    for t in tag_names:
        cov.append(f"| {t} | {tc.get(t, 0)} |")
    cov += ["", "## Регистры", "", "| регистр | шт. |", "|---|---|"]
    for reg in ORDER:
        cov.append(f"| {reg} | {sum(1 for r in rows if r['register'] == reg)} |")
    open(os.path.join(HERE, "coverage.md"), "w", encoding="utf-8").write("\n".join(cov))

    hard = ["# Трудный ввод (отдельный мини-набор)", "",
            "Эти строки **специально** ломают текущий пайплайн: Stanza видит два предложения",
            "или мешает типографика. В 150 они не входят — это тест для SoMaJo/нормализации.", "",
            "| # | проблема | текст |", "|---|---|---|"]
    for i, f in enumerate(fails, 1):
        hard.append(f"| H{i:02d} | разбивается на 2+ предложения | {f['text']} |")
    hard += [
        "| H91 | типографские кавычки | Ich habe bei der Firma „Paritet-K“ gearbeitet und war sehr zufrieden. |",
        "| H92 | ёлочки вместо лапок | Ich habe bei der Firma «Paritet-K» gearbeitet und war sehr zufrieden. |",
        "| H93 | двоеточие внутри | Zusammenfassend möchte ich sagen: Die Jobsuche ist schnell und modern. |",
        "| H94 | неразрывный пробел | Die Firma\u00a0Müller hat\u00a0im Jahr 2020 insgesamt zwölf Stellen besetzt. |",
        "| H95 | длинное тире | Das Projekt lief gut – bis der Lieferant ausfiel – und dann wurde es teuer. |",
        "| H96 | цифры и даты | Am 1.10.2024 wurden 3.500 Euro überwiesen, also 1.200 Euro mehr als geplant. |",
    ]
    open(os.path.join(HERE, "hard_inputs.md"), "w", encoding="utf-8").write("\n".join(hard))

    print("WROTE: heldout_150.jsonl, heldout_150.md, coverage.md, hard_inputs.md")
    print("registers:", dict(Counter(r["register"] for r in rows)))
    print("buckets:", dict(Counter(bucket(r["text"]) for r in rows)))
    print("tags:", dict(sorted(tc.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    main()
