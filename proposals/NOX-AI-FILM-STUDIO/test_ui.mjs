import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import vm from "node:vm";
const html=readFileSync(new URL("./index.html",import.meta.url),"utf8");
const css=readFileSync(new URL("./film-studio.css",import.meta.url),"utf8");
const src=readFileSync(new URL("./film-studio.js",import.meta.url),"utf8");
class Node {
 constructor(tag="div"){this.tag=tag;this.nodeType=1;this.children=[];this.listeners={};this.value="";this.checked=false;this.disabled=false;this.textContent="";this.className="";this.type="";}
 append(...elements){for(const e of elements){this.children.push(e);if(this.tag==="select"&&!this.value)this.value=e.value}}
 replaceChildren(...nodes){this.children=[...nodes]}
 addEventListener(name,fn){this.listeners[name]=fn}
 click(){this.listeners.click?.()}
 change(){this.listeners.change?.()}
 setAttribute(){}
}
function app() {
 const ids=[...html.matchAll(/id="([^"]+)"/g)].map(x=>x[1]);
 const elements=new Map(ids.map(id=>[id,new Node("div")]));
 for(const id of ["filmStyle","filmRating","filmResolution","sceneSeconds","sceneProvider","sceneMethod"])elements.get(id).tag="select";
 for(const id of ["sceneTitle","scenePrompt","sceneDialog","filmTitle"])elements.get(id).tag="input";
 elements.get("filmTitle").value="NOX movie";
 elements.get("sceneMethod").value="t2v";
 elements.get("sceneSeconds").value="6";
 elements.get("filmRating").value="GENERAL";
 elements.get("filmResolution").value="832x480";
 const web={messages:[],listeners:{},postMessage(cmd){this.messages.push(cmd)},addEventListener(name,fn){this.listeners[name]=fn}};
 const ctx={window:{chrome:{webview:web}},document:{getElementById:id=>elements.get(id),
  createElement:tag=>new Node(tag)},Date,Math};
 vm.runInNewContext(src,ctx);
 return {elements,web,e:id=>elements.get(id)};
}
test("studio has twelve distinct film and animation genre choices",()=>{
 const x=app(),styles=x.e("filmStyle").children;
 assert.equal(styles.length,12);
 assert.ok(styles.some(z=>z.value==="anime"));
 assert.ok(styles.some(z=>z.value==="cartoon_2d"));
 assert.ok(styles.some(z=>z.value==="cartoon_3d"));
 assert.ok(styles.some(z=>z.value==="adult_anime_18"));
 assert.ok(x.e("queueFilm").disabled);
 assert.ok(x.e("exportFilm").disabled);
});
test("offline storyboard is real but never claims a queued film",()=>{
 const x=app();
 x.e("sceneTitle").value="Первый кадр";
 x.e("scenePrompt").value="Красивый закат, камера плавно движется";
 x.e("addScene").click();
 assert.equal(x.e("scenes").children.length,1);
 assert.match(x.e("actionStatus").textContent,/Подтверди права/);
 x.e("filmRights").checked=true;x.e("addScene").click();
 assert.equal(x.e("sceneCount").textContent,"1 сцен");
 assert.equal(x.e("totalTime").textContent,"0:06");
 assert.equal(x.web.messages.length,0);
 assert.ok(x.e("exportFilm").disabled);
});
test("host queue only after explicitly authorized user click",()=>{
 const x=app();
 x.e("filmRights").checked=true;
 x.e("sceneTitle").value="Test";
 x.e("scenePrompt").value="photorealistic cinematic animation";
 x.e("addScene").click();
 x.web.listeners.message({data:{type:"nox.film.snapshot.v1",
  capabilities:{save:true,queue:true,export:true,projector:true},scenes:[]}});
 assert.equal(x.e("queueFilm").disabled,false);
 x.e("queueFilm").click();
 assert.equal(x.web.messages.length,1);
 assert.equal(x.web.messages[0].type,"nox.film.command.v1");
 assert.equal(x.web.messages[0].action,"queue");
 assert.equal(x.web.messages[0].project.scenes.length,1);
 assert.equal(x.web.messages[0].project.scenes[0].status,"PLANNED");
 assert.equal(x.e("exportFilm").disabled,true);
});
test("adult anime cannot queue without 18+ consent",()=>{
 const x=app();x.e("filmRights").checked=true;
 x.e("filmStyle").value="adult_anime_18";x.e("filmRating").value="GENERAL";
 x.e("sceneTitle").value="Adult animation";x.e("scenePrompt").value="adults in an animation";
 x.e("addScene").click();assert.equal(x.e("sceneCount").textContent,"0 сцен");
 x.e("filmRating").value="ADULT_18";x.e("adultConfirmed").checked=true;
 x.e("addScene").click();assert.equal(x.e("sceneCount").textContent,"1 сцен");
});
test("mobile web and D02 source contract",()=>{
 for(const rule of ["max-width:430px","max-width:360px","max-width:800px","max-height:480px","prefers-reduced-motion"])assert.ok(css.includes(rule));
 assert.ok(html.includes('data-nox-wow-slot="secondary"'));
 assert.ok(!src.includes("fetch("));
 assert.ok(!src.includes("innerHTML"));
 assert.ok(!src.includes("WebSocket("));
});
