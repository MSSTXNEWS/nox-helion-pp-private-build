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
        # A transport may ignore AbortSignal and leave POST pending forever.
        # STOP must settle the client and a late POST result cannot touch UI.
        check('STOP settles hung transport POST with no replay or late delta', page.evaluate('''async () => {
          const s={conversation_id:'post',exchange_id:'stop-hung'};
          let releasePost,posts=0,acks=0,deltas=0;
          const transport={...opts.transport,
            post(){posts++;return new Promise(resolve=>{releasePost=resolve})},
            async ack(){acks++;return true}};
          const host={...opts.host,async readCommitted(){return null}};
          const ui={async onDelta(){deltas++},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:2000
          });
          const pending=c.begin(s);
          for(let i=0;i<30&&!releasePost;i++) await new Promise(r=>setTimeout(r,0));
          if(posts!==1||!releasePost) return false;
          const didStop=c.stop(s);
          const result=await Promise.race([
            pending,new Promise(r=>setTimeout(()=>r('HUNG'),350))
          ]);
          const repost=await c.begin(s).then(()=>false,
            e=>e.code==='HOLD_STREAM_NO_REPOST');
          releasePost({ok:true,body:new ReadableStream({start(reader){
            reader.enqueue(new TextEncoder().encode(
              'event: delta\\ndata: LATE\\n\\n'));reader.close();
          }})});
          await new Promise(r=>setTimeout(r,0));
          return didStop===true&&result==='STOPPED'&&repost&&
            posts===1&&acks===0&&deltas===0;
        }'''))
        check('timeout settles transport POST ignoring AbortSignal', page.evaluate('''async () => {
          const s={conversation_id:'post',exchange_id:'timeout-hung'};
          let posts=0,acks=0;
          const transport={...opts.transport,
            post(){posts++;return new Promise(()=>{})},
            async ack(){acks++;return true}};
          const host={...opts.host,async readCommitted(){return null}};
          const ui={async onDelta(){},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:35
          });
          const result=await Promise.race([
            c.begin(s),new Promise(r=>setTimeout(()=>r('HUNG'),450))
          ]);
          return result==='STOPPED_TIMEOUT'&&posts===1&&acks===0;
        }'''))
        check('late rejected POST after STOP cannot reopen stream', page.evaluate('''async () => {
          const s={conversation_id:'post',exchange_id:'late-rejection'};
          let rejectPost,posts=0,deltas=0,acks=0;
          const transport={...opts.transport,
            post(){posts++;return new Promise((_,reject)=>{rejectPost=reject})},
            async ack(){acks++;return true}};
          const host={...opts.host,async readCommitted(){return null}};
          const ui={async onDelta(){deltas++},async upsertTerminal(){return true}};
          const c=NOXB1StreamReconnect.createClient({
            transport,host,bridge:opts.bridge,ui,timeoutMs:2000
          });
          const pending=c.begin(s);
          for(let i=0;i<30&&!rejectPost;i++) await new Promise(r=>setTimeout(r,0));
          if(!rejectPost) return false;
          c.stop(s);
          const result=await pending;
          rejectPost(Error('late transport failure'));
          await new Promise(r=>setTimeout(r,0));
          return result==='STOPPED'&&posts===1&&acks===0&&deltas===0;
        }'''))
        browser.close()
    print(f'B1 Chromium synthetic two-turn SSE binding: {len(checks)}/{len(checks)} PASS')
    for name in checks:
        print('PASS',name)


if __name__=='__main__':
    main()
