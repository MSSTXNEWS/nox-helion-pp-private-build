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
        check("terminal reservation drains earlier FIFO delta but rejects later SSE delta", page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'terminal-fifo'};
          const ctrl=new AbortController();
          let release;
          const pending=new Promise(r=>release=r);
          const ui=NOXB1AbortSafeUI.createUiAdapter({container:chat,
            beforeCommit:async kind=>{if(kind==='delta') await pending;}});
          const early=ui.onDelta(s,'BEFORE',ctrl.signal);
          const terminal=ui.upsertTerminal(s,'canonical-terminal-1');
          const late=await ui.onDelta(s,' LATE',ctrl.signal);
          if(late!==false) return false;
          release();
          const results=await Promise.all([early,terminal]);
          const nodes=Array.from(chat.children).filter(
            e=>e.dataset.noxB1Exchange===s.exchange_id);
          return results.every(Boolean)&&nodes.length===1&&
            nodes[0].textContent==='BEFORE'&&nodes[0].dataset.noxB1State==='terminal';
        }"""))
        check("concurrent identical terminal readbacks coalesce and conflict holds", page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'terminal-coalesce'};
          let release,calls=0;
          const pending=new Promise(r=>release=r);
          const ui=NOXB1AbortSafeUI.createUiAdapter({container:chat,
            beforeCommit:async kind=>{if(kind==='terminal'){calls++;await pending;}}});
          const first=ui.upsertTerminal(s,'canonical-terminal-2');
          const second=ui.upsertTerminal(s,'canonical-terminal-2');
          let conflicted=false;
          try{ui.upsertTerminal(s,'different-terminal');}
          catch(e){conflicted=e.code==='HOLD_B1_UI_CONFLICTING_TERMINAL';}
          release();
          const results=await Promise.all([first,second]);
          return first===second&&conflicted&&results.every(Boolean)&&calls===1&&
            Array.from(chat.children).filter(
              e=>e.dataset.noxB1Exchange===s.exchange_id).length===1;
        }"""))
        check("failed terminal precommit releases reservation for safe retry", page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'terminal-retry'};
          let fail=true;
          const ui=NOXB1AbortSafeUI.createUiAdapter({container:chat,
            beforeCommit:async kind=>{if(kind==='terminal'&&fail) throw Error('hold');}});
          let rejected=false;
          try{await ui.upsertTerminal(s,'canonical-terminal-3');}
          catch(_){rejected=true;}
          if(!rejected) return false;
          fail=false;
          const delta=await ui.onDelta(s,'RETRY',new AbortController().signal);
          const terminal=await ui.upsertTerminal(s,'canonical-terminal-3');
          const nodes=Array.from(chat.children).filter(
            e=>e.dataset.noxB1Exchange===s.exchange_id);
          return delta===true&&terminal===true&&nodes.length===1&&
            nodes[0].textContent==='RETRY'&&nodes[0].dataset.noxB1State==='terminal';
        }"""))
        check("a second exchange progresses while first terminal is pending", page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s1={conversation_id:'dialog',exchange_id:'terminal-wait'};
          const s2={conversation_id:'dialog',exchange_id:'next-exchange'};
          let release,entered=false;
          const pending=new Promise(r=>release=r);
          const ui=NOXB1AbortSafeUI.createUiAdapter({container:chat,
            beforeCommit:async(kind,s)=>{
              if(kind==='terminal'&&s.exchange_id===s1.exchange_id){
                entered=true;await pending;
              }
            }});
          const terminal=ui.upsertTerminal(s1,'canonical-terminal-4');
          for(let i=0;i<10&&!entered;i++) await Promise.resolve();
          const next=await ui.onDelta(s2,'NEXT',new AbortController().signal);
          release();await terminal;
          const nodes=Array.from(chat.children).filter(
            e=>e.dataset.noxB1Exchange===s2.exchange_id);
          return entered&&next===true&&nodes.length===1&&nodes[0].textContent==='NEXT';
        }"""))
        check("STOP releases hung terminal precommit without late DOM write and permits GET-only retry",page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'terminal-hung-stop'};
          let release,entered=false,calls=0;
          const pending=new Promise(r=>release=r);
          const ui=NOXB1AbortSafeUI.createUiAdapter({container:chat,
            terminalTimeoutMs:1000,
            beforeCommit:async kind=>{
              if(kind==='terminal'&&++calls===1){entered=true;await pending;}
            }});
          const ctrl=new AbortController();
          const attempt=ui.upsertTerminal(s,'event-stop',ctrl.signal);
          for(let i=0;i<20&&!entered;i++) await Promise.resolve();
          if(!entered)return false;
          ctrl.abort();
          const result=await Promise.race([
            attempt,new Promise(r=>setTimeout(()=>r('HUNG'),250))
          ]);
          release();
          await new Promise(r=>setTimeout(r,0));
          const nodes=()=>Array.from(chat.children).filter(
            x=>x.dataset.noxB1Exchange===s.exchange_id);
          if(result!==false||nodes().length!==0)return false;
          const retry=await ui.upsertTerminal(s,'event-stop',new AbortController().signal);
          return retry===true&&nodes().length===1&&
            nodes()[0].dataset.noxB1EventId==='event-stop'&&calls===2;
        }"""))
        check("terminal UI precommit timeout fences late completion and allows retry",page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'terminal-hung-timeout'};
          let release,calls=0;
          const pending=new Promise(r=>release=r);
          const ui=NOXB1AbortSafeUI.createUiAdapter({container:chat,
            terminalTimeoutMs:30,
            beforeCommit:async kind=>{
              if(kind==='terminal'&&++calls===1) await pending;
            }});
          let timedOut=false;
          try{await ui.upsertTerminal(s,'event-timeout');}
          catch(e){timedOut=e.code==='HOLD_B1_UI_TERMINAL_TIMEOUT';}
          release();
          await new Promise(r=>setTimeout(r,0));
          const nodes=()=>Array.from(chat.children).filter(
            x=>x.dataset.noxB1Exchange===s.exchange_id);
          if(!timedOut||nodes().length!==0)return false;
          const retry=await ui.upsertTerminal(s,'event-timeout');
          return retry===true&&nodes().length===1&&
            nodes()[0].dataset.noxB1State==='terminal'&&calls===2;
        }"""))
        check("fresh reconnect signal reprojects aborted pending terminal without duplicate turn",page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'terminal-stop-reconnect'};
          const stopped=new AbortController();
          const fresh=new AbortController();
          let entered=false,release,calls=0;
          const hung=new Promise(resolve=>release=resolve);
          const ui=NOXB1AbortSafeUI.createUiAdapter({container:chat,
            terminalTimeoutMs:1000,
            beforeCommit:async kind=>{
              if(kind==='terminal'&&++calls===1){entered=true;await hung;}
            }});
          const first=ui.upsertTerminal(s,'canonical-reconnect-id',stopped.signal);
          for(let i=0;i<30&&!entered;i++) await new Promise(r=>setTimeout(r,0));
          if(!entered)return false;
          stopped.abort();
          const second=ui.upsertTerminal(s,'canonical-reconnect-id',fresh.signal);
          let conflict=false;
          try{ui.upsertTerminal(s,'evil-other-id',fresh.signal);}
          catch(e){conflict=e.code==='HOLD_B1_UI_CONFLICTING_TERMINAL';}
          const results=await Promise.race([
            Promise.all([first,second]),
            new Promise(r=>setTimeout(()=>r('HUNG'),250))
          ]);
          if(!Array.isArray(results)||results[0]!==false||results[1]!==true)
            return false;
          release();
          await new Promise(r=>setTimeout(r,0));
          const rows=Array.from(chat.children).filter(
            x=>x.dataset.noxB1Exchange===s.exchange_id);
          // A later explicit readback may re-run beforeCommit; this test only
          // asserts the in-flight reconnect retry and one visible terminal.
          return conflict&&calls===2&&rows.length===1&&
            rows[0].dataset.noxB1State==='terminal'&&
            rows[0].dataset.noxB1EventId==='canonical-reconnect-id'&&
            rows[0].textContent==='';
        }"""))
        check("reconnect subscribed before old STOP retries same terminal exactly once",page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'terminal-early-reconnect'};
          const old=new AbortController(),fresh=new AbortController();
          let entered=false,release,commits=0;
          const hung=new Promise(resolve=>release=resolve);
          const ui=NOXB1AbortSafeUI.createUiAdapter({container:chat,
            terminalTimeoutMs:1000,beforeCommit:async kind=>{
              if(kind==='terminal'&&++commits===1){entered=true;await hung;}
            }});
          const first=ui.upsertTerminal(s,'event-reconnect-early',old.signal);
          for(let i=0;i<30&&!entered;i++) await Promise.resolve();
          if(!entered)return false;
          // Unlike prior regression, reconnect is issued BEFORE STOP.
          const second=ui.upsertTerminal(s,'event-reconnect-early',fresh.signal);
          old.abort();
          const results=await Promise.race([
            Promise.all([first,second]),
            new Promise(r=>setTimeout(()=>r('HUNG'),250))
          ]);
          release();await new Promise(r=>setTimeout(r,0));
          const rows=Array.from(chat.children).filter(
            x=>x.dataset.noxB1Exchange===s.exchange_id);
          return Array.isArray(results)&&results[0]===false&&
            results[1]===true&&commits===2&&rows.length===1&&
            rows[0].dataset.noxB1EventId==='event-reconnect-early'&&
            rows[0].dataset.noxB1State==='terminal';
        }"""))
        check("fresh STOP while reconnect waits prevents terminal DOM commit",page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'terminal-fresh-stop'};
          const old=new AbortController(),fresh=new AbortController();
          let entered=false,release;
          const hung=new Promise(resolve=>release=resolve);
          const ui=NOXB1AbortSafeUI.createUiAdapter({container:chat,
            terminalTimeoutMs:1000,beforeCommit:async kind=>{
              if(kind==='terminal'){entered=true;await hung;}
            }});
          const first=ui.upsertTerminal(s,'event-fresh-stop',old.signal);
          for(let i=0;i<30&&!entered;i++) await Promise.resolve();
          if(!entered)return false;
          const second=ui.upsertTerminal(s,'event-fresh-stop',fresh.signal);
          fresh.abort();old.abort();
          const results=await Promise.race([
            Promise.all([first,second]),
            new Promise(r=>setTimeout(()=>r('HUNG'),250))
          ]);
          release();await new Promise(r=>setTimeout(r,0));
          return Array.isArray(results)&&results.every(x=>x===false)&&
            !Array.from(chat.children).some(
              x=>x.dataset.noxB1Exchange===s.exchange_id);
        }"""))
        check("fresh STOP releases reconnect waiter while old terminal is still hung",page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'terminal-waiter-quick-stop'};
          const old=new AbortController(),fresh=new AbortController();
          let entered=false,release,commits=0;
          const gate=new Promise(resolve=>release=resolve);
          const ui=NOXB1AbortSafeUI.createUiAdapter({container:chat,
            terminalTimeoutMs:1500,beforeCommit:async kind=>{
              if(kind==='terminal'&&++commits===1){entered=true;await gate;}
            }});
          const first=ui.upsertTerminal(s,'event-quick-stop',old.signal);
          for(let i=0;i<30&&!entered;i++) await Promise.resolve();
          if(!entered)return false;
          const second=ui.upsertTerminal(s,'event-quick-stop',fresh.signal);
          fresh.abort();
          const fast=await Promise.race([
            second,new Promise(resolve=>setTimeout(()=>resolve('HUNG'),250))
          ]);
          const beforeRelease=!Array.from(chat.children).some(
            x=>x.dataset.noxB1Exchange===s.exchange_id);
          release();
          const oldResult=await first;
          await new Promise(resolve=>setTimeout(resolve,0));
          const rows=Array.from(chat.children).filter(
            x=>x.dataset.noxB1Exchange===s.exchange_id);
          return fast===false&&beforeRelease&&oldResult===true&&
            commits===1&&rows.length===1&&
            rows[0].dataset.noxB1EventId==='event-quick-stop'&&
            rows[0].dataset.noxB1State==='terminal';
        }"""))
        check("two concurrent adapters serialize the same turn FIFO",page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'reattach-shared-fifo'};
          const ctrl=new AbortController();
          let unblock,entered=0;
          const gate=new Promise(resolve=>unblock=resolve);
          const firstUi=NOXB1AbortSafeUI.createUiAdapter({
            container:chat,beforeCommit:async kind=>{
              if(kind==='delta'){entered++;await gate;}
            }
          });
          const secondUi=NOXB1AbortSafeUI.createUiAdapter({container:chat});
          const a=firstUi.onDelta(s,'A',ctrl.signal);
          for(let i=0;i<20&&!entered;i++) await Promise.resolve();
          if(entered!==1)return false;
          const b=secondUi.onDelta(s,'B',ctrl.signal);
          for(let i=0;i<5;i++) await Promise.resolve();
          const premature=Array.from(chat.children).some(
            x=>x.dataset.noxB1Exchange===s.exchange_id);
          unblock();
          const results=await Promise.all([a,b]);
          const rows=Array.from(chat.children).filter(
            x=>x.dataset.noxB1Exchange===s.exchange_id);
          return !premature&&results.every(Boolean)&&rows.length===1&&
            rows[0].textContent==='AB';
        }"""))
        check("two concurrent adapters coalesce identical terminal projection",page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'reattach-shared-terminal'};
          const ctrl=new AbortController();
          let unblock,entered=0;
          const gate=new Promise(resolve=>unblock=resolve);
          const firstUi=NOXB1AbortSafeUI.createUiAdapter({
            container:chat,beforeCommit:async kind=>{
              if(kind==='terminal'){entered++;await gate;}
            }
          });
          const secondUi=NOXB1AbortSafeUI.createUiAdapter({container:chat});
          const a=firstUi.upsertTerminal(s,'canonical-event-shared',ctrl.signal);
          for(let i=0;i<20&&!entered;i++) await Promise.resolve();
          if(entered!==1)return false;
          const b=secondUi.upsertTerminal(s,'canonical-event-shared',ctrl.signal);
          const samePromise=a===b;
          unblock();
          const results=await Promise.all([a,b]);
          const rows=Array.from(chat.children).filter(
            x=>x.dataset.noxB1Exchange===s.exchange_id);
          return samePromise&&entered===1&&results.every(Boolean)&&
            rows.length===1&&rows[0].dataset.noxB1State==='terminal'&&
            rows[0].dataset.noxB1EventId==='canonical-event-shared';
        }"""))
        check("SSE Last-Event-ID replay coalesces identical deltas across adapters",page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'sse-id-replay'};
          const ctrl=new AbortController();
          let enter=0,release;
          const gate=new Promise(r=>release=r);
          const firstUi=NOXB1AbortSafeUI.createUiAdapter({
            container:chat,beforeCommit:async kind=>{
              if(kind==='delta'){enter++;await gate;}
            }
          });
          const secondUi=NOXB1AbortSafeUI.createUiAdapter({container:chat});
          const first=firstUi.onDelta(s,'A',ctrl.signal,'sse-101');
          for(let i=0;i<30&&!enter;i++) await Promise.resolve();
          if(enter!==1){release();return false;}
          const duplicate=secondUi.onDelta(s,'A',ctrl.signal,'sse-101');
          let conflict=false;
          try{await secondUi.onDelta(s,'EVIL',ctrl.signal,'sse-101');}
          catch(e){conflict=e.code==='HOLD_B1_UI_REPLAY_PAYLOAD';}
          release();
          const [one,two]=await Promise.all([first,duplicate]);
          const replay=await secondUi.onDelta(s,'A',ctrl.signal,'sse-101');
          const next=await secondUi.onDelta(s,'B',ctrl.signal,'sse-102');
          const rows=Array.from(chat.children).filter(
            x=>x.dataset.noxB1Exchange===s.exchange_id);
          return conflict&&one===true&&two===false&&replay===false&&
            next===true&&enter===1&&rows.length===1&&
            rows[0].textContent==='AB';
        }"""))
        check("aborted replay ID reservation permits fresh reconnect to render once",page.evaluate("""async()=>{
          const chat=document.querySelector('#chat');
          const s={conversation_id:'dialog',exchange_id:'sse-replay-after-stop'};
          const old=new AbortController(),fresh=new AbortController();
          let enter=0,release;
          const gate=new Promise(r=>release=r);
          const firstUi=NOXB1AbortSafeUI.createUiAdapter({
            container:chat,beforeCommit:async kind=>{
              if(kind==='delta'){enter++;await gate;}
            }
          });
          const secondUi=NOXB1AbortSafeUI.createUiAdapter({container:chat});
          const first=firstUi.onDelta(s,'SAFE',old.signal,'sse-201');
          for(let i=0;i<30&&!enter;i++) await Promise.resolve();
          if(enter!==1){release();return false;}
          const duplicate=secondUi.onDelta(s,'SAFE',fresh.signal,'sse-201');
          old.abort();
          const results=await Promise.race([
            Promise.all([first,duplicate]),
            new Promise(r=>setTimeout(()=>r('HUNG'),300))
          ]);
          release();
          const rows=Array.from(chat.children).filter(
            x=>x.dataset.noxB1Exchange===s.exchange_id);
          return Array.isArray(results)&&results[0]===false&&
            results[1]===true&&rows.length===1&&
            rows[0].textContent==='SAFE'&&enter===1;
        }"""))
        browser.close()
    print(f"B1 source-only real Chromium: {len(checks)}/{len(checks)} PASS")
    for name, _ in checks:
        print("PASS",name)

if __name__ == "__main__":
    main()
