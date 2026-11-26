#!/usr/bin/env python3
"""Stanza German MCP server (stdio).

Локальный MCP-сервер для синтаксического анализа немецкого языка на базе
Stanford Stanza 1.15.0 (CPU). Работает полностью офлайн: модели берутся из
контрактного каталога проекта <root>\\.stanza\\models
(переопределяется STANZA_RESOURCES_DIR), download_method=None — сеть не используется
и повторная загрузка не требуется.

Запуск:  python server.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
import threading
import time
import datetime
import functools
from pathlib import Path

import anyio

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

# version.json — единственный источник текущей версии сервера.
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
        # Клиент всегда видит состояние правила и фактический RULE_ROOT — даже когда правило
        # не подключено (иначе «сервер отвечает, но судьи нет» выглядит как поломка сервера).
        st = _rule_status_text()
        res["rule_status"] = st
        extra = " rule_status=%s" % st
        v = res.get("verdict")
        if v is not None:
            extra = " verdict=%s" % v
        elif res.get("gate_passed") is not None:
            extra = " gate=%s" % str(res["gate_passed"])
    _log("TOOL %s ok %.1f ms%s" % (name, ms, extra))
    return res

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# ВАЖНО (замер 20.11): синхронный инструмент FastMCP вызывает
# `fn(**args)` ПРЯМО ВНУТРИ asyncio-петли (func_metadata.py: `return fn(...)`), без
# переноса в поток. Долгая синхронная работа блокирует event loop stdio-транспорта:
# сервер не читает stdin и не пишет ответ → клиент получает таймаут, хотя в server.log
# всё «висит на TOOL ... start».
#
# Замер на локальном диске (D:\KI_WORK): pipeline_info 27–40 с, rule_self_test 105–130 с.
# Клиент pi ждёт initialize 8 с, а на вызов инструмента — секунды. Поэтому каждый
# инструмент — async-обёртка над `anyio.to_thread.run_sync`: пока поток считает, петля
# свободна и stdio продолжает работать.
def _async_tool(name: str, description: str):
    """Регистрирует синхронный `fn` как async-инструмент (работа в отдельном потоке)."""
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(**kwargs):
            return await anyio.to_thread.run_sync(functools.partial(fn, **kwargs))
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return mcp.tool(name=name, description=description)(wrapper)
    return deco

LANGUAGE = "de"
PROCESSORS = "tokenize,mwt,pos,lemma,depparse"   # правило работает на зависимостях

# Сколько символов в секунду при чтении вслух — для оценки пауз (не обязательный параметр)
DEFAULT_CHARS_PER_SEC = 4.0

# Правило сегментации (validator.py + config.json) живёт отдельно от сервера.
# Путь — переменная окружения RULE_ROOT (поле env в mcp.json), иначе — дефолт:
# папка «правило» рядом с этим файлом (MCP-stanza-german/../rule). Так сервер
# работает после переноса проекта в любой каталог, без правки кода.
RULE_ROOT_DEFAULT = str(Path(__file__).resolve().parent.parent / "rule")

mcp = FastMCP(
    "stanza-german",
    instructions=(
        "Stanza de: segment_german — нарезать текст на блоки по правилу V4 (with_check=true — "
        "ещё и проверить результат); check_segmentation — проверить готовую разбивку "
        "(вердикт + коды нарушений + штрафы); parse_german — синтаксис (леммы/POS/зависимости + MWT); "
        "rule_info / rule_self_test — паспорт и регресс правила; pipeline_info — статус. Офлайн."
    ),
)

# ВАЖНО (замер 20.11): `import stanza` на верхнем уровне стоит 63 с на сетевой/VMware-шаре
# (сам пакет читается с Z:\...\.venv), а MCP-клиент ждёт ответа на initialize 8 с
# (pi-web-ui: mcp-bridge.js, start(timeoutMs = 8000) — не настраивается из mcp.json).
# Handshake обязан отвечать быстро, поэтому stanza импортируется лениво — при первой
# загрузке пайплайна, а не при старте сервера.
def _stanza():
    """Модуль stanza (ленивый импорт). Аннотации ниже — строковые, чтобы не тянуть импорт."""
    import stanza
    return stanza


_pipeline: "stanza.Pipeline | None" = None
_pipeline_lock = threading.Lock()
_load_notes: list[str] = []


def _load_pipeline() -> "stanza.Pipeline":
    """Пайплайн из локального кэша (без сети): tokenize, MWT, POS, леммы, зависимости.

    Constituency не грузим: правило V4 считает оценку границы по дереву зависимостей,
    а модель составляющих добавляла ~1.7 с к старту и память."""
    try:
        stanza = _stanza()
        return stanza.Pipeline(
            lang=LANGUAGE,  # в Stanza 1.15 параметр называется lang
            processors=PROCESSORS,
            download_method=None,  # офлайн: только локальный кэш, без сети
            verbose=False,
        )
    except Exception as exc:  # noqa: BLE001
        _load_notes.append(f"Не удалось загрузить '{PROCESSORS}': {exc}")
        raise RuntimeError("Stanza pipeline не удалось загрузить: " + "; ".join(_load_notes))


def get_pipeline() -> "stanza.Pipeline":
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


@_async_tool("parse_german",
               "Синтаксис немецкого текста: предложения, токены, леммы, POS, зависимости (MWT)")
def parse_german(text: str | list[str]) -> dict:
    return _run_tool("parse_german", lambda: _parse_german_impl(text))

def _updates_info() -> dict:
    """Обновления зависимостей — по снимку, без сети и без оценок.

    bench/results/deps.json пишет `python installer/install_tools/pins.py --latest --write` (CI раз в неделю).
    Файла нет или он битый -> {"available": false}: сервер не падает и ничего не выдумывает.
    """
    try:
        path = Path(_BASE_DIR).parent / "bench" / "results" / "deps.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        as_of = str(data.get("as_of") or "")
        stale = None
        try:
            when = datetime.datetime.strptime(as_of, "%Y-%m-%dT%H:%M:%SZ")
            now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            stale = max(0, (now - when).days)
        except ValueError:
            pass
        outdated = [{"name": n, "current": (v or {}).get("current"), "latest": (v or {}).get("latest")}
                    for n, v in (data.get("packages") or {}).items()
                    if (v or {}).get("latest") and v.get("latest") != v.get("current")]
        m = data.get("models") or {}
        return {"available": True, "as_of": as_of, "stale_days": stale, "python": data.get("python"),
                "outdated": sorted(outdated, key=lambda x: x["name"]),
                "models_stanza": m.get("stanza"), "models_ok": m.get("pack_ok")}
    except Exception:  # noqa: BLE001
        return {"available": False}


def _pipeline_info_impl() -> dict:
    """Статус сервера: загруженные процессоры, версии, путь к кэшу, offline-статус."""
    import torch

    pipe = get_pipeline()
    return {
        "server": "stanza-german",
        "server_version": _get_server_version(),
        "log_file": _SERVER_LOG_FILE,
        "language": LANGUAGE,
        "processors_loaded": sorted(pipe.processors.keys()),
        "download_method": None,
        "offline": True,
        "model_dir": str(pipe.dir),
        "versions": {
            "python": sys.version.split()[0],
            "stanza": _stanza().__version__,
            "torch": torch.__version__,
        },
        "rule_root": _rule_root(),
        "rule_registered": _RULE is not None,
        "updates": _updates_info(),
        "notes": list(_load_notes) + ([_RULE_NOTE] if _RULE_NOTE else []),
    }


# ======================= правило сегментации (судья) =========================
# Единственный код правила - validator.py + config.json (раздел
# "segment"). Сервер - тонкая read-only обёртка: судья (check), регресс
# (self_test), паспорт правила (rule_info). config.json перечитывается на
# КАЖДЫЙ вызов: поправили конфиг - сразу действует, рестарт не нужен.
_RULE = None
_RULE_NOTE: str | None = None


@_async_tool("pipeline_info",
               "Статус сервера: процессоры, версии, путь кэша, offline, правило, обновления")
def pipeline_info() -> dict:
    return _run_tool("pipeline_info", lambda: _pipeline_info_impl())


def _rule_root() -> str:
    """Папка правила: env RULE_ROOT, иначе папка по умолчанию."""
    return os.environ.get("RULE_ROOT", RULE_ROOT_DEFAULT)


def _rule_status_text() -> str:
    """Тот же статус, что пишется в журнал на старте; всегда с фактическим путём."""
    root = _rule_root()
    if _RULE is not None and os.path.exists(_config_path()):
        try:
            cfg = rule_config()
            return "rule %s, config_hash=%s; RULE_ROOT=%s" % (
                cfg.get("_version"), _canonical_hash(cfg), root)
        except Exception as exc:  # noqa: BLE001
            return "rule error: %s; RULE_ROOT=%s" % (exc, root)
    reason = _RULE_NOTE or "validator.py не подключён"
    return "rule not connected: %s; RULE_ROOT=%s" % (reason, root)


def _config_path() -> str:
    return os.path.join(_rule_root(), "config.json")


def _regression_set() -> str:
    return os.environ.get(
        "RULE_SET",
        os.path.join(os.path.dirname(_rule_root()), "bench", "sets", "corpus52.jsonl"))


def _load_rule() -> None:
    """Импорт validator.py из RULE_ROOT. Нет правила - сервер работает как раньше,
    инструменты судьи просто не регистрируются (не падает)."""
    global _RULE, _RULE_NOTE
    root = _rule_root()
    path = os.path.join(root, "validator.py")
    if not os.path.exists(path):          # старое имя (reference/validator_v3.py)
        path = os.path.join(root, "reference", "validator_v3.py")
    if not os.path.exists(path):
        _RULE_NOTE = (
            f"правило не подключено: в {root} нет validator.py "
            f"(искали также reference/validator_v3.py); проверьте RULE_ROOT")
        _log("RULE_STATUS: %s; RULE_ROOT=%s" % (_RULE_NOTE, root))
        return
    try:
        ref_dir = os.path.dirname(path)
        if ref_dir not in sys.path:
            sys.path.insert(0, ref_dir)   # segment.py импортирует validator.py рядом
        spec = importlib.util.spec_from_file_location("rule_validator", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["rule_validator"] = mod
        sys.modules.setdefault("validator", mod)   # segment.py делает import validator
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _RULE = mod
    except Exception as exc:  # noqa: BLE001
        _RULE_NOTE = f"правило не подключено: {exc}"
        _log("RULE_STATUS: %s; RULE_ROOT=%s" % (_RULE_NOTE, root))


def get_rule():
    if _RULE is None:
        raise RuntimeError(_RULE_NOTE or "validator.py не подключен")
    return _RULE


_SEG = None
_SEG_NOTE: str | None = None


def _load_segmenter() -> None:
    """Импорт segment.py из RULE_ROOT (нарезчик). Отдельно от судьи: сервер работает,
    даже если нарезчика нет."""
    global _SEG, _SEG_NOTE
    path = os.path.join(_rule_root(), "segment.py")
    if not os.path.exists(path):
        _SEG_NOTE = f"нарезчик не подключён: нет {path}"
        return
    try:
        ref_dir = os.path.dirname(path)
        if ref_dir not in sys.path:
            sys.path.insert(0, ref_dir)
        spec = importlib.util.spec_from_file_location("rule_segment", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["rule_segment"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        _SEG = mod
    except Exception as exc:  # noqa: BLE001
        _SEG_NOTE = f"нарезчик не подключён: {exc}"


def get_segmenter():
    if _SEG is None:
        raise RuntimeError(_SEG_NOTE or "segment.py не подключен")
    return _SEG


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


def _check_one(item: dict) -> dict:
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


def _check_segmentation_impl(items) -> dict:
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
    results = [_check_one(i) for i in lst]
    cfg = rule_config()
    return {
        "count": len(results),
        "all_compliant": all(r["verdict"] == "compliant" for r in results),
        "rule_version": cfg.get("_version"),
        "config_hash": _canonical_hash(cfg),
        "results": results,
    }


def check_segmentation(items) -> dict:
    return _run_tool("check_segmentation", lambda: _check_segmentation_impl(items))


def _segment_german_impl(text, with_check: bool = False) -> dict:
    """Нарезка текста на блоки по правилу V4.

    text — строка или список строк (абзац/страница: делится на предложения сам).
    with_check=true — дополнительно прогнать валидатор по своей же нарезке
    (показывает цену штрафов и предупреждения).
    Перед разбором текст чистится от технического мусора (NBSP, мягкие переносы,
    лигатуры, прямые кавычки) — список правок в поле "normalized". Слова и пунктуация
    исходника сохраняются.
    Пример: segment_german("Ich habe bei der Firma gearbeitet.")"""
    seg, val = get_segmenter(), get_rule()
    cfg = rule_config()
    pipe = get_pipeline()
    out, all_fixes = [], []
    for k, t in enumerate(_texts_arg(text)):
        sentences, fixes = seg.segments_of_text(t, cfg, pipe)
        for f in fixes:
            if f not in all_fixes:
                all_fixes.append(f)
        for x in sentences:
            row = {
                "id": len(out) + 1,
                "item": k + 1,
                "text": x["text"],
                "blocks": x["blocks"],
                "block_count": len(x["blocks"]),
                "lens": x["lens"],
            }
            if with_check:
                rep = val.check(x["text"], x["blocks"], cfg, pipeline=pipe)
                row["verdict"] = rep["verdict"]
                row["cost"] = rep["cost"]
                if rep["errors"]:
                    row["errors"] = [{"type": e["code"], "detail": e["message"]}
                                     for e in rep["errors"]]
                if rep["info"]:
                    row["penalties"] = [i["code"] for i in rep["info"]]
            out.append(row)
    return {
        "language": LANGUAGE,
        "count": len(out),
        "blocks_total": sum(r["block_count"] for r in out),
        "rule_version": cfg.get("_version"),
        "config_hash": _canonical_hash(cfg),
        "normalized": all_fixes,
        "sentences": out,
    }


def segment_german(text, with_check: bool = False) -> dict:
    return _run_tool("segment_german", lambda: _segment_german_impl(text, with_check))


def _rule_self_test_impl() -> dict:
    """Регресс: разметка bench/sets/corpus52.jsonl должна проходить валидатор
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
        "segmenter_ready": _SEG is not None,
    }


