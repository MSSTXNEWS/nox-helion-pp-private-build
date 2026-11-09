"""T06 no-loss repair source contract. Runtime compile is a separate Windows gate."""
import importlib.util
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
STAGER=ROOT/"coordination/e06/stage_p05_html_verbatim.py"
BUILDER=ROOT/"coordination/e06/build_onehost_installer.ps1"

class P05VerbatimSourceTests(unittest.TestCase):
    def test_lossless_html_and_dynamic_expressions(self):
        spec=importlib.util.spec_from_file_location("e06_p05_stage",STAGER)
        mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fixture='return """<div class="a">""" + E(value) + """</div>""";'
        original=mod.PATTERN.findall(fixture)
        patched=mod.PATTERN.sub(
            lambda m:'@"'+m.group(1).replace('"','""')+'"',fixture)
        recovered=mod.VERBATIM.sub(
            lambda m:'"""'+m.group(1).replace('""','"')+'"""',patched)
        self.assertEqual(recovered,fixture)
        self.assertEqual(len(original),2)
        self.assertIn(' + E(value) + ',patched)
    def test_stager_pinned_before_wpf_publish(self):
        source=BUILDER.read_text("utf-8")
        self.assertIn("E06_P05_REPAIR_PIN_HOLD",source)
        self.assertIn("E06_P05_EXACT_HTML_REPAIR_HOLD",source)
        self.assertLess(source.index("E06_P05_EXACT_HTML_REPAIR_HOLD"),
                        source.index("& dotnet publish $project"))
