import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {setTimeout as sleep} from 'node:timers/promises';
import {performance} from 'node:perf_hooks';
import {measureSseResponse} from './b4_sse_latency_probe.mjs';

const hash=s=>createHash('sha256').update(s).digest('hex');
const event=x=>'data: '+JSON.stringify({choices:[x]})+'\n\n';
const messages=['Привет 🌍','Hola 🌈','三番目 ✨'];
const clean=i=>[ ': heartbeat\n\n',event({delta:{content:' \u0301'}}),
  event({delta:{content:messages[i]}}),event({delta:{},finish_reason:'stop'}),'data: [DONE]\n\n' ];

async function withFixture(handler){
  const requests=[];
  const server=createServer(async(req,res)=>{
    if(req.url!=='/nox/chat'||req.method!=='POST'){res.writeHead(404).end();return;}
    let input='';for await(const chunk of req)input+=chunk;
    const {turn,scenario='clean'}=JSON.parse(input);
    requests.push({turn,scenario,body_sha256:hash(input)});
    res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-store'});
    res.flushHeaders();
    try{
      const chunks=clean(turn-1);
      if(['cr_only','crlf_split','multiline','unframed_cr','unframed_crlf'].includes(scenario)){
        const base=chunks.join('');
        if(scenario==='multiline'){
          const parts=[': heartbeat\r\n\r\n','data\r\n\r\n',
            'data: {"choices":[\r\n',
            'data: {"delta":{"content":'+JSON.stringify(messages[turn-1])+'}}]}\r\n\r\n',
            event({delta:{},finish_reason:'stop'}).replaceAll('\n','\r\n'),
            'data: [DONE]\r\n\r\n'];
          for(const part of parts){res.write(part);await sleep(2);}
        }else if(scenario==='crlf_split'){
          // Split each CRLF across successive HTTP writes, not just JS strings.
          for(const part of base.replaceAll('\n','\r\n').split(/(?<=\r)(?=\n)/u)){
            res.write(part);await sleep(2);
          }
        }else{
          let body=base.replaceAll('\n',scenario==='unframed_crlf'?'\r\n':'\r');
          if(scenario==='unframed_cr')body=body.slice(0,-1);
          if(scenario==='unframed_crlf')body=body.slice(0,-2);
          for(const part of [body.slice(0,10),body.slice(10)]){
            res.write(part);await sleep(2);
          }
        }
        res.end();return;
      }
      for(let i=0;i<chunks.length;i++){
        if(scenario==='abort'&&i===3){res.destroy();return;}
        if(scenario==='stall'&&i===1){await sleep(100);res.destroy();return;}
        if(scenario==='repeat'&&i===4)chunks[i]+='data: [DONE]\n\n';
        if(scenario==='broken'&&i===3){res.end();return;}
        // Real HTTP chunk boundaries may split a UTF-8 emoji.
        const bytes=Buffer.from(chunks[i]);
        if(i===2){const p=bytes.length-3;res.write(bytes.subarray(0,p));await sleep(8);res.write(bytes.subarray(p));}
        else res.write(bytes);
        await sleep(6);
      }
      res.end();
    }catch{try{res.destroy();}catch{}}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const url='http://127.0.0.1:'+server.address().port+'/nox/chat';
  try{return await handler(url,requests);}finally{
    server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
  }
}
const send=(url,turn,scenario='clean')=>{
  const startedAt=performance.now();
  return fetch(url,{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({turn,scenario})}).then(response=>({response,startedAt}));
};

test('R24 real loopback HTTP three sequential turns: Unicode, independent SHA and true EOF completion',async()=>{
  await withFixture(async(url,requests)=>{
    const proofs=[];
    for(let turn=1;turn<=3;turn++){
      const {response,startedAt}=await send(url,turn);
      const result=await measureSseResponse(response,{startedAt});proofs.push(result);
      assert.equal(result.verified,true);
      assert.ok(result.first_byte_ms>=0);
      assert.ok(result.ttft_ms>=result.first_byte_ms);
      assert.ok(result.completion_ms>=result.sse_done_ms);
      assert.ok(result.sse_done_ms>=result.ttft_ms);
      assert.equal(result.visible_text_sha256,hash(' \u0301'+messages[turn-1]));
      assert.equal(result.native_verified,false);
      assert.equal(result.browser_authenticated,false);
      assert.equal(result.canonical_s03_verified,false);
      assert.equal(result.model_tokens_per_second,null);
      assert.doesNotMatch(JSON.stringify(result),/Привет|Hola|三番目|data:/);
    }
    assert.equal(requests.length,3);
    assert.deepEqual(requests.map(p=>p.turn),[1,2,3]);
    assert.equal(new Set(proofs.map(p=>p.body_sha256)).size,3);
    assert.equal(new Set(proofs.map(p=>p.visible_text_sha256)).size,3);
  });
});

test('R24 third-turn abort, unframed EOF, duplicate DONE, and stalled SSE fail closed',async()=>{
  await withFixture(async(url,requests)=>{
    for(const [scenario,pattern] of [
      ['abort',/B4_INCOMPLETE_SSE|terminated|fetch failed/],
      ['broken',/B4_INCOMPLETE_SSE/],
      ['repeat',/B4_POST_DONE_EVENT/],
      ['stall',/B4_IDLE_TIMEOUT|terminated/]
    ]){
      const {response,startedAt}=await send(url,3,scenario);
      await assert.rejects(measureSseResponse(response,{startedAt,idleTimeoutMs:35}),pattern);
    }
    assert.equal(requests.length,4);
  });
});


test('R25 real HTTP loopback: lone CR, split CRLF, multiline SSE; incomplete terminal framing fails closed',async()=>{
  await withFixture(async(url,requests)=>{
    for(const [i,scenario] of ['cr_only','crlf_split','multiline'].entries()){
      const {response,startedAt}=await send(url,i+1,scenario);
      const result=await measureSseResponse(response,{startedAt});
      assert.equal(result.verified,true,scenario);
      assert.ok(result.first_byte_ms>=0 && result.ttft_ms>=result.first_byte_ms,scenario);
      assert.ok(result.completion_ms>=result.sse_done_ms && result.sse_done_ms>=result.ttft_ms,scenario);
      assert.equal(result.visible_text_sha256,hash(scenario==='multiline'?messages[i]:' \u0301'+messages[i]));
      assert.equal(result.browser_authenticated,false);
      assert.equal(result.native_verified,false);
      assert.equal(result.canonical_s03_verified,false);
    }
    for(const scenario of ['unframed_cr','unframed_crlf']){
      const {response,startedAt}=await send(url,3,scenario);
      await assert.rejects(measureSseResponse(response,{startedAt}),/B4_UNFRAMED_EOF/,scenario);
    }
    assert.deepEqual(requests.map(x=>x.scenario),
      ['cr_only','crlf_split','multiline','unframed_cr','unframed_crlf']);
  });
});
