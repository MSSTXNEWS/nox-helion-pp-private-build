/* B1 R59: exact-source, no-network UI identity regression. Run with Node. */
'use strict';
async function run(api){
  let passed=0;
  function check(v,label){if(!v)throw new Error(label);passed++;}
  function dom(){return {nodeType:1,children:[],ownerDocument:{createElement:()=>({dataset:{},textContent:''})},appendChild(e){this.children.push(e);}};}
  function controller(){
    const listeners=new Set();
    const signal={aborted:false,addEventListener(t,f){listeners.add(f);},removeEventListener(t,f){listeners.delete(f);}};
    return {signal,abort(){signal.aborted=true;for(const f of [...listeners])f();}};
  }
  const s={conversation_id:'dialog',exchange_id:'turn2'};
  const c=dom(), ac=controller(); let callbacks=0;
  const a=api.createUiAdapter({container:c,beforeCommit(kind,scope){callbacks++;scope.conversation_id='foreign';scope.exchange_id='turn99';}});
  check(await a.onDelta(s,'alpha',ac.signal,'e1')===true,'delta succeeds');
  check(c.children.length===1&&c.children[0].dataset.noxB1Conversation==='dialog'&&c.children[0].dataset.noxB1Exchange==='turn2','delta pinned to correct row');
  check(await a.onDelta(s,'alpha',ac.signal,'e1')===false&&callbacks===1,'reconnect duplicate suppressed');
  check(await a.upsertTerminal(s,'done2',ac.signal)===true,'terminal succeeds');
  check(c.children.length===1&&c.children[0].dataset.noxB1State==='terminal'&&c.children[0].textContent==='alpha','terminal same immutable row');
  check(await a.upsertTerminal(s,'done2',ac.signal)===true&&callbacks===2,'terminal replay no callback');
  let reads=0;
  const changing={conversation_id:'dialog',get exchange_id(){return ++reads===1?'turn3':'foreign';}};
  check(await a.onDelta(changing,'beta',ac.signal,'e2')===true&&reads===1,'input getter read once');
  check(c.children.length===2&&c.children[1].dataset.noxB1Exchange==='turn3'&&c.children[1].textContent==='beta','third turn separate');
  const stopped=controller(), d=dom();
  const b=api.createUiAdapter({container:d,beforeCommit(kind,scope){scope.exchange_id='foreign';stopped.abort();}});
  check(await b.onDelta(s,'never',stopped.signal,'e3')===false&&d.children.length===0,'STOP no projection');
  const fresh=controller();
  const resume=api.createUiAdapter({container:d});
  check(await resume.onDelta(s,'once',fresh.signal,'e3')===true&&d.children.length===1&&d.children[0].dataset.noxB1Exchange==='turn2','GET-only projection replay after STOP');
  const stopTerminal=controller(), e=dom();
  const z=api.createUiAdapter({container:e,beforeCommit(kind,scope){scope.exchange_id='foreign';stopTerminal.abort();}});
  check(await z.upsertTerminal(s,'done2',stopTerminal.signal)===false&&e.children.length===0,'terminal STOP no projection');
  return passed;
}
module.exports=run;
if(require.main===module)run(require('./b1_abort_safe_ui_adapter.js')).then(n=>console.log('B1 R59 '+n+'/'+n+' PASS')).catch(e=>{console.error(e);process.exitCode=1;});
