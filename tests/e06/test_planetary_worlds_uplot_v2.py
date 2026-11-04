"""NOX D02 visual planetary worlds + vendored uPlot source admission.
Only deterministic source verification; not physical WebView2 E07 or GPU training.
"""
import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / 'integrations/wow200/runtime/home-scene.mjs'
CSS = ROOT / 'integrations/wow200/runtime/home-guard.css'
P03 = ROOT / 'Packages/P03/Source/P03.ModelCenter.Wow'
BUILDER = ROOT / 'coordination/e06/build_onehost_installer.ps1'


def gitblob(path):
    data = path.read_bytes()
    return hashlib.sha1(('blob %d\0' % len(data)).encode() + data).hexdigest()


class PlanetWorldsAndUplot(unittest.TestCase):
    def test_nine_d02_orbs_untouched_and_five_planet_modes(self):
        js = HOME.read_text(encoding='utf-8')
        self.assertIn("'CONSCIOUSNESS','PERSONA','ATLAS','VOICE','REFLECTION','CORE','NEXUS','FORGE'", js)
        self.assertIn("items.length!==8", js)
        self.assertIn("MINI_START:'REDUCED',AUTO:null", js)
        self.assertIn("selectedQuality='CINEMA'", js)
        self.assertIn("NOX PLANETARY WORLDS V2", js)
        self.assertIn("panel.hidden=true", js)
        self.assertIn("home.dataset.noxPlanetWorld=selected.toLowerCase()", js)
        self.assertIn("home.dataset.noxPlanetPalette", js)
        self.assertIn("nox.d02.graphics.preference.v1", js)
        self.assertIn("localStorage?.setItem(prefKey,choice)", js)
        self.assertIn("if(!autoRaf)autoRaf=view.requestAnimationFrame(sampleAuto)", js)
        self.assertNotIn("training.start", js)
        self.assertNotIn("models.pull", js)

    def test_known_host_pages_and_real_renderer_readout(self):
        js = HOME.read_text(encoding='utf-8')
        self.assertIn("studio.href='/creative/studio.html'", js)
        self.assertIn("models.href='/creative/modelcenter/index.html'", js)
        self.assertIn("snapshot.frames", js)
        self.assertIn("snapshot.particles", js)
        self.assertIn("' · GPU Н/Д'", js)
        self.assertIn("Math.max(0,(snapshot.frames-previous.frames)*1000/(now-previous.time))", js)
        self.assertIn("home.append(dock)", js)
        self.assertIn("new view.MutationObserver(sync)", js)
        self.assertIn("film?.destroy();film=null", js)

    def test_film_and_quality_css_fail_closed(self):
        css = CSS.read_text(encoding='utf-8')
        self.assertIn("NOX PLANETARY WORLDS V2 STYLE", css)
        self.assertIn("NOX QUALITY PLANET ATMOSPHERES V2", css)
        self.assertIn("nox-quality-world[hidden]", css)
        self.assertIn("nox-quality-planet__sphere", css)
        self.assertIn('data-nox-effective="reduced"', css)
        self.assertIn("prefers-reduced-motion:reduce", css)
        self.assertIn("forced-colors:active", css)
        self.assertIn("pointer-events:none", css)
        self.assertIn("nox-cinema-film", css)

    def test_licensed_uplot_source_and_windows_packaging(self):
        build = BUILDER.read_text(encoding='utf-8')
        files = {
            'vendor/uPlot.iife.min.js': '6749c4f02499c6999245f406f4bd208985f89aee',
            'vendor/uPlot.min.css': '976000608e7ee21ef0c700b08ad6f90834b40055',
            'vendor/uPlot.LICENSE.txt': 'cde4b3f8352d147d5e626fea36358797c4fc06f2',
        }
        for relative, sha in files.items():
            with self.subTest(file=relative):
                self.assertEqual(gitblob(P03/relative), sha)
                self.assertIn("relative='%s';blob='%s'" % (relative, sha), build)
        lic = (P03/'vendor/uPlot.LICENSE.txt').read_text(encoding='utf-8')
        self.assertIn('Permission is hereby granted', lic)
        self.assertIn('Copyright', lic)

    def test_onehost_only_real_chart_no_second_downloader(self):
        html = (P03/'index.html').read_text(encoding='utf-8')
        js = (P03/'ui.js').read_text(encoding='utf-8')
        css = (P03/'ui.css').read_text(encoding='utf-8')
        self.assertIn('href="vendor/uPlot.min.css"', html)
        self.assertIn('src="vendor/uPlot.iife.min.js"', html)
        self.assertIn('id="noxTracePlot"', html)
        self.assertIn('id="quickInstallGrid"', html)
        self.assertIn('connect-src \'none\'', html)
        self.assertIn('NOX VERIFIED NATIVE OBSERVATORY', js)
        self.assertIn("p03.snapshot.v1", js)
        self.assertIn("p03.event.v1", js)
        self.assertIn("typeof window.uPlot!=='function'", js)
        self.assertIn("sampleNativeTrace();render();", js)
        self.assertIn("NOX OBSERVATORY UPlot V1", css)
        self.assertNotIn("fetch(", js)
        self.assertEqual(html.count('class="tool-source-card"'), 12)


if __name__ == '__main__':
    unittest.main()
