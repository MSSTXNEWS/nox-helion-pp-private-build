"""B1 R60: cumulative R55-R59 real Chromium DOM checks, no native network."""
from pathlib import Path
import runpy
import subprocess
import os
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
ADAPTER = ROOT / "b1_abort_safe_ui_adapter.js"
BASE_SUITE = ROOT / "test_b1_r58_adapter_chromium.py"
EXPECTED = {
    ADAPTER: "9a9365258888e218990e0126bdc918605005777f",
    BASE_SUITE: "28361cd34c1cc6a4ae203c48e4eea42aec23a295",
}
R59 = r"""
async () => {
  const {createUiAdapter}=window.NOXB1AbortSafeUI;
  const checks=[];
  const check=(v,label)=>{if(!v)throw Error(label);checks.push(label);};
  const fresh=()=>document.body.appendChild(document.createElement('section'));
  const s={conversation_id:'dialog',exchange_id:'turn2'};
  const c=fresh(), ac=new AbortController(); let calls=0;
  const a=createUiAdapter({container:c,beforeCommit(kind,scope){
    calls++; scope.conversation_id='foreign';scope.exchange_id='turn99';
  }});
  check(await a.onDelta(s,'alpha',ac.signal,'e1')===true,'R59 delta succeeds');
  check(c.children.length===1&&c.firstElementChild.dataset.noxB1Conversation==='dialog'&&
    c.firstElementChild.dataset.noxB1Exchange==='turn2','R59 pinned identity');
  check(await a.onDelta(s,'alpha',ac.signal,'e1')===false&&calls===1,'R59 duplicate suppressed');
  check(await a.upsertTerminal(s,'done2',ac.signal)===true,'R59 terminal succeeds');
  check(c.children.length===1&&c.firstElementChild.dataset.noxB1State==='terminal'&&
    c.firstElementChild.dataset.noxB1EventId==='done2'&&c.textContent==='alpha','R59 immutable row');
  check(await a.upsertTerminal(s,'done2',ac.signal)===true&&calls===2,'R59 terminal replay no callback');
  let reads=0;
  const changing={conversation_id:'dialog',get exchange_id(){return ++reads===1?'turn3':'foreign';}};
  check(await a.onDelta(changing,'beta',ac.signal,'e2')===true&&reads===1,'R59 getter read once');
  check(c.children.length===2&&c.lastElementChild.dataset.noxB1Exchange==='turn3'&&
    c.lastElementChild.textContent==='beta','R59 separate third turn');
  const stopped=new AbortController(), d=fresh();
  const b=createUiAdapter({container:d,beforeCommit(kind,scope){scope.exchange_id='foreign';stopped.abort();}});
  check(await b.onDelta(s,'never',stopped.signal,'e3')===false&&d.children.length===0,'R59 STOP no row');
  const resume=createUiAdapter({container:d}), live=new AbortController();
  check(await resume.onDelta(s,'once',live.signal,'e3')===true&&
    d.children.length===1&&d.firstElementChild.dataset.noxB1Exchange==='turn2','R59 replay correct row');
  check(await resume.onDelta(s,'once',live.signal,'e3')===false&&d.textContent==='once','R59 replay exactly once');
  const terminalStop=new AbortController(), e=fresh();
  const z=createUiAdapter({container:e,beforeCommit(kind,scope){scope.exchange_id='foreign';terminalStop.abort();}});
  check(await z.upsertTerminal(s,'done2',terminalStop.signal)===false&&e.children.length===0,'R59 terminal STOP');
  check(await createUiAdapter({container:e}).upsertTerminal(s,'done2',live.signal)===true&&
    e.children.length===1&&e.firstElementChild.dataset.noxB1Exchange==='turn2','R59 terminal resume');
  return checks;
}
"""

def main():
    for path, expected in EXPECTED.items():
        actual = subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()
        assert actual == expected, (path.name, actual, expected)
    base_js = runpy.run_path(str(BASE_SUITE))["JS"]
    with sync_playwright() as p:
        kwargs = {}
        if os.environ.get("B1_LOCAL_CHROMIUM"):
            kwargs["executable_path"] = os.environ["B1_LOCAL_CHROMIUM"]
        browser = p.chromium.launch(headless=True, **kwargs)
        try:
            page = browser.new_page()
            requests = []
            page.on("request", lambda req: requests.append(req.url))
            page.route("**/*", lambda route: route.abort())
            page.set_content("<html><body></body></html>")
            page.add_script_tag(path=str(ADAPTER))
            base = page.evaluate(base_js)
            assert len(base) == 20, base
            extra = page.evaluate(R59)
            assert len(extra) == 13, extra
            assert not requests, requests
            for label in base + extra:
                print("PASS", label)
            print(f"B1 R60 Chromium {browser.version} 33/33 PASS; zero network; adapter={EXPECTED[ADAPTER]}; baseline={EXPECTED[BASE_SUITE]}")
        finally:
            browser.close()

if __name__ == "__main__":
    main()
