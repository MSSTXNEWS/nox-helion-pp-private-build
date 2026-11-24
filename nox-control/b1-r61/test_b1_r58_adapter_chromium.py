"""B1 R58: actual Chromium DOM regression for R55/R56/R57; no native network."""
from pathlib import Path
import subprocess

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
ADAPTER = ROOT / "b1_abort_safe_ui_adapter.js"
EXPECTED_BLOB = "717f92cec61cd78795c38fe273fb0fdef78d6240"
JS = r"""
async () => {
  const {createUiAdapter} = window.NOXB1AbortSafeUI;
  const checks = [];
  const check = (v, label) => {if (!v) throw Error(label); checks.push(label);};
  const within = async (p, ms=1500) => {
    let t;
    try {return await Promise.race([p, new Promise((_, reject) => {
      t=setTimeout(()=>reject(Error('unexpected blocked waiter')), ms);
    })]);} finally {clearTimeout(t);}
  };
  const defer = () => {let resolve; const promise = new Promise(r=>resolve=r); return {promise,resolve};};
  const fresh = () => {const c=document.createElement('section'); document.body.append(c); return c;};
  const s = {conversation_id:'r58-dialog', exchange_id:'r58-exchange'};
  const makeSignal = () => new AbortController();
  const expectConflict = async (p, label) => {
    let code; try {await within(p);} catch(e) {code=e.code;}
    check(code==='HOLD_B1_UI_REPLAY_PAYLOAD',label);
  };
  // R55: no late precommit after terminal. Known ID conflict still fails closed.
  {
    const c=fresh(), signal=makeSignal().signal;
    let deltas=0, late=false;
    const a=createUiAdapter({container:c,deltaPrecommitTimeoutMs:5000,
      beforeCommit: kind=>{if(kind==='delta'){deltas++; if(late) return new Promise(()=>{});}}});
    check(await within(a.onDelta(s,'A',signal,'d1'))===true,'R55 initial delta');
    check(await within(a.upsertTerminal(s,'done',signal))===true,'R55 terminal');
    late=true;
    check(await within(a.onDelta(s,'late',signal,'d2'))===false,'R55 late delta promptly ignored');
    await expectConflict(a.onDelta(s,'different',signal,'d1'),'R55 known ID conflict');
    check(deltas===1&&c.children.length===1&&c.textContent==='A'&&
      c.firstElementChild.dataset.noxB1State==='terminal','R55 immutable one row, no late precommit');
  }
  // R56: own STOP returns while prior live FIFO callback is blocked.
  {
    const c=fresh(), entered=defer(), gate=defer();
    const first=makeSignal(), second=makeSignal(), third=makeSignal();
    let calls=0;
    const a=createUiAdapter({container:c,deltaPrecommitTimeoutMs:5000,
      beforeCommit: kind=>{if(kind==='delta'&&++calls===1){entered.resolve();return gate.promise;}}});
    const b=createUiAdapter({container:c});
    const p1=a.onDelta(s,'A',first.signal,'d1'); await within(entered.promise);
    const p2=a.onDelta(s,'B',second.signal,'d2');
    let thirdSettled=false;
    const p3=b.onDelta(s,'C',third.signal,'d3').then(x=>{thirdSettled=true;return x;});
    second.abort();
    try {
      check(await within(p2)===false,'R56 queued own STOP prompt');
      check(!thirdSettled&&calls===1&&c.children.length===0,'R56 FIFO remains held');
    } finally {gate.resolve();}
    check(await within(p1)===true&&await within(p3)===true,'R56 unaffected deltas complete');
    check(c.textContent==='AC'&&calls===1,'R56 stopped callback not invoked');
    const replay=makeSignal().signal;
    check(await within(b.onDelta(s,'B',replay,'d2'))===true,'R56 canceled ID can be replayed');
    check(await within(b.onDelta(s,'B',replay,'d2'))===false,'R56 same replay suppressed');
    check(await within(b.upsertTerminal(s,'done',replay))===true&&
      c.children.length===1&&c.textContent==='ACB','R56 one final DOM row');
  }
  // R57: pending terminal must reject conflicting committed AND reserved IDs.
  {
    const c=fresh(), entered=defer(), gate=defer();
    const a=createUiAdapter({container:c,terminalTimeoutMs:5000,
      beforeCommit:kind=>{if(kind==='terminal'){entered.resolve();return gate.promise;}}});
    const b=createUiAdapter({container:c});
    const signal=makeSignal().signal;
    check(await within(a.onDelta(s,'A',signal,'d1'))===true,'R57 committed initial');
    const terminal=a.upsertTerminal(s,'done',signal);
    await within(entered.promise);
    try {
      await expectConflict(b.onDelta(s,'different',signal,'d1'),'R57 committed conflict while terminal pending');
      check(await within(b.onDelta(s,'A',signal,'d1'))===false,'R57 equal replay suppressed');
      check(await within(b.onDelta(s,'new',signal,'d2'))===false,'R57 fresh delta suppressed');
    } finally {gate.resolve();}
    check(await within(terminal)===true&&c.children.length===1&&c.textContent==='A','R57 canonical terminal unchanged');
  }
  {
    const c=fresh(), entered=defer(), gate=defer();
    const a=createUiAdapter({container:c,deltaPrecommitTimeoutMs:5000,terminalTimeoutMs:5000,
      beforeCommit:kind=>{if(kind==='delta'){entered.resolve();return gate.promise;}}});
    const b=createUiAdapter({container:c});
    const signal=makeSignal().signal;
    const delta=a.onDelta(s,'A',signal,'d1'); await within(entered.promise);
    const terminal=a.upsertTerminal(s,'done',signal);
    try {
      await expectConflict(b.onDelta(s,'different',signal,'d1'),'R57 reserved conflict while terminal pending');
      check(await within(b.onDelta(s,'A',signal,'d1'))===false,'R57 reserved equal suppressed');
    } finally {gate.resolve();}
    check(await within(delta)===true&&await within(terminal)===true&&
      c.children.length===1&&c.textContent==='A','R57 reserved FIFO terminal single row');
  }
  return checks;
}
"""

def main():
    blob = subprocess.check_output(["git", "hash-object", str(ADAPTER)], text=True).strip()
    if blob != EXPECTED_BLOB:
        raise AssertionError(f"adapter blob mismatch {blob}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            requests = []
            page.on("request", lambda req: requests.append(req.url))
            page.route("**/*", lambda route: route.abort())
            page.set_content("<html><body></body></html>")
            page.add_script_tag(path=str(ADAPTER))
            checks = page.evaluate(JS)
            assert not requests, f"unexpected network {requests}"
            assert len(checks) == 20, checks
            for label in checks:
                print("PASS", label)
            print(f"B1 R58 Chromium {browser.version} {len(checks)}/{len(checks)} PASS; zero network; blob={blob}")
        finally:
            browser.close()

if __name__ == "__main__":
    main()
