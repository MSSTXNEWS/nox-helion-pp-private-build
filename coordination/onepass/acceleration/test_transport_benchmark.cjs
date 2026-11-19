/* Isolated transport benchmark; NOT a GPU/model/server benchmark. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const id='abcd1234abcd1234abcd1234abcd1234', exchange='benchmark-exchange';
const prompt='Synthetic transport fixture, not model performance';
const parts=Array.from({length:12},(_,i)=>`Секция ${i} `+'Ж'.repeat(70)+' 👨‍👩‍👧‍👦 e\u0301 '+ 'X'.repeat(70));
const answer=parts.join('');
async function run(file){
  let frames=0, historyReads=0;
  const native=async(u,opts={})=>{
    const url=new URL(String(u),'https://nox.local');
    if(url.pathname==='/api/nox/chat/stream'){
      const wire=[{type:'preparing',stream_mode:'NATIVE_TOKEN_STREAM'},{type:'start'},
        ...parts.map(text=>({type:'delta',text})),{type:'done',saved:true,s03_integrated:true,dialog_id:id,exchange_id:exchange}];
      const bytes=new TextEncoder();
      return new Response(new ReadableStream({start(c){for(const row of wire)c.enqueue(bytes.encode(JSON.stringify(row)+'\n'));c.close();}}));
    }
    if(url.pathname==='/api/ui/memory/dialogs/history'){
      historyReads++;
      return Response.json({status:'READY',dialog_id:id,messages:[{role:'user',content:prompt,exchange_id:exchange},{role:'assistant',content:answer,exchange_id:exchange}]});
    }
    throw Error('Unexpected URL');
  };
  const window={NOX_NATIVE_OWNER:true,fetch:native};
  const location={origin:'https://nox.local',href:'https://nox.local/nox-web-v29/pc/resonance.html',pathname:'/nox-web-v29/pc/resonance.html'};
  const sandbox={window,location,URL,Request,Response,ReadableStream,TextDecoder,TextEncoder,AbortController,performance,console,setTimeout,clearTimeout,
    requestAnimationFrame(cb){frames++;return setTimeout(()=>cb(performance.now()),16);}};
  vm.runInNewContext(fs.readFileSync(file,'utf8'),sandbox,{filename:file});
  const start=performance.now();
  const response=await window.fetch('/api/nox/chat',{method:'POST',body:JSON.stringify({message:prompt,dialog_id:id,request_id:'transport-bench'})});
  const text=await response.text(),total_ms=performance.now()-start;
  const events=text.trim().split('\n\n').map(s=>JSON.parse(s.slice(6)));
  assert.equal(events.filter(e=>e.type==='token').map(e=>e.t).join(''),answer);
  assert.equal(events.filter(e=>e.type==='done').length,1);
  assert.equal(events.filter(e=>e.type==='error').length,0);
  assert.equal(historyReads,1);
  return {total_ms:Number(total_ms.toFixed(3)),animation_frame_waits:frames,independent_s03_fixture_reads:historyReads};
}
(async()=>{
  const before=process.argv[2],after=process.argv[3],out=process.argv[4];
  assert(before&&after&&out,'usage: node test_transport_benchmark.cjs BEFORE AFTER OUT');
  const old=[],fast=[];
  for(let i=0;i<5;i++){old.push(await run(before));fast.push(await run(after));}
  const median=rows=>rows.map(r=>r.total_ms).sort((a,b)=>a-b)[Math.floor(rows.length/2)];
  const receipt={schema:'NOX_ISOLATED_TRANSPORT_BENCH_V1',sample_count:5,fixture:'12 immediate NDJSON deltas; controlled 16ms rAF',
    before:old,after:fast,before_median_ms:median(old),after_median_ms:median(fast),
    native_gpu_benchmark:false,native_server_modified:false,token_bytes_equal:true,s03_guard_preserved:true,
    source_before_sha256:require('node:crypto').createHash('sha256').update(fs.readFileSync(before)).digest('hex'),
    source_after_sha256:require('node:crypto').createHash('sha256').update(fs.readFileSync(after)).digest('hex')};
  assert(fast.every(r=>r.animation_frame_waits===0));
  fs.writeFileSync(out,JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
