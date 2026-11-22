#!/usr/bin/env python3
"""B1 source-only real-Chromium two-turn SSE/UI composition fixture.

Uses real B1 SSE, abort-safe adapter, and composition code; server, signer,
owner/ACK gate and S03 are synthetic. Never counts as native acceptance.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent


def main():
    checks = []

    def check(name, valid):
        checks.append(name)
        assert valid, name

    with sync_playwright() as p:
        # CI installs Playwright's pinned Chromium. Local machines may use the
        # system Chromium when the Playwright-managed binary is absent.
        # Never substitute JS fixtures: all three scripts below load from this
        # checked-out repository's exact files.
        launch = {'headless': True, 'args': ['--no-sandbox']}
        if not Path(p.chromium.executable_path).is_file() and Path('/usr/bin/chromium').is_file():
            launch['executable_path'] = '/usr/bin/chromium'
        browser = p.chromium.launch(**launch)
        page = browser.new_page()
        page.set_content('<main id="chat"></main>')
        for src in ('b1_abort_safe_ui_adapter.js', 'b1_client_stream_reconnect_harness.js', 'b1_sse_ui_binding.js'):
            page.add_script_tag(path=str(HERE / src))
        page.evaluate('''() => {
          // Synthetic trusted host only; no model request or actual S03.
          if(!crypto.randomUUID) Object.defineProperty(crypto,'randomUUID',
            {value:()=> 'nonce-'+Math.random().toString(36).slice(2)});
          const state=new Map(), seen={};
          window.metrics={posts:0,acks:0,readbacks:0,canonicalGets:0};
          window.s1={conversation_id:'dialog',exchange_id:'t1'};
          window.s2={conversation_id:'dialog',exchange_id:'t2'};
          window.current=()=>Array.from(document.querySelector('#chat').children)
            .map(e=>({c:e.dataset.noxB1Conversation,t:e.dataset.noxB1Exchange,
              state:e.dataset.noxB1State,text:e.textContent,id:e.dataset.noxB1EventId}));
          const packet=s => ({conversation_id:s.conversation_id,exchange_id:s.exchange_id});
          const transport={
            async post(s,signal){
              metrics.posts++;
              const frames=s.exchange_id==='t1'
                ?'event: delta\\ndata: Hello\\n\\nevent: delta\\ndata: LATE\\n\\n'
                :'event: delta\\ndata: Hola\\n\\n';
              return {ok:true,body:new ReadableStream({start(c){
                c.enqueue(new TextEncoder().encode(frames)); c.close();
              }})};
            },
            async readback(s){metrics.readbacks++; return packet(s);},
            async ack(s){metrics.acks++;return true;},
            async readCanonicalAck(s,expected,challenge){
              metrics.canonicalGets++;
              const now=Date.now();
              return {request_nonce:challenge.request_nonce,issued_at_ms:now,
                expires_at_ms:now+1000,ack_id:'ack-'+s.exchange_id};
            }
          };
          const host={
            async readCommitted(){return null;},
            async verifyFreshCanonicalAck(){return true;},
            async verifyCanonicalAck(){return true;}
          };
          const bridge={async acceptTerminal(packet,s){
            return {safe_to_ack:true,model_post:false,
              conversation_id:s.conversation_id,exchange_id:s.exchange_id,
              projection_event_id:'event-'+s.exchange_id,ack_cursor:'cursor-'+s.exchange_id};
          }};
          const ackGate={
            async reserve(s){
              const k=s.exchange_id;
              if(state.has(k)) return {status:'ALREADY_ACKED'};
              return {status:'RESERVED',key:k};
            },
            async beginSend(grant){state.set(grant.key,'SENDING');},
            async confirm(){throw Error('local confirm must not be used');},
            async requireCanonicalAck(s,event,cursor,read,verify){
              const expected={event_id:event,ack_cursor:cursor};
              const receipt=await read(expected);
              if(await verify(receipt,expected)!==true) throw Error('invalid proof');
              state.set(s.exchange_id,'ACKED');
              return {status:'CANONICAL_ACK_CONFIRMED',
                authority:'VERIFIER_CALLBACK_APPROVED',ack_id:receipt.ack_id};
            }
          };
          window.opts={container:document.querySelector('#chat'),transport,host,bridge,ackGate};
          window.gate={};
          window.opts.beforeCommit=async(kind,s)=>{
            if(kind==='delta'&&s.exchange_id==='t1'&&
              (seen.t1=(seen.t1||0)+1)===2){
              window.paused=true;
              await new Promise(resolve=>{window.release=resolve});
            }
          };
          window.client=NOXB1SseUiBinding.bind(window.opts);
        }''')
        check('actual DOM/SSE modules loaded', page.evaluate('''() =>
            typeof NOXB1AbortSafeUI.createUiAdapter==='function' &&
            typeof NOXB1StreamReconnect.createClient==='function' &&
            typeof NOXB1SseUiBinding.bind==='function' '''))
        check('bound API has only begin/stop/reconnect', page.evaluate('''() =>
            Object.keys(client).sort().join(',')==='begin,reconnect,stop' '''))
        page.evaluate('''() => { window.p1=client.begin(s1); }''')
        page.wait_for_function('window.paused===true')
        check('STOP cancels active first exchange', page.evaluate('()=>client.stop(s1)') is True)
        page.evaluate('()=>release()')
        check('first stream returns STOPPED', page.evaluate('()=>p1')=='STOPPED')
        check('first saved partial text survives STOP', page.evaluate('''() =>
            current().length===1 && current()[0].text==='Hello' '''))
        check('late frame never reaches DOM', page.evaluate('''() =>
            !current().some(e=>e.text.includes('LATE')) '''))
        check('same exchange cannot post twice', page.evaluate('''async()=>{
          try {await client.begin(s1);return false}
          catch(e){return e.code==='HOLD_STREAM_NO_REPOST'}
        }'''))
        check('first reconnect uses canonical readback', page.evaluate('''async()=>{
          const r=await client.reconnect(s1);
          return r.canonical_ack_status==='CANONICAL_ACK_CONFIRMED' &&
            current()[0].state==='terminal' && current()[0].id==='event-t1';
        }'''))
        check('second exchange begins without blocking first', page.evaluate('''async()=>{
          const r=await client.begin(s2);
          return r==='STREAM_ENDED_READBACK_REQUIRED' &&
            current().length===2 && current()[1].text==='Hola';
        }'''))
        check('second exchange independently confirms canonical readback', page.evaluate('''async()=>{
          const r=await client.reconnect(s2);
          return r.canonical_ack_status==='CANONICAL_ACK_CONFIRMED' &&
            current()[1].state==='terminal';
        }'''))
        check('repeat reconnect does not duplicate model POST or ACK', page.evaluate('''async()=>{
          const p=metrics.posts,a=metrics.acks;
          await Promise.all([client.reconnect(s1),client.reconnect(s1)]);
          return metrics.posts===p && metrics.acks===a &&
            metrics.canonicalGets>=3 && current().length===2;
        }'''))
        check('two distinct terminal events retained', page.evaluate('''() =>
          current()[0].id==='event-t1'&&current()[1].id==='event-t2' &&
          current()[0].c==='dialog'&&current()[1].c==='dialog' '''))
        check('two model POSTs and two ACKs in total', page.evaluate('''() =>
          metrics.posts===2 && metrics.acks===2 '''))
        check('ACK-less mounting is rejected before any IO', page.evaluate('''() => {
          const p=metrics.posts,a=metrics.acks;
          try{ NOXB1SseUiBinding.bind({...opts,ackGate:null});return false; }
          catch(e){return e.code==='HOLD_B1_BINDING_CANONICAL_ACK_GATE_REQUIRED'&&
            metrics.posts===p&&metrics.acks===a;}
        }'''))
        check('missing verifier is rejected before any IO', page.evaluate('''() => {
          try{ NOXB1SseUiBinding.bind({...opts,host:{}});return false; }
          catch(e){return e.code==='HOLD_B1_BINDING_TRUSTED_VERIFIER_REQUIRED';}
        }'''))
        check('DOM turn count remains exactly two', page.evaluate('()=>current().length===2'))

        # Reattachment can encounter an older, legacy terminal intent that
        # was started without AbortSignal. Fresh reconnect STOP must release
        # its own waiter immediately rather than inheriting the old 350ms
        # projection wait. The old projection is deliberately never released.
        check('fresh STOP releases waiter on legacy signal-less terminal', page.evaluate('''async () => {
          const container=document.createElement('section');
          const s={conversation_id:'legacy-terminal',exchange_id:'stop-new'};
          const beforePosts=metrics.posts,beforeAcks=metrics.acks;
          const ui=NOXB1AbortSafeUI.createUiAdapter({
            container,terminalTimeoutMs:350,
            beforeCommit:kind=>kind==='terminal'?new Promise(()=>{}):Promise.resolve()
          });
          const legacy=ui.upsertTerminal(s,'canonical-event');
          // Suppress the intentional old terminal timeout rejection.
          legacy.catch(()=>{});
          const signal=new AbortController();
          const fresh=ui.upsertTerminal(s,'canonical-event',signal.signal);
          signal.abort();
          const result=await Promise.race([
            fresh.then(v=>v,e=>e.code),
            new Promise(resolve=>setTimeout(()=>resolve('HUNG'),75))
          ]);
          return result===false && container.children.length===0 &&
            metrics.posts===beforePosts && metrics.acks===beforeAcks;
        }'''))
        # A legacy terminal precommit without AbortSignal can expire after a
        # fresh GET-only reconnect joins its pending intent. This is not an
        # unsafe precommit failure: allow one new projection of the exact same
        # canonical event after old timeout, without a second model POST/ACK.
        check('legacy terminal timeout allows fresh canonical reconnect', page.evaluate('''async () => {
          const container=document.createElement('section');
          const s={conversation_id:'legacy-terminal',exchange_id:'retry-timeout'};
          const beforePosts=metrics.posts,beforeAcks=metrics.acks;
          let terminals=0;
          const ui=NOXB1AbortSafeUI.createUiAdapter({
            container,terminalTimeoutMs:45,
            beforeCommit:kind=>{
              if(kind==='terminal'&&++terminals===1)
                return new Promise(()=>{});
              return Promise.resolve();
            }
          });
          const original=ui.upsertTerminal(s,'canonical-v1');
          const oldResult=original.then(()=>null,e=>e.code);
          const freshSignal=new AbortController();
          const fresh=ui.upsertTerminal(s,'canonical-v1',freshSignal.signal);
          const [oldCode,restored]=await Promise.race([
            Promise.all([oldResult,fresh]),
            new Promise(resolve=>setTimeout(()=>resolve(['HUNG',false]),450))
          ]);
          const row=container.firstElementChild;
          let conflicting;
          try{await ui.upsertTerminal(s,'canonical-v2',freshSignal.signal)}
          catch(e){conflicting=e.code}
          const repeated=await ui.upsertTerminal(s,'canonical-v1',freshSignal.signal);
          return oldCode==='HOLD_B1_UI_TERMINAL_TIMEOUT' &&
            restored===true && repeated===true && terminals===2 &&
            conflicting==='HOLD_B1_UI_CONFLICTING_TERMINAL' &&
            container.children.length===1 &&
            row.dataset.noxB1EventId==='canonical-v1' &&
            row.dataset.noxB1State==='terminal' &&
            metrics.posts===beforePosts && metrics.acks===beforeAcks;
        }'''))
        # Non-timeout UI errors remain a HOLD rather than automatically
        # replaying potentially unsafe side effects on reconnect.
        check('legacy terminal arbitrary precommit failure does not retry', page.evaluate('''async () => {
          const container=document.createElement('section');
          const s={conversation_id:'legacy-terminal',exchange_id:'unsafe-error'};
          let calls=0;
          const ui=NOXB1AbortSafeUI.createUiAdapter({
            container,terminalTimeoutMs:80,
            beforeCommit:()=>{
              calls++;
              throw Error('unsafe-beforeCommit');
            }
          });
          const old=ui.upsertTerminal(s,'canonical-v1').then(()=>null,e=>e.message);
          const fresh=ui.upsertTerminal(s,'canonical-v1',
            new AbortController().signal).then(()=>null,e=>e.message);
          const [a,b]=await Promise.all([old,fresh]);
          return a==='unsafe-beforeCommit' && b==='unsafe-beforeCommit' &&
            calls===1 && container.children.length===0;
        }'''))
        # Reproduce a real race in the abort-safe DOM adapter: a delta that
        # fails precommit after terminal intent is reserved must not prevent
        # the independently authenticated GET-only terminal from projecting.
        # No new model POST or network ACK is used in this synthetic check.
        check('failed delta does not poison later canonical terminal UI', page.evaluate('''async () => {
          const container=document.createElement('section');
          const s={conversation_id:'delta-rejected',exchange_id:'recovery'};
          const beforePosts=metrics.posts,beforeAcks=metrics.acks;
          let terminalHooks=0;
          const ui=NOXB1AbortSafeUI.createUiAdapter({
            container,
            beforeCommit:kind=>{
              if(kind==='delta') return Promise.reject(Error('delta-precommit-fail'));
              terminalHooks++;
              return Promise.resolve();
            }
          });
          const deltaSignal=new AbortController();
          const terminalSignal=new AbortController();
          const delta=ui.onDelta(s,'UNCOMMITTED',deltaSignal.signal,
            'delta-aborted').then(()=>null,e=>e.code);
          // Reserve the terminal while the older delta is still in flight.
          const terminal=ui.upsertTerminal(s,'durable-event',terminalSignal.signal);
          const outcomes=await Promise.allSettled([delta,terminal]);
          const row=container.firstElementChild;
          const repeated=await ui.upsertTerminal(s,'durable-event',terminalSignal.signal);
          return outcomes[0].status==='fulfilled' &&
            outcomes[0].value==='HOLD_B1_UI_PRECOMMIT' &&
            outcomes[1].status==='fulfilled' && outcomes[1].value===true &&
            repeated===true && terminalHooks===1 &&
            container.children.length===1 &&
            row.dataset.noxB1State==='terminal' &&
            row.dataset.noxB1EventId==='durable-event' &&
            row.textContent==='' &&
            metrics.posts===beforePosts && metrics.acks===beforeAcks;
        }'''))
        # A real Chromium caller must be able to select short B1 deadlines;
        # the previous binding silently dropped these values, leaving 30s
        # waits even when a host requested 25ms.
        check('bound UI forwards four independent reconnect deadlines', page.evaluate('''async () => {
          const cases=[
            {name:'readback',config:{reconnectReadTimeoutMs:25,
              transport:{...opts.transport,readback:()=>new Promise(()=>{})}},
              code:'HOLD_STREAM_READBACK_TIMEOUT'},
            {name:'projection',config:{uiProjectionTimeoutMs:25,
              beforeCommit:kind=>kind==='terminal'?
                new Promise(()=>{}):Promise.resolve()},
              code:'HOLD_STREAM_UI_PROJECTION_TIMEOUT'},
            {name:'acksend',config:{ackSendTimeoutMs:25,
              transport:{...opts.transport,ack:()=>new Promise(()=>{})}},
              code:'HOLD_STREAM_ACK_SEND_TIMEOUT'},
            {name:'canonical',config:{canonicalAckTimeoutMs:25,
              transport:{...opts.transport,
                readCanonicalAck:()=>new Promise(()=>{})}},
              code:'HOLD_STREAM_CANONICAL_ACK_TIMEOUT'}
          ];
          const beforePosts=metrics.posts;
          for(const t of cases){
            const c=NOXB1SseUiBinding.bind({...opts,...t.config});
            const s={conversation_id:'deadline',exchange_id:t.name};
            const started=Date.now();
            const result=await Promise.race([
              c.reconnect(s).then(()=>null,e=>e.code),
              new Promise(r=>setTimeout(()=>r('HUNG'),1200))
            ]);
            if(result!==t.code||Date.now()-started>1000) return false;
          }
          return metrics.posts===beforePosts;
        }'''))
        check('invalid bound reconnect deadlines fail before IO', page.evaluate('''() => {
          const beforePosts=metrics.posts;
          for(const name of ['reconnectReadTimeoutMs',
              'uiProjectionTimeoutMs','ackSendTimeoutMs',
              'canonicalAckTimeoutMs']){
            let code=null;
            try {NOXB1SseUiBinding.bind({...opts,[name]:0});}
            catch(e){code=e.code}
            if(code!=='HOLD_STREAM_HOST_CONTRACT')return false;
          }
          return metrics.posts===beforePosts;
        }'''))
        # Focused preflight race: a second begin must fail BEFORE the first
        # asynchronous committed-state read resolves, with only one POST.
        check('concurrent begin precheck sends exactly one model POST', page.evaluate('''async () => {
          const s={conversation_id:'race',exchange_id:'single'};
          let release,posts=0;
          const transport={...opts.transport,async post(){
            posts++;return {ok:true,body:new ReadableStream({start(c){c.close()}})};
          }};
          const host={...opts.host,readCommitted:()=>new Promise(r=>{release=r})};
          const ui={async onDelta(){},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:2000
          });
          const first=c.begin(s);
          const rejected=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          if(typeof release==='function') release(null);
          const result=await first;
          return rejected && result==='STREAM_ENDED_READBACK_REQUIRED' &&
            posts===1;
        }'''))
        check('STOP during pending precheck prevents late POST', page.evaluate('''async () => {
          const s={conversation_id:'race',exchange_id:'stop-preflight'};
          let release,posts=0;
          const host={...opts.host,readCommitted:()=>new Promise(r=>{release=r})};
          const transport={...opts.transport,async post(){posts++;return null}};
          const ui={async onDelta(){},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:2000
          });
          const pending=c.begin(s);
          await Promise.resolve();
          const stopped=c.stop(s);
          const result=await pending;
          if(typeof release==='function') release(null);
          return stopped===true && result==='STOPPED' && posts===0;
        }'''))
        check('timeout interrupts hung committed-state precheck', page.evaluate('''async () => {
          const s={conversation_id:'race',exchange_id:'timeout-preflight'};
          let posts=0;
          const host={...opts.host,readCommitted:()=>new Promise(()=>{})};
          const transport={...opts.transport,async post(){posts++;return null}};
          const ui={async onDelta(){},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:25
          });
          const result=await c.begin(s);
          return result==='STOPPED_TIMEOUT' && posts===0;
        }'''))
        # An uncooperative reader can leave read() and even cancel() pending.
        # STOP must settle promptly without waiting for either operation.
        check('STOP settles hung SSE reader without another POST or ACK', page.evaluate('''async () => {
          const s={conversation_id:'reader',exchange_id:'stop-hung'};
          let posts=0,acks=0,deltas=0;
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({
              pull(){return new Promise(()=>{})},
              cancel(){return new Promise(()=>{})}
            })};
          },async ack(){acks++;return true}};
          const host={...opts.host,async readCommitted(){return null}};
          const ui={async onDelta(){deltas++},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:2000
          });
          const pending=c.begin(s);
          for(let i=0;i<30&&!posts;i++) await new Promise(r=>setTimeout(r,0));
          if(posts!==1) return false;
          await new Promise(r=>setTimeout(r,0));
          const didStop=c.stop(s);
          const result=await Promise.race([
            pending,new Promise(r=>setTimeout(()=>r('HUNG'),350))
          ]);
          const rejected=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          return didStop===true && result==='STOPPED' && rejected &&
            posts===1 && acks===0 && deltas===0;
        }'''))
        check('timeout settles hung SSE reader without model repost', page.evaluate('''async () => {
          const s={conversation_id:'reader',exchange_id:'timeout-hung'};
          let posts=0,acks=0;
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({
              pull(){return new Promise(()=>{})}
            })};
          },async ack(){acks++;return true}};
          const host={...opts.host,async readCommitted(){return null}};
          const ui={async onDelta(){},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:30
          });
          const result=await Promise.race([
            c.begin(s),new Promise(r=>setTimeout(()=>r('HUNG'),500))
          ]);
          return result==='STOPPED_TIMEOUT' && posts===1 && acks===0;
        }'''))
        check('late reader resolution after STOP cannot write a delta', page.evaluate('''async () => {
          const s={conversation_id:'reader',exchange_id:'late-read'};
          let release,posts=0,deltas=0,acks=0;
          const reader={
            read(){return new Promise(r=>{release=r})},
            cancel(){return Promise.resolve()}
          };
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:{getReader(){return reader}}};
          },async ack(){acks++;return true}};
          const host={...opts.host,async readCommitted(){return null}};
          const ui={async onDelta(){deltas++},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:2000
          });
          const pending=c.begin(s);
          for(let i=0;i<30&&!release;i++) await new Promise(r=>setTimeout(r,0));
          if(!release) return false;
          const didStop=c.stop(s),result=await pending;
          release({done:false,value:new TextEncoder().encode(
            'event: delta\\ndata: LATE\\n\\n')});
          await new Promise(r=>setTimeout(r,0));
          return didStop===true && result==='STOPPED' &&
            posts===1 && acks===0 && deltas===0;
        }'''))
        check('wire SSE id replay coalesces one UI delta and rejects conflicts without ACK', page.evaluate('''async () => {
          const chat=document.querySelector('#chat');
          const s1={conversation_id:'id-wire',exchange_id:'same'};
          const s2={conversation_id:'id-wire',exchange_id:'conflict'};
          const s3={conversation_id:'id-wire',exchange_id:'malformed'};
          let posts=0,acks=0,commits=0;
          const transport={...opts.transport,
            async post(s){
              posts++;
              let frames;
              if(s.exchange_id==='same')
                frames='id: delta-001\\nevent: delta\\ndata: ONE\\n\\n' +
                  'id: delta-001\\nevent: delta\\ndata: ONE\\n\\n';
              else if(s.exchange_id==='conflict')
                frames='id: delta-002\\nevent: delta\\ndata: SAFE\\n\\n' +
                  'id: delta-002\\nevent: delta\\ndata: MUTATED\\n\\n';
              else frames='id: invalid!\\nevent: delta\\ndata: EVIL\\n\\n';
              return {ok:true,body:new ReadableStream({start(c){
                c.enqueue(new TextEncoder().encode(frames));c.close();
              }})};
            },
            async ack(){acks++;return true;}
          };
          const ui=NOXB1AbortSafeUI.createUiAdapter({container:chat,
            beforeCommit:async kind=>{if(kind==='delta') commits++;}});
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,timeoutMs:3000
          });
          const same=await c.begin(s1);
          const conflict=await c.begin(s2).then(()=>null,e=>e.code);
          const malformed=await c.begin(s3).then(()=>null,e=>e.code);
          const nodes=Array.from(chat.children).filter(
            e=>e.dataset.noxB1Conversation==='id-wire');
          const row=k=>nodes.find(e=>e.dataset.noxB1Exchange===k);
          return same==='STREAM_ENDED_READBACK_REQUIRED' &&
            conflict==='HOLD_STREAM_POST_OR_READ' &&
            malformed==='HOLD_STREAM_DELTA_EVENT_ID' &&
            posts===3 && acks===0 && commits===2 &&
            nodes.length===2 && row('same')?.textContent==='ONE' &&
            row('conflict')?.textContent==='SAFE' && !row('malformed');
        }'''))
        # SSE parsing allows ONE U+0020 after 'id:', never trimming the
        # actual identifier. Otherwise two distinct wire IDs can collapse
        # into a single replay token and silently suppress an SSE delta.
        check('SSE exact ID rejects whitespace aliases before DOM commit', page.evaluate('''async () => {
          const variants=[
            ['trailing','id: exact-001 '],
            ['double-leading','id:  exact-001'],
            ['tab-leading','id:\\texact-001'],
            ['canonical','id: exact-001']
          ];
          for(const [kind,wireId] of variants){
            const scope={conversation_id:'id-exact',exchange_id:kind};
            const container=document.createElement('section');
            let posts=0,acks=0,commits=0;
            const first='id: exact-001\\nevent: delta\\ndata: SAFE\\n\\n';
            const second=wireId+'\\nevent: delta\\ndata: MUTATED\\n\\n';
            const frames=first+(kind==='canonical'?'':second);
            const transport={...opts.transport,
              async post(){
                posts++;
                return {ok:true,body:new ReadableStream({start(c){
                  c.enqueue(new TextEncoder().encode(frames));c.close();
                }})};
              },
              async ack(){acks++;return true;}
            };
            const ui=NOXB1AbortSafeUI.createUiAdapter({
              container,beforeCommit:async type=>{
                if(type==='delta')commits++;
              }
            });
            const c=NOXB1StreamReconnect.createClient({
              transport,host:opts.host,bridge:opts.bridge,ui,timeoutMs:3000
            });
            const actual=await c.begin(scope).then(v=>v,e=>e.code);
            const expected=kind==='canonical'?
              'STREAM_ENDED_READBACK_REQUIRED':'HOLD_STREAM_DELTA_EVENT_ID';
            if(actual!==expected||posts!==1||acks!==0||commits!==1||
               container.children.length!==1||
               container.children[0].textContent!=='SAFE')return false;
          }
          return true;
        }'''))
        # A proxy may batch >64KiB of individually valid, small SSE frames
        # into ONE read(). Reject oversized individual frames, not large reads.
        # This is a source-only Chromium transport/DOM regression.
        check('one large read of small SSE frames preserves one turn', page.evaluate('''async () => {
          const s={conversation_id:'bulk-framing',exchange_id:'many-deltas'};
          const container=document.createElement('section');
          const payload='X'.repeat(780);
          const packed=Array.from({length:96},(_,i)=>
            'id: bulk-'+i+'\\nevent: delta\\ndata: '+payload+'\\n\\n').join('');
          let posts=0,acks=0;
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({start(c){
              c.enqueue(new TextEncoder().encode(packed));
              c.close();
            }})};
          },async ack(){acks++;return true;}};
          const ui=NOXB1AbortSafeUI.createUiAdapter({container});
          const client=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,timeoutMs:5000
          });
          const ended=await client.begin(s);
          const rejected=await client.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          return packed.length>65536 &&
            ended==='STREAM_ENDED_READBACK_REQUIRED' && rejected &&
            posts===1 && acks===0 &&
            container.children.length===1 &&
            container.firstElementChild.textContent===payload.repeat(96);
        }'''))
        check('one SSE frame over 64KiB still fails closed', page.evaluate('''async () => {
          const s={conversation_id:'bulk-framing',exchange_id:'oversized-frame'};
          const payload='X'.repeat(65537);
          const packed='id: huge\\nevent: delta\\ndata: '+payload+'\\n\\n';
          let posts=0,acks=0,deltas=0;
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({start(c){
              c.enqueue(new TextEncoder().encode(packed));c.close();
            }})};
          },async ack(){acks++;return true;}};
          const ui={async onDelta(){deltas++},async upsertTerminal(){return true}};
          const client=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,timeoutMs:5000
          });
          const code=await client.begin(s).then(()=>null,e=>e.code);
          return code==='HOLD_STREAM_FRAME_TOO_LARGE' &&
            posts===1 && acks===0 && deltas===0;
        }'''))
        # EventSource allows CR by itself as a line ending (HTML Living
        # Standard); split reads and EOF must not drop the final CR-only
        # empty line or accidentally create duplicate model turns.
        check('CR-only SSE events across one-byte reads and EOF keep one turn', page.evaluate('''async () => {
          const s={conversation_id:'cr-only',exchange_id:'two-deltas'};
          const wire='id: cr-one\\revent: delta\\rdata: FIRST\\r\\r' +
            'id: cr-two\\revent: delta\\rdata: SECOND\\r\\r';
          const deltas=[];
          let posts=0,acks=0;
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({start(c){
              for(const ch of wire) c.enqueue(new TextEncoder().encode(ch));
              c.close();
            }})};
          },async ack(){acks++;return true}};
          const ui={
            async onDelta(scope,data,signal,id){
              if(!signal.aborted) deltas.push([data,id]);
            },
            async upsertTerminal(){return true}
          };
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,timeoutMs:5000
          });
          const result=await c.begin(s);
          const duplicate=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          return result==='STREAM_ENDED_READBACK_REQUIRED' && duplicate &&
            posts===1 && acks===0 && deltas.length===2 &&
            deltas[0][0]==='FIRST' && deltas[0][1]==='cr-one' &&
            deltas[1][0]==='SECOND' && deltas[1][1]==='cr-two';
        }'''))
        # A CR-only blank line is a complete event BEFORE stream closure.
        # A hanging subsequent reader must not stall visible streaming tokens.
        check('CR-only SSE event is visible before EOF and STOP fences its turn', page.evaluate('''async () => {
          const s={conversation_id:'cr-only',exchange_id:'open-reader'};
          const frame='id: early\\revent: delta\\rdata: LIVE\\r\\r';
          let posts=0,acks=0,deltas=0,notify;
          const visible=new Promise(r=>{notify=r});
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({start(c){
              c.enqueue(new TextEncoder().encode(frame));
              // Intentionally do NOT close: must dispatch before EOF.
            }})};
          },async ack(){acks++;return true}};
          const ui={async onDelta(_s,data,signal,id){
            if(!signal.aborted&&data==='LIVE'&&id==='early'){
              deltas++;notify('VISIBLE');
            }
          },async upsertTerminal(){return true}};
          const client=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,timeoutMs:2000
          });
          const pending=client.begin(s);
          const first=await Promise.race([
            visible,new Promise(r=>setTimeout(()=>r('LATE'),300))
          ]);
          const stopped=client.stop(s);
          const result=await Promise.race([
            pending,new Promise(r=>setTimeout(()=>r('HUNG'),350))
          ]);
          const noRepost=await client.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          return first==='VISIBLE'&&stopped&&result==='STOPPED'&&
            noRepost&&posts===1&&acks===0&&deltas===1;
        }'''))
        check('CRLF split between chunks still emits one identified SSE delta', page.evaluate('''async () => {
          const s={conversation_id:'crlf-boundary',exchange_id:'one'};
          let posts=0,acks=0;
          const deltas=[];
          // Each byte gets its own stream chunk, placing every CR and LF in
          // different chunks, including the blank line closing the frame.
          const frame='id: event-123\\r\\nevent: delta\\r\\ndata: SPLIT\\r\\n\\r\\n';
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({start(c){
              for(const ch of frame) c.enqueue(new TextEncoder().encode(ch));
              c.close();
            }})};
          },async ack(){acks++;return true;}};
          const ui={
            async onDelta(scope,content,signal,eventId){
              if(!signal.aborted) deltas.push([content,eventId]);
            },
            async upsertTerminal(){return true;}
          };
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,timeoutMs:5000
          });
          const ended=await c.begin(s);
          const noRepost=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          return ended==='STREAM_ENDED_READBACK_REQUIRED' &&
            noRepost && posts===1 && acks===0 &&
            deltas.length===1 && deltas[0][0]==='SPLIT' &&
            deltas[0][1]==='event-123';
        }'''))
        # Strict incremental UTF-8 must reject an ill-formed complete sequence
        # and a truncated final sequence BEFORE a model token reaches the UI.
        # Recovery is GET-only; a rejected exchange must never be re-POSTed.
        check('invalid complete UTF-8 SSE event fails closed without repost', page.evaluate('''async () => {
          const s={conversation_id:'utf8-validation',exchange_id:'bad-complete'};
          const prefix=new TextEncoder().encode('id: invalid\\nevent: delta\\ndata: ');
          const suffix=new TextEncoder().encode('\\n\\n');
          const bytes=Uint8Array.from([...prefix,0xc3,0x28,...suffix]);
          let posts=0,acks=0,deltas=0;
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({start(c){
              c.enqueue(bytes);c.close();
            }})};
          },async ack(){acks++;return true}};
          const ui={async onDelta(){deltas++},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,timeoutMs:5000
          });
          const code=await c.begin(s).then(()=>null,e=>e.code);
          const noRepost=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          return code==='HOLD_STREAM_INVALID_UTF8' && noRepost &&
            posts===1 && acks===0 && deltas===0;
        }'''))
        check('truncated final UTF-8 SSE data holds before DOM commit', page.evaluate('''async () => {
          const s={conversation_id:'utf8-validation',exchange_id:'bad-final'};
          const prefix=new TextEncoder().encode('id: truncated\\nevent: delta\\ndata: ');
          let posts=0,acks=0,deltas=0;
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({start(c){
              c.enqueue(Uint8Array.from([...prefix,0xe2]));
              c.enqueue(Uint8Array.from([0x82])); // UTF-8 final byte missing
              c.close();
            }})};
          },async ack(){acks++;return true}};
          const ui={async onDelta(){deltas++},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,timeoutMs:5000
          });
          const code=await c.begin(s).then(()=>null,e=>e.code);
          const noRepost=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          return code==='HOLD_STREAM_INVALID_UTF8' && noRepost &&
            posts===1 && acks===0 && deltas===0;
        }'''))
        check('valid split multi-byte SSE delta still streams once', page.evaluate('''async () => {
          const s={conversation_id:'utf8-validation',exchange_id:'valid-split'};
          const prefix=new TextEncoder().encode('id: emoji\\nevent: delta\\ndata: ');
          const suffix=new TextEncoder().encode('\\n\\n');
          let posts=0,acks=0;
          const deltas=[];
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({start(c){
              c.enqueue(prefix);
              for(const byte of [0xf0,0x9f,0x98,0x80])
                c.enqueue(Uint8Array.from([byte]));
              c.enqueue(suffix);c.close();
            }})};
          },async ack(){acks++;return true}};
          const ui={async onDelta(scope,data,signal,id){
            if(!signal.aborted)deltas.push([data,id]);
          },async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,timeoutMs:5000
          });
          const done=await c.begin(s);
          const noRepost=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          return done==='STREAM_ENDED_READBACK_REQUIRED' && noRepost &&
            posts===1 && acks===0 && deltas.length===1 &&
            deltas[0][0]==='😀' && deltas[0][1]==='emoji';
        }'''))
        check('SSE preserves literal leading/trailing spaces in multi-line delta', page.evaluate('''async () => {
          const s={conversation_id:'literal-whitespace',exchange_id:'one'};
          let posts=0,acks=0;
          const deltas=[];
          // Literal payload spaces after the optional single separator must
          // survive CRLF, multiple data fields, and one-byte stream chunks.
          const frame='id: space-123\\r\\nevent: delta\\r\\n' +
            'data:  indented  \\r\\ndata:  spaced  \\r\\n\\r\\n';
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({start(c){
              for(const ch of frame) c.enqueue(new TextEncoder().encode(ch));
              c.close();
            }})};
          },async ack(){acks++;return true;}};
          const ui={
            async onDelta(scope,content,signal,eventId){
              if(!signal.aborted) deltas.push([content,eventId]);
            },
            async upsertTerminal(){return true;}
          };
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,timeoutMs:5000
          });
          const ended=await c.begin(s);
          const noRepost=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          return ended==='STREAM_ENDED_READBACK_REQUIRED' &&
            noRepost && posts===1 && acks===0 &&
            deltas.length===1 && deltas[0][0]===' indented  \\n spaced  ' &&
            deltas[0][1]==='space-123';
        }'''))
        check('STOP interrupts hung model POST without retry or late UI commit', page.evaluate('''async () => {
          const s={conversation_id:'hung-post',exchange_id:'stop-1'};
          let posts=0,acks=0,deltas=0,release;
          const transport={...opts.transport,
            post(){posts++;return new Promise(resolve=>{release=resolve});},
            async ack(){acks++;return true;}
          };
          const host={...opts.host,async readCommitted(){return null}};
          const ui={async onDelta(){deltas++},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:2000
          });
          const pending=c.begin(s);
          for(let i=0;i<30&&!release;i++) await new Promise(r=>setTimeout(r,0));
          if(posts!==1||typeof release!=='function') return false;
          const didStop=c.stop(s);
          const result=await Promise.race([
            pending,new Promise(r=>setTimeout(()=>r('HUNG'),350))
          ]);
          const noRepost=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          // Even if the transport later resolves, the stopped exchange must
          // not consume its body, project a delta or send an ACK.
          release({ok:true,body:{getReader(){deltas++;throw Error('LATE')}}});
          await new Promise(r=>setTimeout(r,0));
          return didStop===true && result==='STOPPED' && noRepost &&
            posts===1 && acks===0 && deltas===0;
        }'''))
        check('timeout interrupts hung model POST without retransmit', page.evaluate('''async () => {
          const s={conversation_id:'hung-post',exchange_id:'timeout-1'};
          let posts=0,acks=0,deltas=0;
          const transport={...opts.transport,
            post(){posts++;return new Promise(()=>{})},
            async ack(){acks++;return true;}
          };
          const host={...opts.host,async readCommitted(){return null}};
          const ui={async onDelta(){deltas++},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:30
          });
          const result=await Promise.race([
            c.begin(s),new Promise(r=>setTimeout(()=>r('HUNG'),500))
          ]);
          const noRepost=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          return result==='STOPPED_TIMEOUT' && noRepost &&
            posts===1 && acks===0 && deltas===0;
        }'''))
        check('STOP settles hung UI delta without later frame or repost', page.evaluate('''async () => {
          const s={conversation_id:'ui-stall',exchange_id:'stop-delta'};
          let posts=0,acks=0,calls=0,lateCommits=0,release;
          const frame='id: delta-ui-1\\nevent: delta\\ndata: WAIT\\n\\n' +
            'id: delta-ui-2\\nevent: delta\\ndata: NEVER\\n\\n';
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({start(c){
              c.enqueue(new TextEncoder().encode(frame));c.close();
            }})};
          },async ack(){acks++;return true;}};
          const host={...opts.host,async readCommitted(){return null}};
          const ui={
            onDelta(_s,_content,signal){
              calls++;
              return new Promise(resolve=>{
                release=()=>{if(!signal.aborted)lateCommits++;resolve();};
              });
            },
            async upsertTerminal(){throw Error('NO_TERMINAL')}
          };
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:2000
          });
          const pending=c.begin(s);
          for(let i=0;i<40&&!release;i++) await new Promise(r=>setTimeout(r,0));
          if(posts!==1||typeof release!=='function'||calls!==1) return false;
          const didStop=c.stop(s);
          const outcome=await Promise.race([
            pending,new Promise(r=>setTimeout(()=>r('HUNG'),350))
          ]);
          release();
          await new Promise(r=>setTimeout(r,0));
          const noRepost=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          return didStop===true&&outcome==='STOPPED'&&noRepost&&
            posts===1&&acks===0&&calls===1&&lateCommits===0;
        }'''))
        check('timeout settles hung UI delta without duplicate model POST', page.evaluate('''async () => {
          const s={conversation_id:'ui-stall',exchange_id:'timeout-delta'};
          let posts=0,acks=0,calls=0;
          const frame='id: delta-time\\nevent: delta\\ndata: WAIT\\n\\n';
          const transport={...opts.transport,async post(){
            posts++;
            return {ok:true,body:new ReadableStream({start(c){
              c.enqueue(new TextEncoder().encode(frame));c.close();
            }})};
          },async ack(){acks++;return true;}};
          const host={...opts.host,async readCommitted(){return null}};
          const ui={onDelta(){calls++;return new Promise(()=>{})},
            async upsertTerminal(){throw Error('NO_TERMINAL')}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:40
          });
          const outcome=await Promise.race([
            c.begin(s),new Promise(r=>setTimeout(()=>r('HUNG'),450))
          ]);
          const noRepost=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          return outcome==='STOPPED_TIMEOUT'&&noRepost&&
            posts===1&&acks===0&&calls===1;
        }'''))
        check('hung reconnect GET times out and retry stays GET-only', page.evaluate('''async () => {
          const s={conversation_id:'reconnect-deadline',exchange_id:'get-hung'};
          let reads=0,posts=0,acks=0,projections=0,late;
          const transport={...opts.transport,
            post(){posts++;throw Error('NO_MODEL_POST')},
            readback(){
              reads++;
              if(reads===1)return new Promise(resolve=>{late=resolve});
              return Promise.resolve({conversation_id:s.conversation_id,
                exchange_id:s.exchange_id});
            },
            async ack(){acks++;return true}
          };
          const ui={async onDelta(){},
            async upsertTerminal(){projections++;return true;}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,
            reconnectReadTimeoutMs:30
          });
          const first=await Promise.race([
            c.reconnect(s).then(()=>null,e=>e.code),
            new Promise(r=>setTimeout(()=>r('HUNG'),400))
          ]);
          if(first!=='HOLD_STREAM_READBACK_TIMEOUT'||reads!==1||
             posts!==0||acks!==0||projections!==0)return false;
          const recovered=await c.reconnect(s);
          late({conversation_id:s.conversation_id,exchange_id:s.exchange_id});
          await new Promise(r=>setTimeout(r,0));
          return recovered.safe_to_ack===true&&reads===2&&
            posts===0&&acks===1&&projections===1;
        }'''))
        check('late witness after timeout cannot project or ACK', page.evaluate('''async () => {
          const s={conversation_id:'reconnect-deadline',exchange_id:'witness-hung'};
          let posts=0,reads=0,acks=0,projects=0,calls=0,late;
          const transport={...opts.transport,
            post(){posts++;throw Error('NO_MODEL_POST')},
            readback(){reads++;return Promise.resolve({conversation_id:s.conversation_id,
              exchange_id:s.exchange_id});},
            async ack(){acks++;return true}
          };
          const bridge={acceptTerminal(){
            calls++;
            const witness={safe_to_ack:true,model_post:false,
              conversation_id:s.conversation_id,exchange_id:s.exchange_id,
              projection_event_id:'event-witness',ack_cursor:'cursor-witness'};
            if(calls===1)return new Promise(resolve=>{late=()=>resolve(witness)});
            return Promise.resolve(witness);
          }};
          const ui={async onDelta(){},
            async upsertTerminal(){projects++;return true;}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge,ui,reconnectReadTimeoutMs:30
          });
          const first=await Promise.race([
            c.reconnect(s).then(()=>null,e=>e.code),
            new Promise(r=>setTimeout(()=>r('HUNG'),400))
          ]);
          if(first!=='HOLD_STREAM_WITNESS_TIMEOUT'||calls!==1||
             posts!==0||acks!==0||projects!==0)return false;
          const recovered=await c.reconnect(s);
          late();
          await new Promise(r=>setTimeout(r,0));
          return recovered.safe_to_ack===true&&calls===2&&reads===2&&
            posts===0&&acks===1&&projects===1;
        }'''))
        check('hung ACK send times out and uncertain retry stays canonical GET only', page.evaluate('''async () => {
          const s={conversation_id:'ack-stall',exchange_id:'send-pending'};
          let stage='NEW',posts=0,reads=0,projects=0,acks=0,release;
          const uncertain=code=>Object.assign(new Error(code),{code});
          const transport={...opts.transport,
            post(){posts++;throw Error('MODEL_POST_FORBIDDEN')},
            async readback(){reads++;return {...s}},
            ack(){acks++;return new Promise(resolve=>{release=resolve})}
          };
          const gate={
            async reserve(){
              if(stage==='SENDING') throw uncertain('HOLD_CROSSTAB_ACK_UNCERTAIN');
              return {status:'RESERVED',key:s.exchange_id};
            },
            async beginSend(){stage='SENDING'},
            async confirm(){throw Error('NO_LOCAL_CONFIRM')},
            async requireCanonicalAck(){
              throw uncertain('HOLD_STREAM_ACK_UNCERTAIN_GET_ONLY');
            }
          };
          const ui={
            async onDelta(){},
            async upsertTerminal(){projects++;return true}
          };
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,ackGate:gate,
            reconnectReadTimeoutMs:150,ackSendTimeoutMs:25
          });
          const first=await Promise.race([
            c.reconnect(s).then(()=>null,e=>e.code),
            new Promise(resolve=>setTimeout(()=>resolve('HUNG'),400))
          ]);
          if(first!=='HOLD_STREAM_ACK_SEND_TIMEOUT'||stage!=='SENDING'||
             posts!==0||reads!==1||acks!==1||projects!==1)return false;
          const second=await c.reconnect(s).then(()=>null,e=>e.code);
          if(typeof release!=='function')return false;
          release(true); // late server ACK result cannot resume or resend
          await new Promise(resolve=>setTimeout(resolve,0));
          return second==='HOLD_STREAM_ACK_UNCERTAIN_GET_ONLY'&&
            stage==='SENDING'&&posts===0&&reads===2&&acks===1;
        }'''))
        check('hung UI terminal projection times out without ACK or model repost', page.evaluate('''async () => {
          const s={conversation_id:'projection-stall',exchange_id:'terminal-once'};
          let posts=0,reads=0,acks=0,projects=0,release;
          const ids=[];
          const transport={...opts.transport,
            post(){posts++;throw Error('MODEL_POST_FORBIDDEN')},
            async readback(){reads++;return {...s}},
            async ack(){acks++;return true}
          };
          const ui={
            async onDelta(){},
            upsertTerminal(_s,eventId){
              ids.push(eventId);
              projects++;
              if(projects===1)
                return new Promise(resolve=>{release=resolve});
              return Promise.resolve(true);
            }
          };
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,
            uiProjectionTimeoutMs:25
          });
          const first=await Promise.race([
            c.reconnect(s).then(()=>null,e=>e.code),
            new Promise(resolve=>setTimeout(()=>resolve('HUNG'),400))
          ]);
          if(first!=='HOLD_STREAM_UI_PROJECTION_TIMEOUT'||
             posts!==0||reads!==1||acks!==0||projects!==1||
             typeof release!=='function')return false;
          const second=await c.reconnect(s);
          release(true); // Late result must not resume the timed-out ACK path.
          await new Promise(resolve=>setTimeout(resolve,0));
          return second.safe_to_ack===true&&reads===2&&
            posts===0&&acks===1&&projects===2&&
            ids.length===2&&ids[0]===ids[1];
        }'''))
        check('reconnect timeout aborts real adapter late DOM commit; GET-only retry succeeds', page.evaluate('''async () => {
          const s={conversation_id:'projection-abort',exchange_id:'late-dom-fence'};
          const container=document.createElement('main');
          document.body.appendChild(container);
          let release,precommits=0,posts=0,reads=0,acks=0;
          const ui=NOXB1AbortSafeUI.createUiAdapter({
            container,terminalTimeoutMs:1000,
            beforeCommit(kind){
              if(kind==='terminal'&&++precommits===1)
                return new Promise(resolve=>{release=resolve});
            }
          });
          const transport={...opts.transport,
            post(){posts++;throw Error('NO_REPOST')},
            async readback(){reads++;return {...s}},
            async ack(){acks++;return true}
          };
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,
            uiProjectionTimeoutMs:30
          });
          const first=await Promise.race([
            c.reconnect(s).then(()=>null,e=>e.code),
            new Promise(resolve=>setTimeout(()=>resolve('HUNG'),400))
          ]);
          if(first!=='HOLD_STREAM_UI_PROJECTION_TIMEOUT'||
             typeof release!=='function'||posts!==0||acks!==0||
             reads!==1||container.children.length!==0)return false;
          // The old harness returned HOLD but failed to abort the adapter;
          // settling its late beforeCommit then created a terminal DOM row.
          release();
          await new Promise(resolve=>setTimeout(resolve,0));
          if(container.children.length!==0||acks!==0)return false;
          const second=await c.reconnect(s);
          const row=container.firstElementChild;
          return second.safe_to_ack===true&&posts===0&&acks===1&&
            reads===2&&precommits===2&&container.children.length===1&&
            row.dataset.noxB1State==='terminal'&&
            row.dataset.noxB1EventId==='event-late-dom-fence';
        }'''))
        check('terminal UI projection requires literal true before any ACK', page.evaluate('''async () => {
          const s={conversation_id:'projection-contract',exchange_id:'strict-confirm'};
          const projections=[undefined,null,false,0,'ok',true];
          let posts=0,reads=0,acks=0,projected=0;
          const eventIds=[];
          const transport={...opts.transport,
            post(){posts++;throw Error('NO_MODEL_POST')},
            async readback(){reads++;return {...s}},
            async ack(){acks++;return true}
          };
          const ui={async onDelta(){},
            async upsertTerminal(_s,eventId){
              projected++;eventIds.push(eventId);
              return projections.shift();
            }
          };
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui
          });
          for(let i=0;i<5;i++){
            const code=await c.reconnect(s).then(()=>null,e=>e.code);
            if(code!=='HOLD_STREAM_UI_NOT_CONFIRMED'||
               posts!==0||acks!==0||reads!==i+1||projected!==i+1)
              return false;
          }
          const witness=await c.reconnect(s);
          return witness.safe_to_ack===true &&
            reads===6&&projected===6&&acks===1&&posts===0&&
            new Set(eventIds).size===1;
        }'''))
        check('canonical ACK GET and verifier stalls time out; retries remain GET-only', page.evaluate('''async () => {
          const s={conversation_id:'canonical-stall',exchange_id:'read-verify'};
          let posts=0,acks=0,reads=0,projects=0,gets=0,freshCalls=0;
          let releaseGet,releaseVerifier;
          const mint=challenge=>{
            const now=Date.now();
            return {request_nonce:challenge.request_nonce,issued_at_ms:now,
              expires_at_ms:now+1000,ack_id:'canonical-confirmed'};
          };
          const transport={...opts.transport,
            post(){posts++;throw Error('NO_MODEL_POST')},
            async readback(){reads++;return {...s}},
            async ack(){acks++;throw Error('NO_ACK_RESEND')},
            readCanonicalAck(_s,_expected,challenge){
              gets++;
              if(gets===1)
                return new Promise(resolve=>{releaseGet=()=>resolve(mint(challenge))});
              return Promise.resolve(mint(challenge));
            }
          };
          const host={...opts.host,
            verifyFreshCanonicalAck(){
              freshCalls++;
              if(freshCalls===1)
                return new Promise(resolve=>{releaseVerifier=resolve});
              return true;
            }
          };
          const gate={
            async reserve(){return {status:'ALREADY_ACKED'}},
            async beginSend(){throw Error('NO_NEW_ACK')},
            async confirm(){throw Error('NO_LOCAL_ACK')},
            async requireCanonicalAck(_s,eventId,cursor,read,verify){
              const expected={event_id:eventId,ack_cursor:cursor};
              const receipt=await read(expected);
              if(await verify(receipt,expected)!==true)throw Error('BAD_ACK_PROOF');
              return {status:'CANONICAL_ACK_CONFIRMED',
                authority:'VERIFIER_CALLBACK_APPROVED',ack_id:receipt.ack_id};
            }
          };
          const eventIds=[];
          const ui={async onDelta(){},async upsertTerminal(_s,eventId){
            projects++;eventIds.push(eventId);return true;
          }};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,ackGate:gate,
            canonicalAckTimeoutMs:25
          });
          const result=()=>Promise.race([
            c.reconnect(s).then(()=>null,e=>e.code),
            new Promise(resolve=>setTimeout(()=>resolve('HUNG'),400))
          ]);
          const one=await result();
          if(one!=='HOLD_STREAM_CANONICAL_ACK_TIMEOUT'||
             gets!==1||posts!==0||acks!==0||projects!==1||
             typeof releaseGet!=='function')return false;
          const two=await result();
          if(two!=='HOLD_STREAM_CANONICAL_ACK_TIMEOUT'||
             gets!==2||freshCalls!==1||posts!==0||acks!==0||
             typeof releaseVerifier!=='function')return false;
          const recovered=await c.reconnect(s);
          if(recovered.canonical_ack_status!=='CANONICAL_ACK_CONFIRMED'||
             reads!==3||projects!==3||gets!==3||posts!==0||acks!==0||
             new Set(eventIds).size!==1)return false;
          // Late GET/verifier settlement must not resume a timed-out path or
          // trigger a model POST / network ACK after a successful GET retry.
          releaseGet();
          releaseVerifier(true);
          await new Promise(resolve=>setTimeout(resolve,0));
          return reads===3&&projects===3&&gets===3&&posts===0&&acks===0;
        }'''))
        check('STOP during hung reconnect GET settles promptly, late GET cannot ACK', page.evaluate('''async () => {
          const s={conversation_id:'stop-reconnect',exchange_id:'hung-get'};
          let release,reads=0,posts=0,projects=0,acks=0;
          const transport={...opts.transport,
            post(){posts++;throw Error('NO_MODEL_POST')},
            readback(){
              reads++;
              if(reads===1)return new Promise(resolve=>{release=resolve});
              return Promise.resolve({...s});
            },
            async ack(){acks++;return true}
          };
          const ui={async onDelta(){},async upsertTerminal(){projects++;return true;}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,
            reconnectReadTimeoutMs:3000
          });
          const first=c.reconnect(s);
          for(let i=0;i<30&&!release;i++) await new Promise(r=>setTimeout(r,0));
          if(typeof release!=='function')return false;
          const stopped=c.stop(s);
          const code=await Promise.race([
            first.then(()=>null,e=>e.code),
            new Promise(r=>setTimeout(()=>r('HUNG'),400))
          ]);
          release({...s}); // stale GET must not project or ACK.
          await new Promise(r=>setTimeout(r,0));
          if(stopped!==true||code!=='HOLD_STREAM_RECONNECT_STOPPED'||
             posts!==0||projects!==0||acks!==0)return false;
          const recovered=await c.reconnect(s);
          return recovered.safe_to_ack===true&&reads===2&&posts===0&&
            projects===1&&acks===1&&c.stop(s)===false;
        }'''))
        check('STOP aborts late terminal DOM projection and never sends ACK', page.evaluate('''async () => {
          const s={conversation_id:'stop-reconnect',exchange_id:'hung-ui'};
          const container=document.createElement('main');
          document.body.appendChild(container);
          let release,precommits=0,posts=0,reads=0,acks=0;
          const ui=NOXB1AbortSafeUI.createUiAdapter({
            container,terminalTimeoutMs:3000,
            beforeCommit(kind){
              if(kind==='terminal'&&++precommits===1)
                return new Promise(resolve=>{release=resolve});
            }
          });
          const transport={...opts.transport,
            post(){posts++;throw Error('NO_MODEL_POST')},
            async readback(){reads++;return {...s}},
            async ack(){acks++;return true}
          };
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,
            uiProjectionTimeoutMs:3000
          });
          const first=c.reconnect(s);
          for(let i=0;i<30&&!release;i++) await new Promise(r=>setTimeout(r,0));
          if(typeof release!=='function')return false;
          const stopped=c.stop(s);
          const code=await Promise.race([
            first.then(()=>null,e=>e.code),
            new Promise(r=>setTimeout(()=>r('HUNG'),400))
          ]);
          release(); // delayed beforeCommit cannot mutate after scoped STOP.
          await new Promise(r=>setTimeout(r,0));
          if(stopped!==true||code!=='HOLD_STREAM_RECONNECT_STOPPED'||
             container.children.length!==0||acks!==0||posts!==0)return false;
          const recovered=await c.reconnect(s);
          return recovered.safe_to_ack===true&&reads===2&&
            precommits===2&&container.children.length===1&&
            posts===0&&acks===1;
        }'''))
        check('reconnect ownership fences duplicate begin during GET and after STOP', page.evaluate('''async () => {
          const s={conversation_id:'reconnect-begin-fence',exchange_id:'one'};
          let release,reads=0,posts=0,acks=0;
          const transport={...opts.transport,
            async post(){posts++;throw Error('DUPLICATE_MODEL_POST')},
            readback(){
              reads++;
              if(reads===1)return new Promise(resolve=>{release=resolve});
              return Promise.resolve({...s});
            },
            async ack(){acks++;return true}
          };
          const ui={async onDelta(){},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,
            reconnectReadTimeoutMs:3000
          });
          const pending=c.reconnect(s);
          for(let i=0;i<30&&!release;i++)await new Promise(r=>setTimeout(r,0));
          if(typeof release!=='function')return false;
          // Old code accepted begin() here if readCommitted() returned null,
          // causing a second model POST for the same ambiguous exchange.
          const beforeStop=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          const stopped=c.stop(s);
          const status=await Promise.race([
            pending.then(()=>null,e=>e.code),
            new Promise(r=>setTimeout(()=>r('HUNG'),400))
          ]);
          const afterStop=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          release({...s}); // stale GET must not ACK.
          await new Promise(r=>setTimeout(r,0));
          if(!beforeStop||!afterStop||!stopped||
             status!=='HOLD_STREAM_RECONNECT_STOPPED'||
             posts!==0||acks!==0)return false;
          const restored=await c.reconnect(s);
          return restored.safe_to_ack===true&&reads===2&&
            posts===0&&acks===1;
        }'''))
        check('STOP and timeout abort underlying read-only reconnect GET', page.evaluate('''async () => {
          const stopScope={conversation_id:'get-abort',exchange_id:'stop'};
          const timeoutScope={conversation_id:'get-abort',exchange_id:'deadline'};
          let reads=0,posts=0,acks=0,projects=0;
          const aborted={};
          const transport={...opts.transport,
            post(){posts++;throw Error('NO_MODEL_POST')},
            readback(s,signal){
              reads++;
              // Old harness passed no signal: it released the UI wait but
              // left the underlying HTTP GET alive after STOP/deadline.
              if(!signal||typeof signal.addEventListener!=='function')
                return new Promise(()=>{});
              return new Promise(resolve=>{
                signal.addEventListener('abort',()=>{
                  aborted[s.exchange_id]=(aborted[s.exchange_id]||0)+1;
                  // Even a transport resolving late cannot project or ACK.
                  setTimeout(()=>resolve({...s}),0);
                },{once:true});
              });
            },
            ack(){acks++;return true}
          };
          const ui={async onDelta(){},async upsertTerminal(){projects++;return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host:opts.host,bridge:opts.bridge,ui,
            reconnectReadTimeoutMs:45
          });
          const first=c.reconnect(stopScope);
          for(let i=0;i<30&&reads<1;i++)await new Promise(r=>setTimeout(r,0));
          if(reads!==1)return false;
          const didStop=c.stop(stopScope);
          const stopped=await Promise.race([
            first.then(()=>null,e=>e.code),
            new Promise(r=>setTimeout(()=>r('HUNG'),400))
          ]);
          const timedOut=await Promise.race([
            c.reconnect(timeoutScope).then(()=>null,e=>e.code),
            new Promise(r=>setTimeout(()=>r('HUNG'),400))
          ]);
          await new Promise(r=>setTimeout(r,0));
          return didStop===true &&
            stopped==='HOLD_STREAM_RECONNECT_STOPPED' &&
            timedOut==='HOLD_STREAM_READBACK_TIMEOUT' &&
            aborted.stop===1 && aborted.deadline===1 &&
            reads===2&&posts===0&&acks===0&&projects===0;
        }'''))
        check('STOP/timeout abort canonical ACK GET and fence late gate completion', page.evaluate('''async () => {
          async function one(kind){
            const s={conversation_id:'canonical-abort',exchange_id:kind};
            let posts=0,acks=0,gets=0,confirmed=0,verifications=0;
            let release,readSignal;
            const mint=challenge=>{
              const now=Date.now();
              return {request_nonce:challenge.request_nonce,issued_at_ms:now,
                expires_at_ms:now+1000,ack_id:'ack-'+kind};
            };
            const transport={...opts.transport,
              post(){posts++;throw Error('NO_MODEL_POST')},
              async readback(){return {...s}},
              ack(){acks++;throw Error('NO_DUPLICATE_ACK')},
              readCanonicalAck(_s,_expected,challenge,signal){
                gets++;
                if(gets===1){
                  readSignal=signal;
                  return new Promise(resolve=>{
                    release=()=>resolve(mint(challenge));
                  });
                }
                return Promise.resolve(mint(challenge));
              }
            };
            const host={...opts.host,
              async verifyFreshCanonicalAck(){verifications++;return true}
            };
            const gate={
              async reserve(){return {status:'ALREADY_ACKED'}},
              async beginSend(){throw Error('NO_NEW_ACK')},
              async confirm(){throw Error('NO_LOCAL_ACK')},
              async requireCanonicalAck(_s,event,cursor,read,verify){
                const expected={event_id:event,ack_cursor:cursor};
                const receipt=await read(expected);
                if(await verify(receipt,expected)!==true)
                  throw Error('BAD_VERIFIER');
                confirmed++;
                return {status:'CANONICAL_ACK_CONFIRMED',
                  authority:'VERIFIER_CALLBACK_APPROVED',ack_id:receipt.ack_id};
              }
            };
            const ui={async onDelta(){},async upsertTerminal(){return true}};
            const c=NOXB1StreamReconnect.createClient({
              transport,host,bridge:opts.bridge,ui,ackGate:gate,
              canonicalAckTimeoutMs:35
            });
            const pending=c.reconnect(s);
            for(let i=0;i<50&&!release;i++)
              await new Promise(r=>setTimeout(r,0));
            if(!release||!readSignal)return false;
            const didStop=kind==='stop'?c.stop(s):false;
            const code=await Promise.race([
              pending.then(()=>null,e=>e.code),
              new Promise(r=>setTimeout(()=>r('HUNG'),450))
            ]);
            if((kind==='stop'&&(!didStop||
                code!=='HOLD_STREAM_RECONNECT_STOPPED'))||
               (kind==='timeout'&&code!=='HOLD_STREAM_CANONICAL_ACK_TIMEOUT')||
               !readSignal.aborted)return false;
            // Even a transport ignoring AbortSignal and resolving later must
            // not pass the receipt to an ACK gate after stop/deadline.
            release();
            await new Promise(r=>setTimeout(r,0));
            if(confirmed!==0||verifications!==0||posts!==0||acks!==0)
              return false;
            const restored=await c.reconnect(s);
            return restored.canonical_ack_status==='CANONICAL_ACK_CONFIRMED' &&
              gets===2&&confirmed===1&&verifications===1&&
              posts===0&&acks===0;
          }
          return await one('stop') && await one('timeout');
        }'''))
        # The composition binding must forward the UI adapter's own deadlines:
        # otherwise a hung beforeCommit waits 30s despite a host's 30ms budget.
        check('bound UI adapter deadlines stop hung delta and terminal projection', page.evaluate('''async () => {
          let posts=0,acks=0;
          const afterPosts=metrics.posts;
          const container=document.createElement('div');
          const scope={conversation_id:'ui-deadlines',exchange_id:'delta'};
          const deltaTransport={...opts.transport,
            async post(){
              posts++;
              return {ok:true,body:new ReadableStream({start(c){
                c.enqueue(new TextEncoder().encode(
                  'event: delta\\ndata: HELLO\\n\\n'));c.close();
              }})};
            },
            async ack(){acks++;return true;}
          };
          const dc=NOXB1SseUiBinding.bind({
            ...opts,container,transport:deltaTransport,
            deltaPrecommitTimeoutMs:35,timeoutMs:1000,
            beforeCommit:kind=>kind==='delta'?
              new Promise(()=>{}):Promise.resolve()
          });
          const firstStarted=Date.now();
          const first=await Promise.race([
            dc.begin(scope).then(()=>null,e=>e.code),
            new Promise(r=>setTimeout(()=>r('HUNG'),900))
          ]);
          if(first!=='HOLD_STREAM_POST_OR_READ'||
             Date.now()-firstStarted>800||posts!==1||acks!==0||
             container.children.length!==0)return false;
          const secondScope={conversation_id:'ui-deadlines',exchange_id:'terminal'};
          const tc=NOXB1SseUiBinding.bind({
            ...opts,container,transport:{...opts.transport,
              post(){posts++;throw Error('NO_SECOND_MODEL_POST')},
              ack(){acks++;return true}},
            terminalTimeoutMs:35,uiProjectionTimeoutMs:1000,
            beforeCommit:kind=>kind==='terminal'?
              new Promise(()=>{}):Promise.resolve()
          });
          const secondStarted=Date.now();
          const second=await Promise.race([
            tc.reconnect(secondScope).then(()=>null,e=>e.code),
            new Promise(r=>setTimeout(()=>r('HUNG'),900))
          ]);
          if(second!=='HOLD_STREAM_UI_PROJECTION'||
             Date.now()-secondStarted>800||posts!==1||acks!==0||
             container.children.length!==0)return false;
          for(const option of ['terminalTimeoutMs','deltaPrecommitTimeoutMs']){
            let error=null;
            try{NOXB1SseUiBinding.bind({...opts,[option]:0});}
            catch(e){error=e.code}
            if(error!=='HOLD_B1_UI_CONTRACT')return false;
          }
          return metrics.posts===afterPosts&&posts===1&&acks===0;
        }'''))
        # An SSE reader must be cancelled when STOP races a hung UI delta,
        # or a malformed stream is held. A clean EOF must not be cancelled.
        # This is source-only Chromium; no live model/ACK/S03 operations.
        check('STOP and malformed SSE release reader; normal EOF does not', page.evaluate('''async () => {
          async function one(kind){
            const s={conversation_id:'reader-finally',exchange_id:kind};
            let posts=0,acks=0,cancels=0,deltas=0,notify;
            const entered=new Promise(resolve=>{notify=resolve});
            const bytes=kind==='invalid'
              ?new Uint8Array([0xc3,0x28])
              :new TextEncoder().encode(
                'event: delta\\nid: frame-1\\ndata: Hello\\n\\n');
            const stream=new ReadableStream({
              start(controller){
                controller.enqueue(bytes);
                if(kind==='complete')controller.close();
              },
              cancel(){cancels++;}
            });
            const transport={...opts.transport,
              async post(){posts++;return {ok:true,body:stream}},
              async ack(){acks++;return true}
            };
            const ui={
              onDelta(){
                deltas++;notify();
                if(kind==='stop')return new Promise(()=>{});
                return Promise.resolve();
              },
              async upsertTerminal(){throw Error('NO_TERMINAL')}
            };
            const c=NOXB1StreamReconnect.createClient({
              transport,host:opts.host,bridge:opts.bridge,ui,timeoutMs:1000
            });
            const pending=c.begin(s);
            if(kind==='stop'){
              const ready=await Promise.race([
                entered.then(()=>true),
                new Promise(r=>setTimeout(()=>r(false),350))
              ]);
              if(!ready||!c.stop(s))return false;
            }
            const result=await Promise.race([
              pending.then(v=>v,e=>e.code),
              new Promise(r=>setTimeout(()=>r('HUNG'),500))
            ]);
            await new Promise(r=>setTimeout(r,0));
            return result===(kind==='stop'?'STOPPED':
                kind==='invalid'?'HOLD_STREAM_INVALID_UTF8':
                'STREAM_ENDED_READBACK_REQUIRED') &&
              cancels===(kind==='complete'?0:1) &&
              posts===1&&acks===0&&
              deltas===(kind==='invalid'?0:1);
          }
          return await one('stop')&&await one('invalid')&&
            await one('complete');
        }'''))
        browser.close()
    print(f'B1 Chromium synthetic two-turn SSE binding: {len(checks)}/{len(checks)} PASS')
    for name in checks:
        print('PASS',name)


if __name__=='__main__':
    main()
