#!/usr/bin/env python3
"""One targeted real-Chromium acceptance for B1 abort-safe UI projection.

Source-only synthetic browser test: not native model, signed ACK, or S03 proof.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

SOURCE = Path(__file__).with_name("b1_abort_safe_ui_adapter.js")

def main():
    checks = []
    def check(name, ok):
        checks.append((name, bool(ok)))
        if not ok:
            raise AssertionError(name)
    with sync_playwright() as p:
        # Use CI-pinned Playwright Chromium, with local system fallback.
        launch = {"headless": True, "args": ["--no-sandbox"]}
        if not Path(p.chromium.executable_path).is_file() and Path("/usr/bin/chromium").is_file():
            launch["executable_path"] = "/usr/bin/chromium"
        browser = p.chromium.launch(**launch)
        page = browser.new_page()
        page.set_content('<main id="chat"></main>')
        page.add_script_tag(path=str(SOURCE))
        page.evaluate("""()=> {
          const chat=document.querySelector('#chat');
          window.s1={conversation_id:'dialog',exchange_id:'turn-1'};
          window.s2={conversation_id:'dialog',exchange_id:'turn-2'};
          window.gate=null;
          window.adapter=NOXB1AbortSafeUI.createUiAdapter({
            container:chat,
            beforeCommit:async(kind,s)=>{
              if(kind==='delta'&&s.exchange_id==='turn-1'&&window.gate)
                await window.gate.promise;
            }
          });
          window.ctrl1=new AbortController();
          window.ctrl2=new AbortController();
          window.children=()=>Array.from(chat.children).map(el=>({
            conversation:el.dataset.noxB1Conversation,
            exchange:el.dataset.noxB1Exchange,
            state:el.dataset.noxB1State,
            event:el.dataset.noxB1EventId||'',
            text:el.textContent
          }));
        }""")
        check("stream first exchange creates exactly one DOM turn", page.evaluate(
            """async()=>{await adapter.onDelta(s1,'Hello',ctrl1.signal);
            await adapter.onDelta(s1,' world',ctrl1.signal);
            return children().length===1&&children()[0].text==='Hello world';}"""))
        check("second exchange creates a separate turn", page.evaluate(
            """async()=>{await adapter.onDelta(s2,'Hola',ctrl2.signal);
            return children().length===2&&children()[1].text==='Hola';}"""))
        check("model HTML is rendered as inert text", page.evaluate(
            """async()=>{await adapter.onDelta(s2,'<img src=x onerror=alert(1)>',ctrl2.signal);
            return document.querySelectorAll('img').length===0 &&
              children()[1].text.includes('<img src=x');}"""))
        # Pause one in-flight UI callback, STOP, then release the callback.
        page.evaluate("""()=>{
          let release;
          gate={promise:new Promise(r=>release=r),release};
          window.delayed=adapter.onDelta(s1,' MUST-NOT-APPEAR',ctrl1.signal);
        }""")
        page.evaluate("()=>ctrl1.abort()")
        page.evaluate("()=>gate.release()")
        check("late delta promise returns false after STOP",page.evaluate("()=>delayed") is False)
        check("STOP leaves the already displayed partial answer untouched", page.evaluate(
            "()=>children()[0].text==='Hello world'"))
        check("STOP rejects further delta without scheduling", page.evaluate(
            "()=>adapter.onDelta(s1,' NEVER',ctrl1.signal)") is False)
        check("reconnect projects two unique terminal identities", page.evaluate(
            """async()=>{
              await adapter.upsertTerminal(s1,'event-111');
              await adapter.upsertTerminal(s2,'event-222');
              return children().length===2&&children().every(x=>x.state==='terminal');
            }"""))
        check("duplicate readback is idempotent",page.evaluate(
            """async()=>{await adapter.upsertTerminal(s1,'event-111');
               return children().length===2&&children()[0].event==='event-111';}"""))
        check("adapter recreation does not duplicate DOM turn",page.evaluate(
            """async()=>{const replacement=NOXB1AbortSafeUI.createUiAdapter({container:document.querySelector('#chat')});
               await replacement.upsertTerminal(s2,'event-222');
               return children().length===2&&children()[1].event==='event-222';}"""))
        check("conflicting terminal event fails closed",page.evaluate(
            """async()=>{try{await adapter.upsertTerminal(s1,'conflicting-event');return false;}
              catch(e){return e.code==='HOLD_B1_UI_CONFLICTING_TERMINAL'&&children().length===2;}}"""))
        check("late streaming cannot mutate verified terminal projection",page.evaluate(
            "()=>adapter.onDelta(s2,' LATE',ctrl2.signal)") is False)
        check("same-dialog scope is preserved across two turns",page.evaluate(
            "()=>children().every(x=>x.conversation==='dialog')&&children()[0].exchange!==children()[1].exchange"))
        # Timeout is represented by the same AbortSignal semantics as explicit STOP.
        page.evaluate("""()=>{window.timeoutCtrl=new AbortController();timeoutCtrl.abort();}""")
        check("expired timeout signal is rejected", page.evaluate(
            "()=>adapter.onDelta({conversation_id:'dialog',exchange_id:'turn-3'},'no',timeoutCtrl.signal)") is False)
        check("no third turn was inserted",page.evaluate("()=>children().length===2"))
        check("no other browser requests or ACKs are made by adapter",page.evaluate(
            "()=>typeof adapter.post==='undefined'&&typeof adapter.ack==='undefined'"))
        check("concurrent async UI deltas preserve first-in-first-out text",page.evaluate("""async()=>{
          const container=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'turn-fifo'};
          const ctrl=new AbortController();
          let release,entered=0;
          const ui=NOXB1AbortSafeUI.createUiAdapter({container,beforeCommit:async()=>{
            entered++;
            if(entered===1) await new Promise(resolve=>release=resolve);
          }});
          const first=ui.onDelta(s,'A',ctrl.signal);
          const second=ui.onDelta(s,'B',ctrl.signal);
          for(let i=0;i<30&&!release;i++) await new Promise(r=>setTimeout(r,0));
          if(!release||entered!==1) return false;
          release();
          const results=await Promise.all([first,second]);
          const nodes=Array.from(container.children).filter(
            e=>e.dataset.noxB1Exchange===s.exchange_id);
          return results.every(Boolean)&&entered===2&&nodes.length===1&&
            nodes[0].textContent==='AB';
        }"""))
        check("STOP unblocks hung first precommit and drops queued deltas",page.evaluate("""async()=>{
          const container=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'turn-stop-queued'};
          const ctrl=new AbortController();
          let entered=0;
          const ui=NOXB1AbortSafeUI.createUiAdapter({container,beforeCommit:async()=>{
            entered++;
            await new Promise(()=>{});
          }});
          const first=ui.onDelta(s,'A',ctrl.signal);
          const second=ui.onDelta(s,'B',ctrl.signal);
          for(let i=0;i<30&&entered===0;i++) await new Promise(r=>setTimeout(r,0));
          if(entered!==1) return false;
          ctrl.abort();
          const results=await Promise.race([
            Promise.all([first,second]),
            new Promise(r=>setTimeout(()=>r('HUNG'),300))
          ]);
          return Array.isArray(results)&&results.length===2&&
            results.every(x=>x===false)&&entered===1&&
            !Array.from(container.children).some(
              e=>e.dataset.noxB1Exchange===s.exchange_id);
        }"""))
        browser.close()
    print(f"B1 source-only real Chromium: {len(checks)}/{len(checks)} PASS")
    for name, _ in checks:
        print("PASS",name)

if __name__ == "__main__":
    main()
