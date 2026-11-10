"""Original R11 MENU glyph must preserve routes and fail closed on ambiguity."""
import importlib.util
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGE_PATH = ROOT / "coordination/express/stage_original_five_primary.py"
spec = importlib.util.spec_from_file_location("nox_express_stage_u04", STAGE_PATH)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)

class GraphicalOriginalMenu(unittest.TestCase):
    def source(self):
        marker='<script id="nox-express-primary-bind">'
        self.assertEqual(stage.INSERT.count(marker), 1)
        return stage.INSERT.split(marker, 1)[1].split('</script>', 1)[0]

    def test_five_existing_routes_and_no_untrusted_click(self):
        self.assertEqual(stage.INSERT.count('data-nox-primary="'), 5)
        self.assertIn("event.isTrusted", stage.INSERT)
        self.assertIn('navControl.click()', stage.INSERT)
        self.assertIn('if(labels.length!==1)return', stage.INSERT)
        self.assertIn('if(nodes.length!==1)return', stage.INSERT)

    def test_unmodified_source_pin_remains_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "U08_ORIGINAL_HOME_SHA_HOLD"):
            stage.publish(bytes(stage.ORIGINAL_BYTES))

    @unittest.skipUnless(shutil.which("node"), "Node required for inline JS dynamic regression")
    def test_original_single_text_only_menu_preserved_and_ambiguous_untouched(self):
        js = json.dumps(self.source())
        harness = """
const source=__SOURCE__;
const run=new Function('document','window',source);
function test(n) {
 const labels=Array.from({length:n},()=>{
  const txt={nodeType:3,textContent:'MENU'};
  return {textContent:'MENU',children:[],childNodes:[txt],dataset:{},
   hasAttribute(){return false},setAttribute(k,v){this.aria=v},txt};
 });
 const nav={contains(){return false},querySelector(){return null},addEventListener(){}};
 const doc={getElementById(){return nav},querySelectorAll(){return labels},
  readyState:'complete',addEventListener(){}};
 run(doc,{});
 return labels;
}
const a=test(1),b=test(2),c=test(0);
if(a[0].txt.textContent!=='✦' || a[0].aria!=='Направления HELION' ||
   a[0].dataset.noxOriginalMenuGlyph!=='true' ||
   b.some(x=>x.txt.textContent!=='MENU') || c.length!==0)process.exit(5);
""".replace('__SOURCE__',js)
        result = subprocess.run(["node", "-e", harness], capture_output=True,
                                text=True, timeout=15, check=False)
        self.assertEqual(result.returncode, 0, result.stderr[:800])


    @unittest.skipUnless(shutil.which("node"), "Node required for delayed original HOME binding")
    def test_late_original_menu_mount_is_bound_once_and_duplicates_hold(self):
        js = json.dumps(self.source())
        harness = r"""
const source=__SOURCE__;
const run=new Function('document','window',source);
function label(){
 const txt={nodeType:3,textContent:'MENU'};
 return {textContent:'MENU',children:[],childNodes:[txt],dataset:{},
         hasAttribute(){return false},setAttribute(k,v){this.aria=v},txt};
}
function fixture(initial=0){
 const labels=Array.from({length:initial},label);
 let mutation=null,observer=null,timeout=null;
 const nav={contains(){return false},querySelector(){return null},addEventListener(){}};
 const doc={getElementById(){return nav},documentElement:{},
            querySelectorAll(){return labels},readyState:'complete',addEventListener(){}};
 const win={
  MutationObserver:class{constructor(cb){mutation=cb;observer=this;this.closed=false}
    observe(){this.observed=true}disconnect(){this.closed=true}},
  setTimeout(cb,ms){if(ms!==8000)throw Error('unbounded watcher');timeout=cb;return 1},
  clearTimeout(){}
 };
 run(doc,win);
 return {labels,add:()=>labels.push(label()),mutate:()=>mutation?.(),
         timeout:()=>timeout?.(),get observer(){return observer}};
}
const late=fixture(0);late.add();late.mutate();
if(late.labels[0].txt.textContent!=='✦'||late.labels[0].aria!=='Направления HELION'||
   late.labels[0].dataset.noxOriginalMenuGlyph!=='true'||!late.observer.closed)process.exit(11);
const duplicate=fixture(0);duplicate.add();duplicate.add();duplicate.mutate();
if(duplicate.labels.some(x=>x.txt.textContent!=='MENU')||duplicate.observer.closed)process.exit(12);
duplicate.timeout();if(!duplicate.observer.closed)process.exit(13);
const immediate=fixture(1);
if(immediate.labels[0].txt.textContent!=='✦'||immediate.observer!==null)process.exit(14);
""".replace('__SOURCE__',js)
        result = subprocess.run(["node","-e",harness],capture_output=True,
                                text=True,timeout=15,check=False)
        self.assertEqual(result.returncode,0,result.stderr[:800])

    @unittest.skipUnless(shutil.which("node"), "Node required for inline JS syntax check")
    def test_script_parses_as_javascript(self):
        result = subprocess.run(["node","--check"], input=self.source(), capture_output=True,
                                text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr[:800])
