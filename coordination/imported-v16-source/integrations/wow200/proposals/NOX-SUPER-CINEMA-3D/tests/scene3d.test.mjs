import test from "node:test";
import assert from "node:assert/strict";
import {CORE_IDS,PROFILES,budget,mountCinema3D} from "../src/scene3d.mjs";
test("exact eight unchanged canonical CoreIDs, no ninth core",()=>{
 assert.deepEqual(CORE_IDS,["CONSCIOUSNESS","PERSONA","ATLAS","VOICE","REFLECTION","CORE","NEXUS","FORGE"]);
 assert.equal(new Set(CORE_IDS).size,8);
});
test("training uses ECO and reduced motion uses zero-FPS",()=>{
 assert.equal(budget("MAX").fps,30);
 assert.equal(budget("MAX",true).fps,12);
 assert.equal(budget("MAX",false,true).fps,0);
 assert.equal(budget("ECO").dpr,1);
 assert.throws(()=>budget("UNKNOWN"),/INVALID_3D_MODE/);
});
test("no renderer can mount on HOME, even if page claims secondary slot",()=>{
 assert.throws(()=>mountCinema3D(null),/D02_HOME_LOCK/);
 const home={nodeType:1,dataset:{noxWowSlot:"secondary"},closest:()=>({}),ownerDocument:{}};
 assert.throws(()=>mountCinema3D(home),/D02_HOME_LOCK/);
});
test("trusted secondary slot needs WebView2 document, not mocked output",()=>{
 const root={nodeType:1,dataset:{noxWowSlot:"secondary"},closest:()=>null,ownerDocument:{}};
 assert.throws(()=>mountCinema3D(root),/WEBVIEW2_DOCUMENT_REQUIRED/);
});