def rule_info() -> dict:
    return _run_tool("rule_info", lambda: _rule_info_impl())


def _torch_version() -> str:
    """Версия torch для строки START: без импорта torch (он тянет ~200 МБ и секунды старта).
    importlib.metadata читает метаданные колеса; настоящий torch.__version__ виден в pipeline_info."""
    try:
        from importlib.metadata import version
        return version("torch")
    except Exception:  # noqa: BLE001
        return "n/a"


def _stanza_version() -> str:
    """Версия stanza для строки START — без импорта stanza (на сетевом диске это ~63 с,
    а initialize клиента ждёт секунды). importlib.metadata читает метаданные колеса."""
    try:
        from importlib.metadata import version
        return version("stanza")
    except Exception:  # noqa: BLE001
        return "n/a"


def _warmup() -> None:
    """Импорт тяжёлых зависимостей ДО старта event loop.

    ЗАМЕР 20.11 (воспроизведено на мини-сервере в 40 строк): `import torch` внутри уже
    работающего MCP-сервера (event loop поднят, stdio-пайпы открыты) ВИСНЕТ НАВСЕГДА —
    ни в главном потоке, ни в anyio.to_thread. Причина: torch при первом импорте поднимает
    пул потоков (OpenMP/intra-op) и конфликтует с asyncio-петлёй и stdio-обёртками anyio
    на Windows. Признак в логе — «TOOL pipeline_info start» без «ok».

    Тот же тест, но с импортом до mcp.run(): 0.1 с на вызов, пайплайн 24.5 с — всё отвечает.
    Поэтому нагружаем torch и stanza синхронно на старте (вне петли) и только потом отдаём
    управление stdio-транспорту.
    """
    t0 = time.perf_counter()
    try:
        _stanza()
    except Exception as exc:  # noqa: BLE001
        _log("WARN: import stanza failed at warmup: %s" % exc)
    try:
        import torch  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        _log("WARN: import torch failed at warmup: %s" % exc)
    _log("WARMUP done %.1f ms (torch+stanza импортированы до старта event loop)"
         % ((time.perf_counter() - t0) * 1000))


