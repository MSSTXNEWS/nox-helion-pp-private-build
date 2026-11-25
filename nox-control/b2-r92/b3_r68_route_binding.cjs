'use strict';
// Offline comparison only. mapping must be supplied by an independent authenticated owner verifier.
// No normalization, network, owner admission, or production acceptance. Distinct transport/physical digests.
function check({wire,physical,mapping}={}){
 const fail=reason=>({status:"HOLD",reason,consistent:false,authentication_verified:false,native_accepted:false});
 const obj=x=>x!==null&&typeof x==="object"&&!Array.isArray(x);
 const hash=x=>typeof x==="string"&&/^[0-9a-f]{64}$/.test(x)&&!/^(.)\1+$/.test(x);
 const id=x=>typeof x==="string"&&x.length>0&&x.length<=160&&x===x.trim()&&!/[\x00-\x1f\x7f]/.test(x);
 const pos=x=>Number.isSafeInteger(x)&&x>0;
 if(!obj(wire)||!obj(physical)||!obj(mapping)||mapping.schema!=="NOX_B3_ROUTE_BINDING_V1")return fail("SCHEMA");
 if(wire.wire!=="named-delta-stable-server-id-v1"||typeof wire.route!=="string"||!/^[A-Za-z0-9._:-]{1,128}$/.test(wire.route))return fail("WIRE");
 const wh=["served_sha256","server_sha256"];
 for(const k of wh)if(!hash(wire[k])||mapping[k]!==wire[k])return fail("WIRE_PIN_"+k);
 if(mapping.wire!==wire.wire||mapping.symbolic_route!==wire.route)return fail("SYMBOLIC_ROUTE");
 for(const k of ["route","model_id","dialog_id"])if(!id(physical[k])||mapping[k]!==physical[k])return fail("PHYSICAL_"+k);
 for(const k of ["weights_manifest_sha256","tokenizer_manifest_sha256","bridge_sha256","original_checkpoint_sha256","owner_admission_receipt_sha256"])if(!hash(physical[k])||mapping[k]!==physical[k])return fail("PHYSICAL_"+k);
 if(physical.bridge_sha256!=="c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7")return fail("R64_RELEASE");
 const a=physical.process,b=mapping.process;
 if(!obj(a)||!obj(b)||!id(a.boot_id)||!pos(a.pid)||!pos(a.start_ticks)||a.boot_id!==b.boot_id||a.pid!==b.pid||a.start_ticks!==b.start_ticks)return fail("PROCESS");
 const ids=physical.turn_request_ids,mids=mapping.turn_request_ids;
 if(!Array.isArray(ids)||!Array.isArray(mids)||ids.length!==2||mids.length!==2||!ids.every(id)||ids[0]===ids[1]||ids.some((x,i)=>x!==mids[i]))return fail("TURN_SCOPE");
 for(const k of ["window_start_ms","window_end_ms"])if(!pos(physical[k])||physical[k]!==mapping[k])return fail("WINDOW");
 if(physical.window_start_ms>=physical.window_end_ms)return fail("WINDOW");
 return {status:"CONSISTENT_MAPPING_ONLY",consistent:true,authentication_verified:false,native_accepted:false,requires_external_verifier:true};
}
function selfTest(){
 const h=n=>n.toString(16).padStart(64,"0");
 const wire={wire:"named-delta-stable-server-id-v1",route:"model-route:1",served_sha256:h(21),server_sha256:h(22)};
 const physical={route:"/fixture/model",model_id:"fixture",dialog_id:"dialog",weights_manifest_sha256:h(11),tokenizer_manifest_sha256:h(12),bridge_sha256:"c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7",original_checkpoint_sha256:h(13),owner_admission_receipt_sha256:h(14),process:{boot_id:"boot",pid:42,start_ticks:123},turn_request_ids:["req2","req3"],window_start_ms:100,window_end_ms:200};
 const mapping={...JSON.parse(JSON.stringify(physical)),schema:"NOX_B3_ROUTE_BINDING_V1",wire:wire.wire,symbolic_route:wire.route,served_sha256:wire.served_sha256,server_sha256:wire.server_sha256};
 const fixture={wire,physical,mapping};
 const cases=[["explicit mapping",()=>{},true],["no mapping",x=>delete x.mapping,false],["guess symbolic route",x=>x.mapping.symbolic_route=x.physical.route,false],["physical alias drift",x=>x.mapping.route="/other",false],["server digest drift",x=>x.mapping.server_sha256=h(99),false],["asset digest drift",x=>x.mapping.served_sha256=h(99),false],["model drift",x=>x.mapping.model_id="other",false],["tokenizer drift",x=>x.mapping.tokenizer_manifest_sha256=h(99),false],["weight drift",x=>x.mapping.weights_manifest_sha256=h(99),false],["process drift",x=>x.mapping.process.start_ticks++,false],["checkpoint drift",x=>x.mapping.original_checkpoint_sha256=h(99),false],["owner receipt drift",x=>x.mapping.owner_admission_receipt_sha256=h(99),false],["turn swap",x=>x.mapping.turn_request_ids.reverse(),false],["window drift",x=>x.mapping.window_end_ms++,false],["coherently wrong release",x=>x.mapping.bridge_sha256=x.physical.bridge_sha256=h(99),false]];
 return cases.map(([name,mutate,want])=>{const x=JSON.parse(JSON.stringify(fixture));mutate(x);const z=check(x);if(z.consistent!==want||z.authentication_verified!==false||z.native_accepted!==false)throw Error(name);return {name,status:z.status,reason:z.reason||null};});
}
module.exports={check,selfTest};
if(require.main===module)console.log(JSON.stringify({cases:selfTest(),native_accepted:false},null,2));
