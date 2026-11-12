// NOX V29 PC API CONTRACT — offline executable source test, no fake runtime PASS.
// Run: node test_v29_pc_api_contract.cjs
'use strict';
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(fs.existsSync(path.join(__dirname,'nox-v29-pc-genesis-addons.mjs'))?path.join(__dirname,'nox-v29-pc-genesis-addons.mjs'):path.join(__dirname,'..','..','nox-v29-pc-genesis-addons.mjs'),'utf8');
const sandbox={
  window:{NOX_NATIVE_OWNER:false},
  document:{body:{dataset:{page:'not-an-active-page'}},readyState:'loading',
            addEventListener(){},querySelector(){return null}},
  location:{protocol:'http:',hostname:'127.0.0.1',port:'8766',origin:'http://127.0.0.1:8766'},
  URL,AbortController,Headers,console,setTimeout,clearTimeout
};
vm.runInNewContext(source+'\nglobalThis.__t={validStatus,formatOwner,isNative,formatProgress,actions};',sandbox,{timeout:2000});
const t=sandbox.__t;
const actual={host:'NOX_CHAT_V24.1',status:'READY',primary_model:'nox-prime',
              ollama:'http://127.0.0.1:11434',safe70:{sensor:'RX6650M'}};
assert.equal(t.isNative(),true,'local owner-scoped GET allowed only on loopback :8766');
assert.equal(t.validStatus(actual),true,'real original backend identity must work');
assert.equal(t.validStatus({backend:'EXISTING_NATIVE_ONEHOST',native_p02_bound:true,primary_model:'NOX'}),true);
assert.equal(t.validStatus({...actual,host:'UNTRUSTED'}),false,'unknown server denied');
sandbox.location.hostname='remote.example';sandbox.location.port='443';sandbox.location.protocol='https:';
assert.equal(t.isNative(),false,'remote preview must not send local API requests');
sandbox.location.hostname='127.0.0.1';sandbox.location.port='8766';sandbox.location.protocol='http:';
assert.equal(t.actions.memory.find(x=>x[0]==='pc-s03')[2],'/api/nox/memory');
assert.equal(t.actions.memory.find(x=>x[0]==='s03-dialogs')[2],'/api/nox/history');
assert.equal(t.actions.chat.find(x=>x[0]==='s03-dialogs')[2],'/api/nox/history');
assert(!source.includes('/api/ui/memory/status')&&!source.includes('/api/ui/memory/dialogs/status'));
const ledger=t.formatOwner('PC MEMORY · S03',{status:'READY',stats:{M0:2,M1:3},
                              segments:{M0:[]},ledger_chain_ok:true});
assert(ledger.includes('M0: 2')&&ledger.includes('Genesis Ledger'));
const dialogs=t.formatOwner('PC MEMORY · диалоги',{status:'READY',dialogs:[{messages:3},{messages:4}]});
assert(dialogs.includes('Диалогов: 2')&&dialogs.includes('Сообщений: 7'));
const creator=t.formatOwner('PC · создатель',{status:'READY',total:12,
                               messages:[{sha256:'a'.repeat(64),created_at:'2026-11-12'}]});
assert(creator.includes('Всего: 12')&&creator.includes('2026-11-12'));
const telemetry=t.formatOwner('PC · ресурс GPU',{status:'READY',source:'LibreHardwareMonitor',
        gpu_hot_spot_c:55,gpu_load_percent:82,cpu_load_percent:25,ram_used_gb:10,vram_used_gb:4});
assert(telemetry.includes('55')&&telemetry.includes('GPU, %: 82'));
assert(telemetry.includes('НЕ ПРОВЕДЕНА'),'telemetry is not independent safety certification');
const noHot=t.formatOwner('PC · ресурс GPU',{status:'READY',source:'OS',cpu_load_percent:19,gpu_hot_spot_c:null});
assert(noHot.includes('HOLD · отсутствует Hot Spot'),'missing sensor must hold SAFE70');
const mood=t.formatOwner('PC · эмоции',{status:'READY',simulated:true,mood:'calm'});
assert(mood.includes('симуляция поведения'),'no fake sentience claim');
assert(t.formatProgress({schema:'nox-progress-receipt-v1',status:'HOLD',reason:'No physical checkpoint'}).includes('HOLD'));
assert(!source.includes('localStorage')&&!source.includes('sessionStorage'));
console.log('NOX_V29_REAL_PC_ENDPOINT_CONTRACT_PASS tests=16;Windows_HARDWARE_NOT_TESTED');
