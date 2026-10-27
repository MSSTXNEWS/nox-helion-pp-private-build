import test from "node:test";
import assert from "node:assert/strict";
import {catalog} from "./catalog.mjs";
import {execute,IDS} from "./ops.mjs";
import {mountPack02} from "./panel.mjs";

const S="1\n00:00:01,000 --> 00:00:02,500\nHola\n\n2\n00:00:02,000 --> 00:00:04,000\nMundo";
const V="WEBVTT\n\n00:00:01.000 --> 00:00:02.500\nHola\n\n00:00:02.000 --> 00:00:04.000\nMundo";
const T="Anna: Hola\nBob: Mundo\nAnna: Adios";
const DOC="Hello. Привет мир!\n\nHello.";
const CSV='name,count,note\nAlice,2,"say, ""hi"""\nBob,3,World\nAlice,2,"say, ""hi"""';
const CHECK="- [x] Done | owner=1 | weight=3 | minutes=30\n- [ ] Pending | owner=2 | weight=1 | minutes=20 | status=doing";
const J='{"a":{"b":2},"flag":false}';
const COMPARISON='{"a":{"b":3},"flag":false}';
const VECTORS=[
["media.srt.parse",S,{},r=>assert.deepEqual(r[0],{n:1,start:1000,end:2500,text:"Hola"})],
["media.srt.to_vtt",S,{},r=>assert.ok(r.startsWith("WEBVTT\n\n00:00:01.000 --> 00:00:02.500"))],
["media.vtt.to_srt",V,{},r=>assert.ok(r.startsWith("1\n00:00:01,000 --> 00:00:02,500"))],
["media.subtitles.shift",S,{seconds:1},r=>assert.ok(r.includes("00:00:02,000 --> 00:00:03,500"))],
["media.subtitles.strip",S,{},r=>assert.equal(r,"Hola\nMundo")],
["media.subtitles.search",S,{term:"mundo"},r=>assert.equal(r.length,1)],
["media.subtitles.duration",S,{},r=>assert.equal(r,3.5)],
["media.subtitles.overlaps",S,{},r=>assert.deepEqual(r,[{previous:1,current:2,ms:500}])],
["media.subtitles.renumber",S,{},r=>assert.ok(r.includes("\n\n2\n00:00:02,000"))],
["media.transcript.speakers",T,{},r=>assert.equal(r.Anna,2)],
["docs.words.count",DOC,{},r=>{assert.equal(r.words,4);assert.equal(r.lines,3)}],
["docs.paragraphs.list",DOC,{},r=>assert.equal(r.length,2)],
["docs.sentences.split","One. Two! Three?",{},r=>assert.deepEqual(r,["One.","Two!","Three?"])],
["docs.lines.dedupe","a\nb\na",{},r=>assert.equal(r,"a\nb")],
["docs.whitespace.normalize"," A   B \n\n\n C ",{},r=>assert.equal(r,"A B\n\nC")],
["docs.text.titlecase","heLLO wORLD",{},r=>assert.equal(r,"Hello World")],
["docs.slug.make","Hello, World!",{},r=>assert.equal(r,"hello-world")],
["docs.urls.extract","Visit https://example.org/a and https://example.org/a",{},r=>assert.deepEqual(r,["https://example.org/a"])],
["docs.emails.extract","a@b.co a@b.co c@d.es",{},r=>assert.deepEqual(r,["a@b.co","c@d.es"])],
["docs.text.chunks","a".repeat(240),{size:100},r=>assert.deepEqual(r.map(x=>x.length),[100,100,40])],
["data.csv.parse",CSV,{},r=>{assert.equal(r.length,3);assert.equal(r[0].note,'say, "hi"')}],
["data.csv.stringify",'[{"name":"A","note":"x,y"}]',{},r=>assert.equal(r,'name,note\nA,"x,y"')],
["data.csv.select",CSV,{fields:"name,note"},r=>assert.deepEqual(Object.keys(r[0]),["name","note"])],
["data.csv.filter",CSV,{field:"name",term:"Bob"},r=>assert.deepEqual(r.map(x=>x.name),["Bob"])],
["data.csv.sort",CSV,{field:"count",desc:true},r=>assert.equal(r[0].name,"Bob")],
["data.csv.dedupe",CSV,{},r=>assert.equal(r.length,2)],
["data.csv.stats",CSV,{},r=>assert.deepEqual(r,{rows:3,columns:["name","count","note"],emptyCells:0})],
["data.json.pretty",J,{},r=>assert.deepEqual(JSON.parse(r),JSON.parse(J))],
["data.json.flatten",J,{},r=>assert.deepEqual(r,{"a.b":2,flag:false})],
["data.json.keys",J,{},r=>assert.deepEqual(r,["a","flag"])],
["dev.diff.lines","one\ntwo",{compare:"one\nthree"},r=>assert.deepEqual(r,[{line:2,before:"two",after:"three"}])],
["dev.json.compare",J,{compare:COMPARISON},r=>assert.deepEqual(r,[{path:"a.b",before:2,after:3}])],
["dev.json.validate","{broken",{},r=>assert.equal(r.valid,false)],
["dev.url.inspect","https://example.com/a?x=1#top",{},r=>assert.deepEqual(r,{scheme:"https:",host:"example.com",path:"/a",query:[["x","1"]],fragment:"#top"})],
["dev.url.query_encode",'{"x":"hello world"}',{},r=>assert.equal(r,"x=hello+world")],
["dev.url.query_decode","x=2&name=Anna",{},r=>assert.deepEqual(r,{x:"2",name:"Anna"})],
["dev.base64.encode","Привет",{},r=>assert.equal(r,"0J/RgNC40LLQtdGC")],
["dev.base64.decode","0J/RgNC40LLQtdGC",{},r=>assert.equal(r,"Привет")],
["dev.hex.encode","Hi",{},r=>assert.equal(r,"4869")],
["dev.hex.decode","4869",{},r=>assert.equal(r,"Hi")],
["workflow.checklist.parse",CHECK,{},r=>{assert.equal(r.length,2);assert.equal(r[0].done,true);assert.equal(r[1].owner,"2")}],
["workflow.checklist.format",CHECK,{},r=>assert.ok(r.includes("- [x] Done"))],
["workflow.tasks.kanban",CHECK,{},r=>{assert.equal(r.done.length,1);assert.equal(r.doing.length,1)}],
["workflow.tasks.sort",CHECK,{},r=>assert.equal(r[0].weight,3)],
["workflow.tasks.group",CHECK,{},r=>{assert.equal(r["1"].length,1);assert.equal(r["2"].length,1)}],
["workflow.tasks.duration",CHECK,{},r=>assert.equal(r.minutes,50)],
["workflow.progress.weighted",CHECK,{},r=>assert.deepEqual(r,{weightedPercent:75,completed:1,total:2})],
["workflow.receipt.inspect",'{"run_id":"A-10","sha256":"'+("a".repeat(64))+'"}',{},r=>{assert.equal(r.hasRunId,true);assert.equal(r.sha256Valid,true)}],
["workflow.manifest.compare",'{"a":1,"b":2}',{compare:'{"a":3,"c":4}'},r=>assert.deepEqual(r,{missing:["b"],added:["c"],changed:["a"]})],
["workflow.runid.validate","NOX-V16-RUN42",{},r=>assert.equal(r.valid,true)]
];
test("all 50 unique routes have exact output contracts and names",()=>{
 assert.equal(VECTORS.length,50);
 assert.deepEqual(VECTORS.map(x=>x[0]),IDS);
 assert.deepEqual(catalog.actions.map(x=>x.routeId),IDS);
});
for(const [id,input,options,check] of VECTORS)test("GOLDEN "+id,()=>{
 const output=execute(id,input,options);assert.equal(output.status,"OK");check(output.result);
});
test("CSV rejects unbalanced quotes",()=>assert.throws(()=>execute("data.csv.parse",'a\n"bad'),/BAD_CSV_QUOTE/));
test("SRT rejects bad end time",()=>assert.throws(()=>execute("media.srt.parse","1\n00:00:02,000 --> 00:00:01,000\nbad"),/BAD_DURATION/));
test("URL inspector rejects file protocol",()=>assert.throws(()=>execute("dev.url.inspect","file:///tmp/x"),/HTTP_ONLY/));
test("invalid JS options fail closed",()=>assert.throws(()=>execute("docs.words.count","Hi",[]),/OPTIONS_INVALID/));
test("unknown routes fail closed",()=>assert.throws(()=>execute("windows.delete","anything"),/UNKNOWN_FUNCTION/));
test("oversized input fails closed",()=>assert.throws(()=>execute("docs.words.count","a".repeat(100001)),/INPUT_SIZE/));

