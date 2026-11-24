'use strict';
// B3 R69: offline comparison for actual B1 R74 verifyWire(pin,scope,signal) callsite.
// Independently authenticated mapping must explicitly link logical IDs to physical IDs.
// No owner admission, POST, authentication or native acceptance; expectedTurn from trusted orchestration.
const r68=require('./b3_r68_route_binding.cjs');
function check({wire,physical,mapping,scope,expectedTurn}={}){
 const fail=reason=>({status:"HOLD",reason,consistent:false,authentication_verified:false,native_accepted:false});
 const id=x=>typeof x==="string"&&/^[A-Za-z0-9._:-]{1,128}$/.test(x);
 const prior=r68.check({wire,physical,mapping});
 if(!prior.consistent)return fail("R68_"+prior.reason);
 if(expectedTurn!==2&&expectedTurn!==3)return fail("TURN_NOT_2_OR_3");
 if(!scope||!id(scope.conversation_id)||!id(scope.exchange_id)||!id(mapping.conversation_id)||scope.conversation_id!==mapping.conversation_id)return fail("CONVERSATION_SCOPE");
 const rows=mapping.exchange_bindings;
 if(!Array.isArray(rows)||rows.length!==2)return fail("EXCHANGE_MAPPING_REQUIRED");
 for(let i=0;i<2;i++){
  const row=rows[i];
  if(!row||row.turn!==i+2||row.request_id!==physical.turn_request_ids[i]||!id(row.exchange_id))return fail("EXCHANGE_MAPPING_"+(i+2));
 }
 if(rows[0].exchange_id===rows[1].exchange_id)return fail("EXCHANGE_REUSE");
 if(rows[expectedTurn-2].exchange_id!==scope.exchange_id)return fail("ACTUAL_EXCHANGE_SCOPE");
 return {status:"CONSISTENT_SCOPE_ONLY",consistent:true,authentication_verified:false,native_accepted:false,requires_external_verifier:true};
}
function selfTest(){
 const h=n=>n.toString(16).padStart(64,"0");
 const wire={wire:"named-delta-stable-server-id-v1",route:"logical-route",served_sha256:h(21),server_sha256:h(22)};
 const physical={route:"/fixture/model",model_id:"fixture",dialog_id:"physical-dialog",weights_manifest_sha256:h(11),tokenizer_manifest_sha256:h(12),bridge_sha256:"c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7",original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),process:{boot_id:"boot",pid:42,start_ticks:123},turn_request_ids:["physical-request-2","physical-request-3"],window_start_ms:100,window_end_ms:200};
 const mapping={...JSON.parse(JSON.stringify(physical)),schema:"NOX_B3_ROUTE_BINDING_V1",wire:wire.wire,symbolic_route:wire.route,served_sha256:wire.served_sha256,server_sha256:wire.server_sha256,conversation_id:"logical-conversation",exchange_bindings:[{turn:2,request_id:"physical-request-2",exchange_id:"logical-exchange-2"},{turn:3,request_id:"physical-request-3",exchange_id:"logical-exchange-3"}]};
 const fixture={wire,physical,mapping,scope:{conversation_id:"logical-conversation",exchange_id:"logical-exchange-2"},expectedTurn:2};
 const cases=[
 ["valid turn2 explicit mapping",()=>{},true],["valid turn3 explicit mapping",x=>{x.expectedTurn=3;x.scope.exchange_id="logical-exchange-3";},true],
 ["foreign actual conversation",x=>x.scope.conversation_id="foreign",false],["foreign actual exchange",x=>x.scope.exchange_id="foreign",false],
 ["turn3 exchange during turn2",x=>x.scope.exchange_id="logical-exchange-3",false],["turn2 exchange during turn3",x=>x.expectedTurn=3,false],
 ["guessed conversation equals physical",x=>x.scope.conversation_id=x.physical.dialog_id,false],["guessed exchange equals physical",x=>x.scope.exchange_id=x.physical.turn_request_ids[0],false],
 ["missing mapping",x=>delete x.mapping.exchange_bindings,false],["duplicate exchange",x=>x.mapping.exchange_bindings[1].exchange_id=x.mapping.exchange_bindings[0].exchange_id,false],
 ["swapped request",x=>x.mapping.exchange_bindings[0].request_id=x.physical.turn_request_ids[1],false],["reordered mapping",x=>x.mapping.exchange_bindings.reverse(),false],
 ["turn1 replay",x=>x.expectedTurn=1,false],["malformed actual scope",x=>x.scope.exchange_id="bad/id",false],
 ["wrong physical tokenizer",x=>x.physical.tokenizer_manifest_sha256=h(90),false],["wrong server bytes",x=>x.wire.server_sha256=h(90),false],
 ["missing actual scope",x=>delete x.scope,false],["missing conversation mapping",x=>delete x.mapping.conversation_id,false]];
 return cases.map(([name,mutate,want])=>{const x=JSON.parse(JSON.stringify(fixture));mutate(x);const old=r68.check(x),z=check(x);if(z.consistent!==want||z.authentication_verified!==false||z.native_accepted!==false)throw Error(name+JSON.stringify(z));return {name,old_consistent:old.consistent,new_consistent:z.consistent,reason:z.reason||null};});
}
module.exports={check,selfTest};
if(require.main===module)console.log(JSON.stringify({cases:selfTest(),native_accepted:false},null,2));
