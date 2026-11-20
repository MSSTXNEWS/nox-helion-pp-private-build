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
async function run(missing=false){const c=new Stub();return capture({ws:'ws://127.0.0.1:9333/fake',makeSession:async()=>c,timeoutMs:2000,onReady:async()=>{
  setTimeout(async()=>{for(let i=0;i<2;i++){
    const requestId=String(i+1),timestamp=100+i;
    c.emit('Network.requestWillBeSent',{requestId,timestamp,request:{method:'POST',url:'http://localhost/api/nox/chat',postData:'{"secret":"'+i+'"}'}});
    c.emit('Network.responseReceived',{requestId,timestamp:timestamp+.005,response:{status:200,mimeType:'text/event-stream'}});
    await new Promise(r=>setImmediate(r));
    if(missing&&i===1)c.emit('Network.dataReceived',{requestId,timestamp:timestamp+.01});
    else c.emit('Network.dataReceived',{requestId,timestamp:timestamp+.01,data:Buffer.from(body).toString('base64')});
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
