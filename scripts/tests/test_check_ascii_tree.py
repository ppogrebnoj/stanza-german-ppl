# -*- coding: utf-8 -*-
"""Тесты контракта ASCII-структуры: только.stdlib, без сети."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import check_ascii_tree as C  # noqa: E402

FIXTURE_REL = "scripts/tests/fixtures/check_ascii_tree/legacy_tokens.md"


class ScanPathsTest(unittest.TestCase):
    def test_non_ascii_component_is_violation(self):
        found = C.scan_paths(["rule/ok.py", "правило/segment.py", "data/ok.md"])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["kind"], "non_ascii_path")
        self.assertEqual(found[0]["path"], "правило/segment.py")

    def test_ignored_and_generated_paths_are_skipped(self):
        paths = [
            ".venv/Scripts/python.exe", ".tmp/install.log", ".stanza/models/x",
            "bench/results/audit.json", "__pycache__/x.pyc", "x.pyc",
            ".mypy_cache/x", ".ruff_cache/x", ".pytest_cache/x",
        ]
        self.assertEqual(C.scan_paths(paths), [])

    def test_non_ascii_inside_excluded_dirs_is_skipped(self):
        paths = [
            ".venv/Либ/модуль.py", ".tmp/отчёт.txt", ".stanza/модели/x",
            ".mypy_cache/кэш/x.json", ".ruff_cache/кэш/x.json",
            ".pytest_cache/кэш/x", "bench/results/отчёт.md",
        ]
        self.assertEqual(C.scan_paths(paths), [])

    def test_leading_dot_paths_are_preserved(self):
        self.assertEqual(C.normalize_rel("./.gitattributes"), ".gitattributes")
        self.assertEqual(C.normalize_rel(".github/workflows/contract.yml"),
                         ".github/workflows/contract.yml")
        self.assertEqual(C.normalize_rel(".venv/x"), ".venv/x")

    def test_ascii_paths_ok(self):
        self.assertEqual(C.scan_paths(["rule/segment.py", "data/MARKUP_51.md", "docs/flags.json"]), [])


class ScanContentTest(unittest.TestCase):
    def test_old_path_token_is_violation(self):
        violations, warnings = C.scan_content("docs/a.md", "см. правило/segment.py")
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["kind"], "legacy_path")
        self.assertEqual(violations[0]["line"], 1)
        self.assertEqual(warnings, [])

    def test_old_doc_path_is_violation(self):
        violations, _ = C.scan_content("docs/a.md", "installer/УСТАНОВКА.md")
        self.assertEqual(violations[0]["kind"], "legacy_doc_path")

    def test_venv_cli_flag_and_internal_param_are_violations(self):
        for text in ("`-Venv`", "$Venv", "-Venv -Force"):
            with self.subTest(text=text):
                violations, _ = C.scan_content("installer/INSTALL.md", text)
                self.assertEqual(violations[0]["kind"], "legacy_flag_venv")

    def test_helper_names_with_venv_are_allowed(self):
        violations, _ = C.scan_content("installer/lib/common.ps1", "Test-VenvBusy; Test-CorrectVenv")
        self.assertEqual(violations, [])

    def test_lm_studio_tokens_are_violations(self):
        for text in ("**LM Studio:** Settings", "$env:USERPROFILE\\.lmstudio\\mcp.json"):
            with self.subTest(text=text):
                violations, _ = C.scan_content("x.md", text)
                self.assertEqual(violations[0]["kind"], "lm_studio")

    def test_bare_data_doc_is_only_warning(self):
        violations, warnings = C.scan_content("README.md", "см. MARKUP_51.md")
        self.assertEqual(violations, [])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["kind"], "bare_data_doc")

    def test_prefixed_data_doc_is_clean(self):
        violations, warnings = C.scan_content("README.md", "см. data/MARKUP_51.md")
        self.assertEqual((violations, warnings), ([], []))

    def test_cyrillic_prose_is_allowed(self):
        text = "Это русский текст: правила, данные, кириллица в документах легитимна."
        self.assertEqual(C.scan_content("README.md", text), ([], []))


class ExclusionTest(unittest.TestCase):
    def test_checker_and_its_tests_are_excluded_from_content_scan(self):
        for rel in ("scripts/check_ascii_tree.py", "scripts/tests/test_check_ascii_tree.py",
                    FIXTURE_REL, "CHANGELOG.md", "bench/results/summary.json"):
            with self.subTest(rel=rel):
                self.assertTrue(C.is_content_excluded(rel))

    def test_regular_docs_are_scanned(self):
        for rel in ("README.md", "installer/INSTALL.md", ".github/workflows/contract.yml",
                    "installer/lib/inventory.ps1", "MCP-stanza-german/mcp.json.example"):
            with self.subTest(rel=rel):
                self.assertFalse(C.is_content_excluded(rel))

    def test_fixture_really_contains_legacy_tokens(self):
        raw = (HERE.parent.parent / FIXTURE_REL).read_text(encoding="utf-8")
        violations, warnings = C.scan_content(FIXTURE_REL, raw)
        self.assertTrue(violations)
        self.assertTrue(warnings)


class CanonicalAndReportTest(unittest.TestCase):
    def test_canonical_paths_presence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for item in C.CANONICAL:
                path = root / item
                if item.endswith("/"):
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("x", encoding="utf-8")
            self.assertEqual(C.check_canonical_paths(root), [])
            (root / "data").rmdir()
            missing = C.check_canonical_paths(root)
            self.assertEqual([m["path"] for m in missing], ["data/"])

    def test_missing_root_is_error_with_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            gone = Path(tmp)
        report = C.run_check(gone)
        self.assertEqual(report["verdict"], "ERROR")
        self.assertEqual(report["exit_code"], 2)
        self.assertEqual(report["violations"], [])

    def test_report_shape_and_exit_codes(self):
        report = {"schema": 1, "verdict": "FAIL", "exit_code": 1,
                  "violations": [{"kind": "x", "path": "a", "line": 1, "detail": "d"}],
                  "warnings": [], "error": "", "scanned": {"paths": 1, "content_files": 1}}
        payload = json.loads(C.format_report(report, json_mode=True))
        self.assertIn("violations", payload)
        self.assertIn("warnings", payload)
        self.assertEqual(payload["exit_code"], 1)
        self.assertIn("VIOLATION", C.format_report(report))

    def test_full_repo_tree_is_clean(self):
        report = C.run_check(C.ROOT)
        self.assertEqual(report["verdict"], "OK", json.dumps(report, ensure_ascii=True, indent=1))
        self.assertEqual(report["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
