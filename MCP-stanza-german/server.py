#!/usr/bin/env python3
"""Stanza German MCP server (stdio).

Локальный MCP-сервер для синтаксического анализа немецкого языка на базе
Stanford Stanza 1.15.0 (CPU). Работает полностью офлайн: модели берутся из
локального кэша C:\\Users\\BIGTER\\AppData\\Local\\StanfordNLP\\stanza\\Cache\\1.15.0\\resources,
download_method=None — сеть не используется и повторная загрузка не требуется.

Запуск:  python server.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import threading
import time
import datetime

# stdout должен оставаться чистым для MCP-протокола (stdio) и быть UTF-8
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ===================== логирование и версия сервера ==========================
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVER_LOG_FILE = os.path.join(_BASE_DIR, "server.log")
_MAX_LOG_SIZE = 2 * 1024 * 1024

# version.json — текущая версия сервера (см. CHANGELOG.md: история).
def _get_server_version() -> str:
    try:
        with open(os.path.join(_BASE_DIR, "version.json"), "r", encoding="utf-8") as f:
            return str(json.load(f).get("server_version") or "dev")
    except Exception:  # noqa: BLE001
        return "dev"

def _log(msg: str) -> None:
    """Лог в файл (вращение при >2 МБ) + stderr. stdout остаётся чистым."""
    line = "%s %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), msg)
    try:
        if os.path.exists(_SERVER_LOG_FILE) and os.path.getsize(_SERVER_LOG_FILE) >= _MAX_LOG_SIZE:
            os.rename(_SERVER_LOG_FILE, _SERVER_LOG_FILE + ".1")
        with open(_SERVER_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:  # noqa: BLE001
        pass
    try:
        sys.stderr.write(line)
    except Exception:  # noqa: BLE001
        pass

def _run_tool(name: str, fn) -> dict:
    """Обёртка для инструмента: лог start/ok/error + время. Возвращает результат."""
    _log("TOOL %s start" % name)
    t0 = time.perf_counter()
    try:
        res = fn()
    except Exception as exc:  # noqa: BLE001
        _log("TOOL %s ERROR %.1f ms: %s" % (name, (time.perf_counter() - t0) * 1000, str(exc)))
        raise
    ms = (time.perf_counter() - t0) * 1000
    extra = ""
    if isinstance(res, dict):
        v = res.get("verdict")
        if v is not None:
            extra = " verdict=%s" % v
        elif res.get("gate_passed") is not None:
            extra = " gate=%s" % str(res["gate_passed"])
    _log("TOOL %s ok %.1f ms%s" % (name, ms, extra))
    return res

import stanza
from mcp.server.fastmcp import FastMCP

LANGUAGE = "de"
FULL_PROCESSORS = "tokenize,mwt,pos,lemma,depparse,constituency"
CORE_PROCESSORS = "tokenize,mwt,pos,lemma,depparse"

# Правило сегментации (validator.py + config.json) живёт отдельно от сервера.
# Путь — переменная окружения RULE_ROOT (поле env в mcp.json), иначе — дефолт.
RULE_ROOT_DEFAULT = r"E:\KI_WORK\правило"

mcp = FastMCP(
    "stanza-german",
    instructions=(
        "Stanza de: parse_german — синтаксис (леммы/POS/зависимости + MWT-поля); "
        "constituency_german — фразовое дерево; calc_pause — паузы в сек по символам, пакетно; "
        "pipeline_info — статус. Судья правила: check_segmentation (verdict + подсказки), "
        "rule_self_test (регресс на разметке 52), rule_info (версия/параметры/цифры). Офлайн."
    ),
)

_pipeline: stanza.Pipeline | None = None
_pipeline_lock = threading.Lock()
_load_notes: list[str] = []


def _default_chars_per_sec() -> float:
    """Скорость calc_pause по умолчанию (симв./сек): переменная окружения
    STANZA_CHARS_PER_SEC, иначе 4.0. Настраивается полем 'env' записи сервера
    в mcp.json (LM Studio: Program → Install → Edit mcp.json)."""
    raw = os.environ.get("STANZA_CHARS_PER_SEC")
    if not raw:
        return 4.0
    try:
        value = float(raw)
    except ValueError:
        _load_notes.append(f"STANZA_CHARS_PER_SEC='{raw}' — не число, использовано 4.0")
        return 4.0
    if value <= 0:
        _load_notes.append(f"STANZA_CHARS_PER_SEC={value} должно быть > 0, использовано 4.0")
        return 4.0
    return value


DEFAULT_CHARS_PER_SEC = _default_chars_per_sec()


def _load_pipeline() -> stanza.Pipeline:
    """Загружает пайплайн из локального кэша (без сети). При неудаче с полным
    набором процессоров откатывается на ядро tokenize,mwt,pos,lemma,depparse."""
    for processors in (FULL_PROCESSORS, CORE_PROCESSORS):
        try:
            pipe = stanza.Pipeline(
                lang=LANGUAGE,  # в Stanza 1.15 параметр называется lang
                processors=processors,
                download_method=None,  # офлайн: только локальный кэш, без сети
                verbose=False,
            )
            if processors != FULL_PROCESSORS:
                _load_notes.append(
                    f"Загружено ядро процессоров ({processors}); "
                    "constituency недоступен"
                )
            return pipe
        except Exception as exc:  # noqa: BLE001 — фиксируем и пробуем ядро
            _load_notes.append(f"Не удалось загрузить '{processors}': {exc}")
    raise RuntimeError("Stanza pipeline не удалось загрузить: " + "; ".join(_load_notes))


def get_pipeline() -> stanza.Pipeline:
    """Ленивый singleton: пайплайн грузится один раз при первом вызове инструмента."""
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline = _load_pipeline()
    return _pipeline


def _word_dict(d: dict) -> dict:
    """Нормализует запись word из Token.to_dict() (Stanza 1.15)."""
    return {
        "id": d.get("id"),
        "text": d.get("text"),
        "lemma": d.get("lemma"),
        "upos": d.get("upos"),
        "xpos": d.get("xpos"),
        "features": d.get("feats"),
        "head": d.get("head"),
        "dep": d.get("deprel"),
    }


def _sentence_words(doc, s) -> list[dict]:
    """Плоский список слов предложения (с учётом MWT-расширений).

    Каждой записи добавлены is_mwt / mwt_id — ИСТОЧНИК ТОЛЬКО STANZA:
    Token.is_mwt() и Token.id. Без вычисления/гадания из text/lemma/upos.
    Для MWT t.id — диапазон Word-ID (a, b); в JSON — список [a, b].
    Слова одного MWT собираются по mwt_id."""
    words: list[dict] = []
    for t in s.tokens:
        is_mwt = bool(t.is_mwt())
        # МWT — диапазон Word-ID; одиночный токен — свой int id.
        mwid = list(t.id) if len(t.id) > 1 else t.id[0]
        for d in t.to_dict():
            w = _word_dict(d)
            w["is_mwt"] = is_mwt
            w["mwt_id"] = mwid
            words.append(w)
    return words


def _sentence_tokens(doc, s) -> list[dict]:
    """Параллельный список поверхностных токенов: один объект на каждый
    Sentence.token. Содержит MWT-флаг (Token.is_mwt()), явный перечень
    word_ids — Word-ID, входящие в токен, и offsets start_char/end_char.
    Нужен для восстановления поверхностного текста/пунктуации,
    диапазона MWT и вырезания текста блока по позициям символов (SPEC §4)."""
    tokens: list[dict] = []
    for t in s.tokens:
        tokens.append({
            "id": list(t.id) if len(t.id) > 1 else t.id[0],  # int; MWT: [a,b]
            "text": t.text,
            "start_char": t.start_char,  # offset в тексте предложения (SPEC §4)
            "end_char": t.end_char,
            "is_mwt": bool(t.is_mwt()),
            "word_ids": [w.id for w in t.words],
        })
    return tokens


def _texts_arg(text):
    """Нормализация входного текста инструментов анализа: str | list[str] |
    JSON-строка списка '["...","..."]' -> список предложений. Один вызов на
    весь пакет предложений."""
    if isinstance(text, (list, tuple)):
        return [str(t) for t in text]
    if isinstance(text, str):
        s = text.strip()
        if s.startswith("["):
            try:
                arr = json.loads(s)
                if isinstance(arr, list) and arr and all(isinstance(x, str) for x in arr):
                    return arr
            except Exception:  # noqa: BLE001 — обычное предложение со скобкой
                pass
        return [text]
    raise ValueError("text: str | list[str] | JSON-строка списка строк")


def _parse_german_impl(text) -> dict:
    """Синтаксический анализ немецкого текста (Stanza). Возвращает предложения: слова с леммой, UPOS/XPOS, features и зависимостями head/dep; MWT-поля is_mwt (bool) и mwt_id (диапазон Word-ID [a,b] для MWT); parallel list tokens (поверхностные токены с word_ids). Пакет: text = list[str] или JSON-строка списка — все предложения за один вызов; у предложения поле item (номер входного текста, 1-based). Пример: parse_german(["S1.", "S2."])"""
    pipe = get_pipeline()
    sentences = []
    for k, t in enumerate(_texts_arg(text)):
        doc = pipe(t)
        for s in doc.sentences:
            sentences.append({
                "id": len(sentences) + 1,
                "item": k + 1,
                "text": s.text,
                "words": _sentence_words(doc, s),
                "tokens": _sentence_tokens(doc, s),
            })
    return {"language": LANGUAGE, "count": len(sentences), "sentences": sentences}


@mcp.tool()
def parse_german(text: str | list[str]) -> dict:
    return _run_tool("parse_german", lambda: _parse_german_impl(text))

def _constituency_german_impl(text) -> dict:
    """Фразовое дерево Penn Treebank (скобочная запись) по предложениям немецкого текста. Пакет: text = list[str] или JSON-строка списка — все предложения за один вызов; поле item — номер входного текста. Пример: constituency_german(["S1.", "S2."])"""
    pipe = get_pipeline()
    out = []
    for k, t in enumerate(_texts_arg(text)):
        doc = pipe(t)
        for s in doc.sentences:
            tree = s.constituency
            out.append({
                "id": len(out) + 1,
                "item": k + 1,
                "text": s.text,
                "tree": str(tree) if tree is not None else None,
            })
    res = {"language": LANGUAGE, "count": len(out), "sentences": out}
    if any(x["tree"] is None for x in out):
        res["note"] = "constituency недоступен: загружено ядро процессоров без constituency"
    return res




@mcp.tool()
def constituency_german(text: str | list[str]) -> dict:
    return _run_tool("constituency_german", lambda: _constituency_german_impl(text))

def _analyze_german_impl(text) -> dict:
    """parse_german + constituency_german ОДНИМ вызовом для всего пакета:
    text = str | list[str] | JSON-строка списка. На каждое предложение:
    words/tokens (полный разбор) + tree (Penn Treebank). Пример:
    analyze_german(["S1.", "S2.", "S3."])"""
    pipe = get_pipeline()
    out = []
    for k, t in enumerate(_texts_arg(text)):
        doc = pipe(t)
        for s in doc.sentences:
            tree = s.constituency
            out.append({
                "id": len(out) + 1,
                "item": k + 1,
                "text": s.text,
                "words": _sentence_words(doc, s),
                "tokens": _sentence_tokens(doc, s),
                "tree": str(tree) if tree is not None else None,
            })
    res = {"language": LANGUAGE, "count": len(out), "sentences": out}
    if any(x["tree"] is None for x in out):
        res["note"] = "constituency недоступен: загружено ядро процессоров без constituency"
    return res


@mcp.tool()
def analyze_german(text: str | list[str]) -> dict:
    return _run_tool("analyze_german", lambda: _analyze_german_impl(text))

def _calc_pause_impl(texts: str | list[str], chars_per_sec: float = DEFAULT_CHARS_PER_SEC) -> dict:
    """Пауза в секундах: ceil(символы / chars_per_sec), 10/4->3c. Пакетно (list): items + total, тот же ceil. Скорость - симв./сек: по умолч. 4; переопределяется аргументом chars_per_sec или env STANZA_CHARS_PER_SEC. Пример: calc_pause(["..."], chars_per_sec=5)"""
    if chars_per_sec <= 0:
        raise ValueError("chars_per_sec должен быть положительным числом")
    items = [texts] if isinstance(texts, str) else list(texts)
    per_item = []
    total_chars = 0
    for t in items:
        n = len(t)
        total_chars += n
        per_item.append(
            {"characters": n, "pause_seconds": math.ceil(n / chars_per_sec)}
        )
    return {
        "chars_per_sec": chars_per_sec,
        "count": len(items),
        "items": per_item,
        "total": {
            "characters": total_chars,
            "pause_seconds": math.ceil(total_chars / chars_per_sec),
        },
    }



@mcp.tool()
def calc_pause(texts: str | list[str], chars_per_sec: float = DEFAULT_CHARS_PER_SEC) -> dict:
    return _run_tool("calc_pause", lambda: _calc_pause_impl(texts, chars_per_sec))

def _pipeline_info_impl() -> dict:
    """Статус сервера: загруженные процессоры, версии, путь к кэшу, offline-статус."""
    import torch

    pipe = get_pipeline()
    return {
        "server": "stanza-german",
        "server_version": _get_server_version(),
        "log_file": _SERVER_LOG_FILE,
        "language": LANGUAGE,
        "chars_per_sec_default": DEFAULT_CHARS_PER_SEC,
        "processors_loaded": sorted(pipe.processors.keys()),
        "download_method": None,
        "offline": True,
        "model_dir": str(pipe.dir),
        "versions": {
            "python": sys.version.split()[0],
            "stanza": stanza.__version__,
            "torch": torch.__version__,
        },
        "rule_root": _rule_root(),
        "rule_registered": _RULE is not None,
        "notes": list(_load_notes) + ([_RULE_NOTE] if _RULE_NOTE else []),
    }


# ======================= правило сегментации (судья) =========================
# Единственный код правила - validator.py + config.json (раздел
# "segment"). Сервер - тонкая read-only обёртка: судья (check), регресс
# (self_test), паспорт правила (rule_info). config.json перечитывается на
# КАЖДЫЙ вызов: поправили конфиг - сразу действует, рестарт не нужен.
_RULE = None
_RULE_NOTE: str | None = None


@mcp.tool()
def pipeline_info() -> dict:
    return _run_tool("pipeline_info", lambda: _pipeline_info_impl())


RULE_ROOT_LEGACY = r"E:\KI_WORK\MCP-stanza-german-RULE"   # до переименования (итерация 20)


def _rule_root() -> str:
    """Папка правила: env RULE_ROOT -> правило/ -> старое имя (если env не задан)."""
    env = os.environ.get("RULE_ROOT")
    if env:
        return env
    if os.path.exists(os.path.join(RULE_ROOT_DEFAULT, "validator.py")):
        return RULE_ROOT_DEFAULT
    return RULE_ROOT_LEGACY


def _config_path() -> str:
    return os.path.join(_rule_root(), "config.json")


def _regression_set() -> str:
    return os.environ.get(
        "RULE_SET",
        os.path.join(os.path.dirname(_rule_root()), "bench", "sets", "corpus52_v3.jsonl"))


def _load_rule() -> None:
    """Импорт validator.py из RULE_ROOT. Нет правила - сервер работает как раньше,
    инструменты судьи просто не регистрируются (не падает)."""
    global _RULE, _RULE_NOTE
    root = _rule_root()
    path = os.path.join(root, "validator.py")
    if not os.path.exists(path):          # старое имя (reference/validator_v3.py)
        path = os.path.join(root, "reference", "validator_v3.py")
    if not os.path.exists(path):
        _RULE_NOTE = f"правило не подключено: нет {path} (задайте RULE_ROOT)"
        return
    try:
        ref_dir = os.path.dirname(path)
        if ref_dir not in sys.path:
            sys.path.insert(0, ref_dir)   # segment.py импортирует validator.py рядом
        spec = importlib.util.spec_from_file_location("rule_validator", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["rule_validator"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _RULE = mod
    except Exception as exc:  # noqa: BLE001
        _RULE_NOTE = f"правило не подключено: {exc}"


def get_rule():
    if _RULE is None:
        raise RuntimeError(_RULE_NOTE or "validator.py не подключен")
    return _RULE


def rule_config():
    """config.json перечитывается каждый раз - свежее правило без рестарта сервера."""
    return get_rule().load_cfg(_config_path())


def _canonical_hash(cfg: dict) -> str:
    """sha256 канонического JSON - доказательство версии суждения."""
    clean = {k: v for k, v in cfg.items() if not str(k).startswith("_")}
    blob = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _parse_payload(sentence: str) -> dict:
    """Разбор одного предложения в формате parse_german (тот же, что видит LLM)."""
    pipe = get_pipeline()
    doc = pipe(sentence)
    if len(doc.sentences) != 1:
        raise ValueError(
            f"ожидается ровно одно предложение, Stanza дала {len(doc.sentences)}")
    s = doc.sentences[0]
    return {"language": "de", "sentences": [{
        "id": 1, "text": s.text,
        "words": _sentence_words(doc, s), "tokens": _sentence_tokens(doc, s),
    }]}


def _blocks_from_toks(sentence: str, toks: list) -> list[str]:
    """toks=[[a,b],...] (Word-ID, b включительно) -> тексты блоков по смещениям
    символов. Номера слов надёжнее текста блока: защита от опечаток в блоке."""
    tokens = _parse_payload(sentence)["sentences"][0]["tokens"]
    out = []
    for a, b in toks:
        a, b = int(a), int(b)
        start = end = None
        for t in tokens:
            ids = t.get("word_ids") or []
            if not ids:
                continue
            if ids[0] == a:
                start = t["start_char"]
            if ids[-1] == b:
                end = t["end_char"]
        if start is None or end is None:
            raise ValueError(f"блок [{a},{b}] не найден в разборе")
        out.append(sentence[start:end].strip())
    # P2: непарный знак препинания в начале блока уходит в конец предыдущего
    for k in range(1, len(out)):
        m = re.match(r"^([,.;:!?]+)\s*(.*)$", out[k])
        if m and m.group(2):
            out[k - 1] = out[k - 1] + m.group(1)
            out[k] = m.group(2)
    return out


def _check_one(item: dict, with_opinion: bool = False) -> dict:
    cfg = rule_config()
    sentence = (item.get("sentence") or "").strip()
    if not sentence:
        return {"verdict": "invalid_input", "sentence": sentence,
                "violations": [{"type": "invalid_sentence", "detail": "empty 'sentence'"}]}
    blocks = item.get("blocks")
    if not blocks and item.get("toks"):
        try:
            blocks = _blocks_from_toks(sentence, item["toks"])
        except Exception as exc:  # noqa: BLE001
            return {"verdict": "invalid_input", "sentence": sentence,
                    "violations": [{"type": "invalid_sentence", "detail": str(exc)}]}
    if not blocks:
        return {"verdict": "invalid_input", "sentence": sentence,
                "violations": [{"type": "invalid_sentence",
                                "detail": "нужны 'blocks' (текст) или 'toks' (Word-ID)"}]}
    rep = get_rule().check(sentence, list(blocks), cfg, pipeline=get_pipeline())
    return {
        "sentence": sentence,
        "verdict": rep["verdict"],
        "violations": [{"type": e["code"], "detail": e["message"],
                        "at": e.get("at"), "suggestion": e.get("suggestion")}
                       for e in rep.get("errors", [])],
        "warnings": [{"type": w["code"], "detail": w["message"], "at": w.get("at")}
                     for w in rep.get("warnings", [])],
        "penalties": [{"type": i["code"], "detail": i["message"], "at": i.get("at")}
                      for i in rep.get("info", [])],
        "cost": rep.get("cost"),
        "blocks": len(blocks),
        "lens": rep.get("lens"),
        "rule_version": cfg.get("_version"),
        "config_hash": _canonical_hash(cfg),
    }


def _check_segmentation_impl(items, with_opinion: bool = False) -> dict:
    """Судья правила V4: проверяет СООТВЕТСТВИЕ разбивки человека правилу.

    items - одно или список: {"sentence": "...", "blocks": ["блок1", "блок2"]}
    (текст блоков) ИЛИ {"sentence": "...", "toks": [[1,3],[4,9]]} (Word-ID).
    verdict: compliant | non_compliant | invalid_input.
    violations - ошибки (правило нарушено), warnings - допустимо, но помечено,
    penalties - мягкие штрафы с весом (нарезчик их избегает).
    Пример: check_segmentation({"sentence":"Ich weiß es, weil er müde ist.",
    "blocks":["Ich weiß es,","weil er müde ist."]})"""
    get_rule()
    if isinstance(items, str):
        st = items.strip()
        if st.startswith("{") or st.startswith("["):
            items = json.loads(st)  # JSON-строка пакета/объекта - принимаем как данные
    lst = [items] if isinstance(items, (dict, str)) else list(items)
    lst = [i if isinstance(i, dict) else {"sentence": i} for i in lst]
    results = [_check_one(i, with_opinion) for i in lst]
    cfg = rule_config()
    return {
        "count": len(results),
        "all_compliant": all(r["verdict"] == "compliant" for r in results),
        "rule_version": cfg.get("_version"),
        "config_hash": _canonical_hash(cfg),
        "results": results,
    }


def check_segmentation(items, with_opinion: bool = False) -> dict:
    return _run_tool("check_segmentation", lambda: _check_segmentation_impl(items, with_opinion))


def _rule_self_test_impl() -> dict:
    """Регресс: разметка bench/sets/corpus52_v3.jsonl должна проходить валидатор
    целиком (гейт G4). Медленно (~30 с): парсит 52 предложения.

    Пример: rule_self_test() -> {"total":52,"compliant":52,"gate_passed":true}"""
    cfg = rule_config()
    path = _regression_set()
    if not os.path.exists(path):
        return {"error": f"нет набора: {path}", "gate_passed": False}
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    failed, codes = [], {}
    for r in rows:
        if not r.get("blocks"):
            continue
        rep = get_rule().check(r["sentence"], r["blocks"], cfg, pipeline=get_pipeline())
        if rep["verdict"] != "compliant":
            failed.append(r["id"])
            for e in rep["errors"]:
                codes[e["code"]] = codes.get(e["code"], 0) + 1
    total = len([r for r in rows if r.get("blocks")])
    return {
        "total": total,
        "compliant": total - len(failed),
        "non_compliant": len(failed),
        "gate_passed": total > 0 and not failed,
        "failed_ids": failed,
        "error_codes": codes,
        "regression_set": path,
        "rule_version": cfg.get("_version"),
        "config_hash": _canonical_hash(cfg),
    }


def rule_self_test() -> dict:
    return _run_tool("rule_self_test", lambda: _rule_self_test_impl())


def _rule_info_impl() -> dict:
    """Паспорт правила: версия, hash конфига, параметры нарезки, запреты, штрафы,
    измеренные цифры, путь регресс-набора.

    Пример: rule_info()"""
    cfg = rule_config()
    measured, seg_version = {}, None
    try:
        raw = json.load(open(_config_path(), encoding="utf-8"))
        measured = raw.get("segment", {}).get("measured", {})
        seg_version = raw.get("segment_version")
    except Exception:  # noqa: BLE001
        pass
    return {
        "rule_root": _rule_root(),
        "registered": True,
        "rule_version": cfg.get("_version"),
        "segment_version": seg_version,
        "config_hash": _canonical_hash(cfg),
        "algorithm": cfg.get("algorithm"),
        "params": {k: cfg.get(k) for k in
                   ("min_lex", "ideal_lex", "cap_lex", "warn_above_lex", "w_len", "objective")},
        "bans": cfg.get("bans"),
        "one_word": cfg.get("one_word"),
        "penalties": cfg.get("penalties"),
        "syllables": cfg.get("syllables"),
        "measured": measured,
        "regression_set": _regression_set(),
    }


def rule_info() -> dict:
    return _run_tool("rule_info", lambda: _rule_info_impl())


def main() -> None:
    rule_status = "rule not connected"
    if _RULE is not None and os.path.exists(os.path.join(_rule_root(), "reference", "config.json")):
        try:
            cfg = rule_config()
            rule_status = "rule v%s, config_hash=%s" % (cfg.get("_version"), _canonical_hash(cfg))
        except Exception:  # noqa: BLE001
            rule_status = "rule error"
    _log(
        "START server_version=%s stanza=%s python=%s torch=n/a rule=%s log=%s" % (
            _get_server_version(),
            getattr(stanza, "__version__", "n/a"),
            sys.version.split()[0],
            rule_status,
            _SERVER_LOG_FILE,
        )
    )
    mcp.run()  # stdio transport


# Правило подключаем до регистрации инструментов: нет правила — судьи нет,
# сервер живёт как раньше.
_load_rule()
if _RULE is not None:
    mcp.tool(name="check_segmentation",
             description="Судья: verdict compliant/non_compliant/invalid_input + подсказки (см. docstring)")(check_segmentation)
    mcp.tool(name="rule_self_test",
             description="Регресс: разметка 52 проходит валидатор целиком (52/52)")(rule_self_test)
    mcp.tool(name="rule_info",
             description="Версия правила, config_hash, параметры нарезки, запреты, штрафы, цифры")(rule_info)


if __name__ == "__main__":
    main()
