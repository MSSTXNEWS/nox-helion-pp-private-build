import {test} from 'node:test';
import assert from 'node:assert/strict';
import {capture} from './b4_chrome_cdp_witness.mjs';
const body='data: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: [DONE]\n\n';
class Stub {
  on(fn){this.emit=fn;}
  close(){}
  async send(cmd){if(cmd==='Browser.getVersion')return {product:'CDP-FIXTURE'};
    if(cmd==='Network.streamResourceContent')return {};
    if(cmd==='Network.getResponseBody')return {body};return {};}
}
async function run(missing=false,chunksForSecondTurn=null){const c=new Stub();return capture({ws:'ws://127.0.0.1:9333/fake',makeSession:async()=>c,timeoutMs:2000,onReady:async()=>{
  setTimeout(async()=>{for(let i=0;i<2;i++){
    const requestId=String(i+1),timestamp=100+i;
    c.emit('Network.requestWillBeSent',{requestId,timestamp,request:{method:'POST',url:'http://localhost/api/nox/chat',postData:'{"secret":"'+i+'"}'}});
    c.emit('Network.responseReceived',{requestId,timestamp:timestamp+.005,response:{status:200,mimeType:'text/event-stream'}});
    await new Promise(r=>setImmediate(r));
    if(missing&&i===1)c.emit('Network.dataReceived',{requestId,timestamp:timestamp+.01});
    else if(i===1&&chunksForSecondTurn){
      for(const chunk of chunksForSecondTurn)
        c.emit('Network.dataReceived',{requestId,timestamp:timestamp+.01,data:Buffer.from(chunk).toString('base64')});
    }else c.emit('Network.dataReceived',{requestId,timestamp:timestamp+.01,data:Buffer.from(body).toString('base64')});
    c.emit('Network.loadingFinished',{requestId,timestamp:timestamp+.02});
    await new Promise(r=>setImmediate(r));
  }},10);
}});}
test('two Chrome-protocol POST events bind distinct digest-only receipts, with SSE timing',async()=>{
  const x=await run();assert.equal(x.cdp_consistent,true);assert.equal(x.ttft_sse_verified,true);
  assert.equal(x.turns.length,2);assert.notEqual(x.turns[0].request_sha256,x.turns[1].request_sha256);
  assert.equal(x.turns[0].ttft_ms,10);assert.equal(x.turns[1].sse_done_ms,10);
  assert.equal(x.native_verified,false);assert.equal(x.browser_authenticated,false);
  assert.equal(x.canonical_s03_verified,false);assert.equal(x.remote_attested,false);
  assert.doesNotMatch(JSON.stringify(x),/secret|Hello/);
});
test('CDP chunk without data cannot prove TTFT or DONE',async()=>{
  const x=await run(true);assert.equal(x.cdp_consistent,true);assert.equal(x.ttft_sse_verified,false);
  assert.equal(x.turns[1].ttft_ms,null);assert.equal(x.turns[1].sse_done_ms,null);
});

test('split UTF-8 and SSE framing are lossless; partial frame/invalid EOF fail closed',async()=>{
  const {createHash}=await import('node:crypto');
  const visible='Привет 🐈';
  const unicodeBody='data: '+JSON.stringify({choices:[{delta:{content:visible}}]})+'\n\ndata: [DONE]\n\n';
  const raw=Buffer.from(unicodeBody,'utf8'),split=raw.indexOf(Buffer.from('🐈'))+2;
  assert.ok(split>2);
  const ok=await run(false,[raw.subarray(0,split),raw.subarray(split,split+1),raw.subarray(split+1)]);
  assert.equal(ok.ttft_sse_verified,true);
  assert.equal(ok.turns[1].visible_text_sha256,createHash('sha256').update(visible).digest('hex'));
  const partial=await run(false,[Buffer.from(body),Buffer.from('data: {"incomplete":true}')]);
  assert.equal(partial.ttft_sse_verified,false);
  assert.equal(partial.turns[1].stream_timing_complete,false);
  assert.equal(partial.turns[1].visible_text_sha256,null);
  const broken=await run(false,[Buffer.from(body),Buffer.from([0xf0,0x9f])]);
  assert.equal(broken.ttft_sse_verified,false);
  assert.equal(broken.turns[1].stream_timing_complete,false);
  assert.equal(broken.turns[1].visible_text_sha256,null);
  assert.doesNotMatch(JSON.stringify(ok),/Привет|🐈/);
});
