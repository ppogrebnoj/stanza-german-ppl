# -*- coding: utf-8 -*-
"""pack_models.py — упаковать кэш моделей Stanza в переносимый архив.

Зачем: 1.59 ГБ моделей `de` живут вне git (каталог Stanza в %LOCALAPPDATA%),
поэтому при переносе машины их надо доставить отдельно. Скрипт делает из них
один zip + контрольную сумму, который кладётся в GitHub Release как ассет.

Что попадает в архив (по умолчанию):
    de/**            — все процессоры, кроме de/default.zip
    resources.json   — реестр моделей Stanza

Почему без default.zip: это исходный архив загрузки (809 МБ), его содержимое
целиком дублирует распакованные каталоги de/. Проверено: пайплайн
(tokenize,pos,lemma,depparse) и валидатор 52/52 работают без него.

Запуск:
    python scripts/pack_models.py --minimal        # 315 МБ: только то, что нужно коду (рекомендуется)
    python scripts/pack_models.py                  # 853 МБ: все процессоры, кроме default.zip
    python scripts/pack_models.py --keep-zip       # 1.6 ГБ: полный кэш как есть
    python scripts/pack_models.py --out D:\\assets  # другой каталог для архива

Что именно отсекает --minimal (проверено на 52/52 и на инструментах сервера):
  * оставляет tokenize, mwt, pos, lemma, depparse, forward_charlm, backward_charlm;
  * из pretrain берёт только conll17.pt (нужен depparse); fasttextwiki.pt — 293 МБ —
    коду не нужен;
  * не берёт constituency, ner, sentiment — их в коде нет с версии 4.0.0.

После упаковки скрипт печатает готовую команду загрузки в GitHub Releases.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths as P  # noqa: E402

# Процессоры, которые реально использует код (server.py + правило/validator.py).
# pretrain нужен depparse напрямую — но только conll17.pt (fasttextwiki.pt не нужен),
# charlm — tokenize/depparse. constituency/ner/sentiment коду не нужны.
MINIMAL = ["tokenize", "mwt", "pos", "lemma", "depparse",
           "forward_charlm", "backward_charlm", "pretrain"]
LEAN_PRETRAIN = {"conll17.pt"}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect(models: Path, cache: Path, keep_zip: bool, minimal: bool) -> list[tuple[Path, str]]:
    """Список (путь на диске, путь внутри архива)."""
    items: list[tuple[Path, str]] = []
    if not models.exists():
        raise SystemExit(f"ОШИБКА: нет каталога моделей {models}")
    for entry in sorted(models.iterdir()):
        if entry.is_dir():
            if minimal and entry.name not in MINIMAL:
                continue
            for f in sorted(entry.rglob("*")):
                if not f.is_file():
                    continue
                if minimal and entry.name == "pretrain" and f.name not in LEAN_PRETRAIN:
                    continue
                items.append((f, f"de/{f.relative_to(models).as_posix()}"))
        elif entry.is_file():
            if entry.name == "default.zip" and not keep_zip:
                continue
            items.append((entry, f"de/{entry.name}"))
    reg = cache / "resources.json"
    if reg.exists():
        items.append((reg, "resources.json"))
    else:
        print(f"ВНИМАНИЕ: нет {reg} — Stanza может считать, что модели не установлены")
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description="Упаковать кэш моделей Stanza в zip для переноса")
    ap.add_argument("--out", default=str(P.ROOT), help="каталог для архива (по умолчанию корень проекта)")
    ap.add_argument("--minimal", action="store_true", help="только процессоры, нужные коду (~610 МБ)")
    ap.add_argument("--keep-zip", action="store_true", help="включить de/default.zip (полный кэш)")
    ap.add_argument("--name", default=f"stanza-models-{P.LANG}-{P.STANZA_VERSION}.zip")
    a = ap.parse_args()

    cache = P.stanza_cache_dir()
    models = P.model_dir()
    print(f"кэш Stanza : {cache}")
    print(f"модели {P.LANG}  : {models}")

    items = collect(models, cache, a.keep_zip, a.minimal)
    if not items:
        raise SystemExit("ОШИБКА: нечего упаковывать")

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / a.name
    if out.exists():
        print(f"перезаписываю существующий архив {out.name}")

    total = sum(src.stat().st_size for src, _ in items)
    print(f"файлов {len(items)}, суммарно {total / 2**30:.2f} ГБ -> {out.name}")

    done = 0
    with zipfile.ZipFile(out, "w", allowZip64=True) as zf:
        for i, (src, arc) in enumerate(items, 1):
            # уже сжатые модели не жмём повторно: быстрее и без выигрыша
            stored = src.suffix.lower() in {".zip", ".xz", ".gz", ".pt", ".bin", ".7z"}
            zf.write(src, arc, compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED,
                     compresslevel=None if stored else 1)
            done += src.stat().st_size
            if i % 25 == 0 or i == len(items):
                print(f"\r  упаковано {i}/{len(items)} ({done / 2**30:.2f}/{total / 2**30:.2f} ГБ)",
                      end="", flush=True)
    print()

    # проверка архива: всё ли читается и совпадает по числу файлов
    with zipfile.ZipFile(out) as zf:
        bad = zf.testzip()
        n = len(zf.namelist())
    if bad:
        raise SystemExit(f"ОШИБКА: битый файл в архиве: {bad}")
    if n != len(items):
        raise SystemExit(f"ОШИБКА: в архиве {n} записей вместо {len(items)}")

    digest = sha256_of(out)
    sum_path = out.with_suffix(out.suffix + ".sha256")
    sum_path.write_text(f"{digest}  {out.name}\n", encoding="utf-8", newline="\n")

    print(f"архив   : {out} ({out.stat().st_size / 2**30:.2f} ГБ)")
    print(f"sha256  : {digest}")
    print(f"сумма   : {sum_path.name}")
    print("\nЗагрузка в GitHub Releases (репозиторий проекта):")
    print(f'  gh release create models-v1 "{out}" "{sum_path}" '
          f'-t "Stanza {P.LANG} models {P.STANZA_VERSION}" '
          f'-n "Кэш моделей Stanza {P.STANZA_VERSION} для {P.LANG} (без default.zip)"')
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
