"""Runtime regression for the original HOME link guard, not a Windows E07 receipt."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'coordination/express/stage_original_five_primary.py'
spec = importlib.util.spec_from_file_location('nox_express_u01', SOURCE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class OriginalNavigationSecurity(unittest.TestCase):
    def test_guard_is_in_original_click_route(self):
        self.assertIn('function safeOriginalLink(a){', module.INSERT)
        self.assertIn('safeOriginalLink(a));', module.INSERT)
        self.assertIn('нет подтверждённого исходного экрана · HOLD', module.INSERT)
        self.assertIn('event.isTrusted', module.INSERT)

    def test_real_js_navigation_cases(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node unavailable; JS not executed and MUST NOT be claimed PASS')
        fn = 'function safeOriginalLink(a){' + module.INSERT.split('function safeOriginalLink(a){', 1)[1].split('\\nfunction findOriginalScreen', 1)[0]
        checks = r'''
const assert=require('node:assert/strict');
const document={baseURI:'https://127.0.0.1:8822/Assets/index.html'};
const anchor=href=>({getAttribute:()=>href});
const cases=[
 ['#chat','https://127.0.0.1:8822/Assets/index.html',true],
 ['pages/report.html','https://127.0.0.1:8822/Assets/index.html',true],
 ['/install','https://127.0.0.1:8822/Assets/index.html',true],
 ['https://evil.example/models','https://127.0.0.1:8822/Assets/index.html',false],
 ['//evil.example/models','https://127.0.0.1:8822/Assets/index.html',false],
 ['javascript:alert(1)','https://127.0.0.1:8822/Assets/index.html',false],
 ['file:///C:/secret.txt','file:///C:/NOX/Assets/index.html',false],
 ['../secrets.html','file:///C:/NOX/Assets/index.html',false],
 ['#chat','file:///C:/NOX/Assets/index.html',true],
 ['\\\\evil\\attack','https://127.0.0.1:8822/Assets/index.html',false],
 ['https://127.0.0.1:8822/Assets/index.html','https://127.0.0.1:8822/Assets/index.html',false],
];
for(const [href,base,expected] of cases){document.baseURI=base;
 assert.equal(safeOriginalLink(anchor(href)),expected,href);}
console.log('11/11 PASS');
'''
        result = subprocess.run([node, '-e', fn+'\\n'+checks], capture_output=True,
                                text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('11/11 PASS', result.stdout)

if __name__ == '__main__': unittest.main()
