# -*- coding: utf-8 -*-
"""Тесты report-only режима pins.py и hash-gating отчёта в issue.

Запуск: python -m unittest discover -s scripts/tests -p 'test_pins*.py'
Сеть не используется: fetch_release подменяется фикстурой.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent / "installer" / "install_tools"))
import pins  # noqa: E402
import deps_watch_issue as D  # noqa: E402

LATEST = {"PyYAML": "6.0.5", "platformdirs": "4.15.0"}


def fake_fetch(pkg, ver=None, cache=None):
    """Все пакеты — с колёсами py3-none-any; два пакета имеют новую версию."""
    current = pins.P.parse_pins(pins.P.LOCK).get(pkg, "1.0.0")
    version = ver or LATEST.get(pkg, current)
    return {"version": version, "files": [f"{pkg}-{version}-py3-none-any.whl"]}


def offline_fetch(pkg, ver=None, cache=None):
    return {"error": "PyPI недоступен (тест)"}


class TestLockParsing(unittest.TestCase):
    def test_lock_has_62_positions(self):
        lock = pins.P.parse_pins(pins.P.LOCK)
        self.assertEqual(len(lock), 62)
        self.assertEqual(lock["PyYAML"], "6.0.4")
        self.assertIn("platformdirs", lock)

    def test_direct_pins(self):
        direct = pins.P.parse_pins()
        self.assertEqual(direct["stanza"], "1.15.0")
        self.assertEqual(direct["torch"], "2.15.0")


class TestReport(unittest.TestCase):
    def test_report_covers_all_lock_positions(self):
        with mock.patch.object(pins, "fetch_release", side_effect=fake_fetch):
            report = pins.build_report({})
        self.assertEqual(len(report["packages"]), 62)
        self.assertTrue(report["pypi_available"])
        self.assertEqual(report["wheel_contract"]["status"], "ok")
        self.assertEqual(report["wheel_contract"]["python"], "3.15")
        rows = {r["package"]: r for r in report["packages"]}
        self.assertEqual(rows["PyYAML"]["latest"], "6.0.5")
        self.assertEqual(rows["PyYAML"]["status"], "есть новее")
        self.assertEqual(rows["platformdirs"]["latest"], "4.15.0")
        self.assertEqual(rows["stanza"]["status"], "актуально")

    def test_markdown_and_json_formats(self):
        with mock.patch.object(pins, "fetch_release", side_effect=fake_fetch):
            report = pins.build_report({}, "https://github.com/o/r/actions/runs/1")
        md = pins.report_markdown(report)
        self.assertIn("| PyYAML | 6.0.4 | 6.0.5 | yes | есть новее |", md)
        self.assertIn("| platformdirs |", md)
        self.assertIn("actions/runs/1", md)
        rows = [ln for ln in md.splitlines() if ln.startswith("| ")]
        self.assertEqual(len(rows) - 1, 62)  # минус заголовок таблицы
        blob = json.dumps(report, ensure_ascii=False)
        self.assertIn('"fingerprint"', blob)
        self.assertIn('"as_of"', blob)

    def test_offline_is_not_a_failure(self):
        with mock.patch.object(pins, "fetch_release", side_effect=offline_fetch), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            report = pins.build_report({})
            rc = pins.main(["--report", "--json"])
        self.assertFalse(report["pypi_available"])
        self.assertEqual(report["wheel_contract"]["status"], "unknown")
        self.assertTrue(all(r["status"] == "нет данных" for r in report["packages"]))
        self.assertEqual(rc, 0)

    def test_report_mode_never_writes_repository(self):
        with tempfile.TemporaryDirectory() as td:
            md, js = Path(td) / "a.md", Path(td) / "a.json"
            with mock.patch.object(pins, "fetch_release", side_effect=fake_fetch), \
                 mock.patch.object(pins, "_save_cache", side_effect=AssertionError("cache write")), \
                 mock.patch.object(pins, "write_snapshot", side_effect=AssertionError("snapshot write")):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    rc = pins.main(["--report", "--out-md", str(md), "--out-json", str(js)])
            self.assertEqual(rc, 0)
            self.assertTrue(md.exists() and js.exists())
            self.assertEqual(len(json.loads(js.read_text(encoding="utf-8"))["packages"]), 62)


class TestWheelTags(unittest.TestCase):
    def test_stable_abi_and_free_threaded(self):
        files = [
            "hf_xet-1.8.0-cp38-abi3-win_amd64.whl",
            "cryptography-50.0.2-cp315-abi3.abi3t-win_amd64.whl",
            "torch-2.15.0-cp314-cp314t-win_amd64.whl",
        ]
        info = pins.wheel_info(files)
        self.assertEqual(pins.supports(info, "3.15"), "yes")
        self.assertEqual(info["wheels"][0], ("cp38", "abi3", "win_amd64"))


class TestHashGating(unittest.TestCase):
    def test_fingerprint_ignores_as_of_and_run(self):
        with mock.patch.object(pins, "fetch_release", side_effect=fake_fetch):
            a = pins.build_report({}, "run-1")
            b = pins.build_report({}, "run-2")
        self.assertEqual(a["fingerprint"], b["fingerprint"])

    def test_fingerprint_changes_with_latest(self):
        with mock.patch.object(pins, "fetch_release", side_effect=fake_fetch):
            a = pins.build_report({})
        with mock.patch.object(pins, "fetch_release", side_effect=lambda p, v=None, c=None: {
            "version": "9.9.9" if v is None and p == "PyYAML" else (v or "1.0.0"),
            "files": [f"{p}-1.0.0-py3-none-any.whl"],
        }):
            b = pins.build_report({})
        self.assertNotEqual(a["fingerprint"], b["fingerprint"])

    def test_issue_markers_and_gating(self):
        body = "Заголовок\n\n" + D.START + "\nстарый отчёт\n" + D.END + \
               "\n<!-- deps-fingerprint:abc123 -->\n\nПодвал\n"
        self.assertFalse(D.fingerprint_changed(body, "abc123"))
        self.assertTrue(D.fingerprint_changed(body, "def456"))
        new = D.replace_report(body, "новый отчёт", "def456")
        self.assertIn(D.START, new)
        self.assertIn("новый отчёт", new)
        self.assertIn("<!-- deps-fingerprint:def456 -->", new)
        self.assertIn("Заголовок", new)
        self.assertIn("Подвал", new)
        self.assertNotIn("старый отчёт", new)
        self.assertFalse(D.fingerprint_changed(new, "def456"))
        fresh = D.replace_report("", "отчёт", "aaa111")
        self.assertTrue(fresh.startswith(D.START))


if __name__ == "__main__":
    unittest.main()
