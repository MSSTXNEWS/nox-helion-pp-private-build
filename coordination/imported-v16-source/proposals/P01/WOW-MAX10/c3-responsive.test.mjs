import test from "node:test";
import assert from "node:assert/strict";
import {viewportClass,installP01Adaptive} from "./p01-responsive.mjs";
test("C3 320px",()=>assert.equal(viewportClass(320,568),"compact"));
test("C3 390px",()=>assert.equal(viewportClass(390,844),"phone"));
test("C3 800x480",()=>assert.equal(viewportClass(800,480),"short"));
test("C3 1920px",()=>assert.equal(viewportClass(1920,1080),"wide"));
test("C3 4k",()=>assert.equal(viewportClass(3840,2160),"wide"));
test("C3 invalid geometry",()=>assert.equal(viewportClass(-1,0),"unknown"));
function fixture(){
 const listeners=new Map(),motion=new Map();
 const mq={matches:false,addEventListener:(k,v)=>motion.set(k,v),removeEventListener:k=>motion.delete(k)};
 const win={innerWidth:800,innerHeight:480,devicePixelRatio:1.5,matchMedia:()=>mq,
  addEventListener:(k,v)=>listeners.set(k,v),removeEventListener:k=>listeners.delete(k)};
 const root={nodeType:1,dataset:{},ownerDocument:{defaultView:win}};
 return {root,win,mq,listeners,motion};
}
test("C3 original root only",()=>{const x=fixture();const doc=x.root.ownerDocument;
 const h=installP01Adaptive(x.root);assert.equal(x.root.ownerDocument,doc);h.destroy();});
test("C3 DPI metadata 150 percent",()=>{const x=fixture();const h=installP01Adaptive(x.root);
 assert.equal(x.root.dataset.noxP01Dpi,"150");h.destroy();});
test("C3 reduced motion change",()=>{const x=fixture();const h=installP01Adaptive(x.root);
 x.mq.matches=true;x.motion.get("change")();assert.equal(x.root.dataset.noxP01Motion,"reduced");h.destroy();});
test("C3 restore data and handlers",()=>{const x=fixture();x.root.dataset.noxP01Layout="owner";
 const h=installP01Adaptive(x.root);h.destroy();assert.equal(x.root.dataset.noxP01Layout,"owner");
 assert.equal(x.listeners.size,0);assert.equal(x.motion.size,0);});

test("C3 768px tablet / 1024px desktop class",()=>{
 assert.equal(viewportClass(768,1024),"tablet");
 assert.equal(viewportClass(1024,768),"tablet");
});
test("C3 DPI 200% and viewport switch remain metadata only",()=>{
 const x=fixture();x.win.devicePixelRatio=2;
 const h=installP01Adaptive(x.root);
 assert.equal(x.root.dataset.noxP01Dpi,"200");
 x.win.innerWidth=390;x.win.innerHeight=844;x.listeners.get("resize")();
 assert.equal(x.root.dataset.noxP01Layout,"phone");
 assert.equal(x.root.dataset.noxP01Orientation,"portrait");
 h.destroy();
 assert.equal(Object.hasOwn(x.root.dataset,"noxP01Dpi"),false);
});