def main() -> None:
    rule_status = _rule_status_text()
    if rule_status.startswith(("rule not connected", "rule error")):
        _log("RULE_STATUS: причина: %s; фактический RULE_ROOT=%s" % (rule_status, _rule_root()))
    # stanza импортируется лениво (см. _stanza): на старте сервера его ещё нет, а в баннере
    # нужна только версия — берём её из importlib.metadata, без импорта 63-секундного пакета
    _log(
        "START server_version=%s stanza=%s python=%s torch=%s rule=%s log=%s" % (
            _get_server_version(),
            _stanza_version(),
            sys.version.split()[0],
            _torch_version(),
            rule_status,
            _SERVER_LOG_FILE,
        )
    )
    # ВАЖНО: до mcp.run() — иначе первый же import torch внутри инструмента вешает сервер
    _warmup()
    mcp.run()  # stdio transport


# Правило подключаем до регистрации инструментов: нет правила — судьи нет,
# сервер живёт как раньше.
_load_rule()
_load_segmenter()
if _RULE is not None:
    if _SEG is not None:
        _async_tool("segment_german",
                    "Нарезать немецкий текст на блоки по правилу V4 (текст или список текстов)")(segment_german)
    _async_tool("check_segmentation",
                "Судья: verdict compliant/non_compliant/invalid_input + подсказки (см. docstring)")(check_segmentation)
    _async_tool("rule_self_test",
                "Регресс: разметка 52 проходит валидатор целиком (52/52)")(rule_self_test)
    _async_tool("rule_info",
                "Версия правила, config_hash, параметры нарезки, запреты, штрафы, цифры")(rule_info)


if __name__ == "__main__":
    main()