class FakeNode {
 constructor(tag){this.tag=tag;this.nodeType=1;this.children=[];this.events={};this.attrs={};this.dataset={};this.textContent="";this.value="";this.hidden=false;this.disabled=false;this.className="";}
 append(...c){this.children.push(...c)}
 setAttribute(k,v){this.attrs[k]=v}
 getAttribute(k){return this.attrs[k]}
 addEventListener(k,v){this.events[k]=v}
 click(){this.events.click?.()}
 closest(){return null}
 remove(){this.removed=true}
 findTag(name){const todo=[this];while(todo.length){let z=todo.shift();if(z.tag===name)return z;todo.push(...z.children)}return null}
};
test("secondary UI: 50 buttons are real, selecting and executing writes result",()=>{
 const original=globalThis.document;
 globalThis.document={createElement:tag=>new FakeNode(tag)};
 try{
  const root=new FakeNode("main"),panel=mountPack02(root);
  assert.equal(panel.getCount(),50);
  const frame=root.children[0],grid=frame.children[2],tools=grid.children;
  assert.equal(tools.length,50);
  const entry=tools.find(x=>x.dataset.tool==="dev.json.pretty");
  entry.click();assert.equal(panel.getSelected(),"dev.json.pretty");
  const space=frame.children[3],editor=space.children[1],opts=space.children[2],run=space.children[3],status=space.children[4],result=space.children[5];
  editor.value='{"a":1}';opts.value="{}";run.click();
  assert.deepEqual(JSON.parse(result.textContent),{a:1});
  assert.ok(status.textContent.includes("OK"));
  editor.value="<script>alert(1)</script>";run.click();
  assert.ok(status.textContent.includes("HOLD"));
  panel.dispose();assert.equal(frame.removed,true);
 }finally{globalThis.document=original}
});
test("HOME cannot mount panel",()=>{
 const root=new FakeNode("main");root.closest=()=>({nodeType:1});
 assert.throws(()=>mountPack02(root),/D02_HOME_LOCK/);
});
