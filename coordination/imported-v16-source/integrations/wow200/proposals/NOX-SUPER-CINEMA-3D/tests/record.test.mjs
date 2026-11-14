import test from "node:test";
import assert from "node:assert/strict";
import {recordCinemaClip} from "../src/record.mjs";
test("real capture requires browser canvas/MediaRecorder and explicit invocation",async()=>{
 await assert.rejects(recordCinemaClip(null),/WEBM_RECORDER_NOT_AVAILABLE/);
 await assert.rejects(recordCinemaClip({},{}),/WEBM_RECORDER_NOT_AVAILABLE/);
});
test("duration/FPS limits bound recording",async()=>{
 const canvas={captureStream:()=>({getTracks:()=>[]})};
 function Recorder(){}
 await assert.rejects(recordCinemaClip(canvas,{seconds:30,Recorder}),/RECORD_LIMIT_INVALID/);
 await assert.rejects(recordCinemaClip(canvas,{seconds:8,fps:60,Recorder}),/RECORD_LIMIT_INVALID/);
});
test("user-directed canvas capture emits a genuine nonempty WebM Blob",async()=>{
 let stopped=false,started=false,frames=0;
 const canvas={captureStream(fps){frames=fps;return {getTracks:()=>[{stop(){stopped=true}}]}}};
 class MockRecorder{
  constructor(){this.state="inactive"}
  static isTypeSupported(x){return x.startsWith("video/webm")}
  start(){started=true;this.state="recording";this.ondataavailable({data:new Blob(["encoded-webm-video"])});}
  stop(){this.state="inactive";this.onstop()}
 }
 const clip=await recordCinemaClip(canvas,{seconds:3,fps:12,Recorder:MockRecorder,
  timer:fn=>{fn();return 1},clear:()=>{}});
 assert.equal(started,true);assert.equal(frames,12);assert.equal(stopped,true);
 assert.equal(clip.size,"encoded-webm-video".length);assert.equal(clip.format,"WEBM_LOCAL_NOT_UPLOADED");
 assert.equal(clip.blob.size,clip.size);
});
test("WebM codec must actually be supported",async()=>{
 const canvas={captureStream:()=>({getTracks:()=>[]})};
 class NoWebM{static isTypeSupported(){return false}}
 await assert.rejects(recordCinemaClip(canvas,{seconds:4,Recorder:NoWebM}),/WEBM_CODEC_NOT_AVAILABLE/);
});
