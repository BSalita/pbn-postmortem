"""Streamlit must reach postmortem data only through the REST API client."""

from __future__ import annotations

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
STREAMLIT_APP = ROOT / "postmortem_pbn_streamlit.py"
FORBIDDEN_MODULES = {
    "pbn_postmortem_create",
    "pbn_postmortem_service",
}


class StreamlitApiBoundaryTests(unittest.TestCase):
    def test_streamlit_does_not_import_the_library(self) -> None:
        source = STREAMLIT_APP.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        violations = {module for module in modules if module in FORBIDDEN_MODULES}
        self.assertFalse(
            violations,
            f"{STREAMLIT_APP.name} bypasses the REST API: {sorted(violations)}",
        )
        self.assertIn("pbn_postmortem_api_client", modules)


if __name__ == "__main__":
    unittest.main()
