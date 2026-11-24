"""Source-only Chromium composition: existing dialog, synthetic server/gate."""
from pathlib import Path
from playwright.sync_api import sync_playwright
HERE=Path(__file__).resolve().parent
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page()
    page.route("**/*",lambda route: route.abort())
    page.set_content('<main id="chat"><div data-nox-b1-conversation="d" data-nox-b1-exchange="t1" data-nox-b1-state="terminal" data-nox-b1-event-id="event-t1">Existing</div></main>')
    for src in (HERE.parent/'b1-r61'/'b1_abort_safe_ui_adapter.js',HERE.parent/'b1-r68'/'b1_client_stream_reconnect_harness.js',HERE.parent/'b1-r62'/'b1_sse_ui_binding.js'):
        page.add_script_tag(path=str(src))
    labels=page.evaluate(r"""async () => {
      if(!crypto.randomUUID) {let nonce=0;Object.defineProperty(crypto,'randomUUID',{value:()=> 'fixture-'+(++nonce)});}
      const labels=[],check=(name,ok)=>{if(!ok)throw Error(name);labels.push(name)};
      const chat=document.querySelector('#chat'),original=chat.firstElementChild;
      const s2={conversation_id:'d',exchange_id:'t2'},s3={conversation_id:'d',exchange_id:'t3'};
      const posts=[],acks=[],gets=[],signed=[],state=new Map();
      let eventReads=0,cursorReads=0;const gateCursors=[];
      const row=s=>Array.from(chat.children).find(e=>e.dataset.noxB1Exchange===s.exchange_id);
      let pausedResolve;const paused=new Promise(r=>pausedResolve=r);
      let release;const blocked=new Promise(r=>release=r);let n=0;
      const transport={
        async post(s,signal){posts.push(s.exchange_id);const frames=s.exchange_id==='t2'?
          'id: e21\nevent: delta\ndata: Hola\n\nid: e22\nevent: delta\ndata: LATE\n\n':
          'id: e31\nevent: delta\ndata: Mundo\n\nid: e31\nevent: delta\ndata: Mundo\n\n';
          return {ok:true,body:new ReadableStream({start(c){c.enqueue(new TextEncoder().encode(frames));c.close()}})}},
        async readback(s){gets.push(s.exchange_id);return {...s}},
        async ack(s){acks.push(s.exchange_id);return true},
        async readCanonicalAck(s,e,c){signed.push(s.exchange_id);return {request_nonce:c.request_nonce,issued_at_ms:Date.now(),expires_at_ms:Date.now()+1000,ack_id:'ack-'+s.exchange_id}}
      };
      const host={async readCommitted(c,e){return null},
        async verifyCanonicalAck(r,e,s){return r.ack_id==='ack-'+s.exchange_id},
        async verifyFreshCanonicalAck(r,e,s,c){return r.request_nonce===c.request_nonce && r.ack_id==='ack-'+s.exchange_id}};
      const bridge={async acceptTerminal(packet,s){return {...s,safe_to_ack:true,model_post:false,get projection_event_id(){eventReads++;return this._eventSeen?'foreign-event':(this._eventSeen=true,'event-'+s.exchange_id)},get ack_cursor(){cursorReads++;return this._cursorSeen?'foreign-cursor':(this._cursorSeen=true,'cursor-'+s.exchange_id)}}}};
      const gate={async reserve(s){return state.has(s.exchange_id)?{status:'ALREADY_ACKED'}:{status:'RESERVED',key:s.exchange_id}},
        async beginSend(g){state.set(g.key,'SENDING');return 'SENDING'},async confirm(){throw Error('local confirm forbidden')},
        async requireCanonicalAck(s,event,cursor,read,verify){gateCursors.push(cursor);const e={event_id:event,ack_cursor:cursor},r=await read(e);
          if(!await verify(r,e))throw Error('bad fixture proof');state.set(s.exchange_id,'ACKED');
          return {status:'CANONICAL_ACK_CONFIRMED',authority:'VERIFIER_CALLBACK_APPROVED',ack_id:r.ack_id}}};
      const client=NOXB1SseUiBinding.bind({container:chat,transport,host,bridge,ackGate:gate,
        timeoutMs:5000, beforeCommit:async(kind,s)=>{if(kind==='delta'&&s.exchange_id==='t2'&&++n===2){pausedResolve();await blocked}}});
      let reads=0;
      const changing={conversation_id:'d',get exchange_id(){return ++reads===1?'t2':'foreign'}};
      const pending=client.begin(changing);
      await Promise.race([paused,new Promise((_,rej)=>setTimeout(()=>rej(Error('pause missing; scope changed')),2000))]);
      check('scope getter read once, target t2',reads===1&&posts.join()==='t2');
      check('STOP t2',client.stop(s2)===true);
      check('t2 stopped',await pending==='STOPPED');
      release();
      check('no late delta',row(s2).textContent==='Hola');
      try{await client.begin(s2);throw Error('repost allowed')}catch(e){check('no repost',e.code==='HOLD_STREAM_NO_REPOST')}
      let r=await client.reconnect(s2);
      check('t2 canonical synthetic receipt',r.canonical_ack_id==='ack-t2'&&row(s2).dataset.noxB1State==='terminal');
      check('t3 stream',await client.begin(s3)==='STREAM_ENDED_READBACK_REQUIRED');
      check('t3 wire duplicate suppressed',row(s3).textContent==='Mundo');
      r=await client.reconnect(s3);
      check('t3 canonical synthetic receipt',r.canonical_ack_id==='ack-t3'&&row(s3).dataset.noxB1State==='terminal');
      await Promise.all([client.reconnect(s2),client.reconnect(s2)]);
      check('GET-only duplicate reconnect',posts.join()==='t2,t3'&&acks.join()==='t2,t3'&&gets.length===3&&signed.length===3);
      check('existing t1 unchanged; exactly three rows',chat.children.length===3&&chat.firstElementChild===original&&original.textContent==='Existing'&&original.dataset.noxB1EventId==='event-t1');
      check('separate terminal identities',row(s2).dataset.noxB1EventId==='event-t2'&&row(s3).dataset.noxB1EventId==='event-t3');
      check('R63 event and cursor getters read once per GET',eventReads===3&&cursorReads===3);
      check('R63 canonical gate uses exact cursors',gateCursors.join()==='cursor-t2,cursor-t3,cursor-t2');
      // Independent browser fixture: reentrant STOP while the POST response
      // is being inspected, before the actual ReadableStream is acquired.
      const second=document.createElement('main');
      second.innerHTML='<div data-nox-b1-conversation="d" data-nox-b1-exchange="t1" data-nox-b1-state="terminal">Existing</div>';
      document.body.appendChild(second);
      const prior=second.firstElementChild;
      let stopClient,stopPosts=0,stopGets=0,stopAcks=0,bodyReads=0,readerReads=0,cancels=0,stopped=false;
      const liveBody=new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('id: late\\nevent: delta\\ndata: LATE\\n\\n'))},cancel(){cancels++}});
      const getReader=liveBody.getReader.bind(liveBody);
      Object.defineProperty(liveBody,'getReader',{value(){readerReads++;return getReader()}});
      stopClient=NOXB1SseUiBinding.bind({container:second,host,bridge,ackGate:gate,timeoutMs:5000,
        transport:{async post(){stopPosts++;return {get body(){bodyReads++;return liveBody},get ok(){stopped=stopClient.stop(s2);return true}}},
          async readback(){stopGets++;throw Error('unexpected GET')},
          async ack(){stopAcks++;throw Error('unexpected ACK')},
          async readCanonicalAck(){throw Error('unexpected canonical ACK')}}});
      check('R65 reentrant HTTP status STOP',await stopClient.begin(s2)==='STOPPED'&&stopped);
      check('R65 unread browser body disposed once',bodyReads===1&&readerReads===0&&cancels===1&&!liveBody.locked);
      try{await stopClient.begin(s2);throw Error('repost allowed')}catch(e){check('R65 stopped POST cannot be repeated',e.code==='HOLD_STREAM_NO_REPOST'&&stopPosts===1)}
      check('R65 no late DOM or implicit GET/ACK',second.children.length===1&&second.firstElementChild===prior&&prior.textContent==='Existing'&&stopGets===0&&stopAcks===0);

      // R68: actual Chromium ReadableStream reader with reentrant result getters.
      const third=document.createElement('main');
      third.innerHTML='<div data-nox-b1-conversation="d" data-nox-b1-exchange="t1" data-nox-b1-state="terminal">Existing</div>';
      document.body.appendChild(third);
      const original3=third.firstElementChild;
      const enc=new TextEncoder(),all=enc.encode('id: r21\nevent: delta\ndata: Привет\n\nid: r22\nevent: delta\ndata: мир\n\n');
      const split=all.findIndex(x=>x===0xd0)+1;
      let snapReads=0,p3=0,c3=0,read3=0,ack3=0,get3=0,client3;
      const real=new ReadableStream({start(c){c.enqueue(all.slice(0,split));c.enqueue(all.slice(split));c.close()}});
      const acquire=real.getReader.bind(real);
      Object.defineProperty(real,'getReader',{value(){const reader=acquire();return {
        async read(){const result=await reader.read();read3++;if(result.done)return result;let n=0;
          return {get done(){snapReads++;return ++n!==1},value:result.value}},
        cancel(){c3++;return reader.cancel()},releaseLock(){reader.releaseLock()}
      }}});
      const r3={async post(){p3++;return {ok:true,body:real}},async readback(){get3++;throw Error('unexpected GET')},
        async ack(){ack3++;throw Error('unexpected ACK')},async readCanonicalAck(){throw Error('unexpected proof')}};
      client3=NOXB1SseUiBinding.bind({container:third,transport:r3,host,bridge,ackGate:gate,timeoutMs:5000});
      check('R68 changing done getter retains both real browser chunks',await client3.begin(s2)==='STREAM_ENDED_READBACK_REQUIRED'&&read3===3&&snapReads===2);
      check('R68 exact split UTF8 and both deltas',third.children.length===2&&third.lastElementChild.textContent==='Приветмир'&&third.firstElementChild===original3);
      try{await client3.begin(s2);throw Error('repost allowed')}catch(e){check('R68 no duplicate POST or implicit ACK/GET',e.code==='HOLD_STREAM_NO_REPOST'&&p3===1&&ack3===0&&get3===0&&c3===0)}
      const fourth=document.createElement('main');fourth.innerHTML=third.firstElementChild.outerHTML;document.body.appendChild(fourth);
      let client4,stop4=false,values4=0,posts4=0,cancel4=0;
      const stopBody=new ReadableStream({start(c){c.enqueue(enc.encode('id: late\nevent: delta\ndata: LATE\n\n'))},cancel(){cancel4++}});
      const acquire4=stopBody.getReader.bind(stopBody);
      Object.defineProperty(stopBody,'getReader',{value(){const reader=acquire4();return {
        async read(){const result=await reader.read();return {get done(){stop4=client4.stop(s3);return result.done},get value(){values4++;return result.value}}},
        cancel(){return reader.cancel()},releaseLock(){reader.releaseLock()}
      }}});
      client4=NOXB1SseUiBinding.bind({container:fourth,host,bridge,ackGate:gate,timeoutMs:5000,transport:{...r3,async post(){posts4++;return {ok:true,body:stopBody}}}});
      check('R68 STOP in done getter prevents value read and late DOM',await client4.begin(s3)==='STOPPED'&&stop4&&values4===0&&cancel4===1&&fourth.children.length===1);
      try{await client4.begin(s3);throw Error('repost allowed')}catch(e){check('R68 STOP cannot replay third POST',e.code==='HOLD_STREAM_NO_REPOST'&&posts4===1&&get3===0&&ack3===0)}
      return labels;
    }""")
    browser.close()
    for label in labels: print("PASS",label)
    print(f"B1_R69_SYNTHETIC {len(labels)}/23 PASS; NATIVE_ACCEPTED=false")
    assert len(labels)==23
