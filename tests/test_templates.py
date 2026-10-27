"""Static checks on templates/*.html.

Guards two bugs found in the monthly template (2026-10-26):
  - onclick handlers (switchLang / toggleDark) that the template never defined;
  - cbp-base.css compat vars (--kb-*) mapped to custom properties the template never declares.
"""
import re
import unittest
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
# Globals / builtins that may legitimately start an onclick expression.
BUILTIN_CALLEES = {"window", "document", "history", "location", "navigator", "this", "event"}


def _html_files():
    return sorted(TEMPLATES.glob("*.html"))


def _script_text(html):
    return "\n".join(re.findall(r"(?s)<script\b[^>]*>(.*?)</script>", html))


class TemplateChecks(unittest.TestCase):
    def test_templates_exist(self):
        self.assertTrue(_html_files(), "no templates found")

    def test_onclick_handlers_are_defined(self):
        for f in _html_files():
            html = f.read_text(encoding="utf-8")
            js = _script_text(html)
            callees = set(re.findall(r'onclick="\s*([A-Za-z_$][\w$]*)\s*\(', html)) - BUILTIN_CALLEES
            for name in sorted(callees):
                defined = re.search(
                    r"\bfunction\s+%s\s*\(|\b(?:const|let|var)\s+%s\s*=|\bwindow\.%s\s*=" % ((re.escape(name),) * 3),
                    js,
                )
                with self.subTest(template=f.name, handler=name):
                    self.assertIsNotNone(defined, "%s calls %s() but never defines it" % (f.name, name))

    def test_kb_compat_vars_resolve(self):
        for f in _html_files():
            html = f.read_text(encoding="utf-8")
            css = "\n".join(re.findall(r"(?s)<style\b[^>]*>(.*?)</style>", html))
            declared = set(re.findall(r"(--[\w-]+)\s*:", css))
            for kb, target in re.findall(r"(--kb-[\w-]+)\s*:\s*var\(\s*(--[\w-]+)", css):
                with self.subTest(template=f.name, var=kb):
                    self.assertIn(target, declared, "%s maps %s to undeclared %s" % (f.name, kb, target))

    def test_bilingual_attrs_paired(self):
        for f in _html_files():
            html = f.read_text(encoding="utf-8")
            with self.subTest(template=f.name):
                self.assertEqual(html.count("data-zh="), html.count("data-en="),
                                 "%s: data-zh / data-en counts differ" % f.name)


if __name__ == "__main__":
    unittest.main()
