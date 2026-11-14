/* Local opt-in WebM capture from an already running NOX WebGL canvas.
 * No audio, upload, background capture or autoplay. Direct user gesture only.
 */
export async function recordCinemaClip(canvas,{seconds=8,fps=24,Recorder=globalThis.MediaRecorder,
 timer=globalThis.setTimeout,clear=globalThis.clearTimeout}={}){
 if(!canvas||typeof canvas.captureStream!=="function"||typeof Recorder!=="function")
  throw Error("WEBM_RECORDER_NOT_AVAILABLE");
 if(!Number.isInteger(seconds)||seconds<3||seconds>20||!Number.isInteger(fps)||fps<8||fps>30)
  throw Error("RECORD_LIMIT_INVALID");
 const mime=["video/webm;codecs=vp9","video/webm;codecs=vp8","video/webm"]
  .find(x=>typeof Recorder.isTypeSupported!=="function"||Recorder.isTypeSupported(x));
 if(!mime)throw Error("WEBM_CODEC_NOT_AVAILABLE");
 const stream=canvas.captureStream(fps);
 if(!stream||typeof stream.getTracks!=="function")throw Error("INVALID_CAPTURE_STREAM");
 let rec;
 try{rec=new Recorder(stream,{mimeType:mime,videoBitsPerSecond:3_200_000})}
 catch(e){stream.getTracks().forEach(t=>t.stop?.());throw Error("VIDEO_RECORDER_START_FAILED")}
 return await new Promise((resolve,reject)=>{
  const chunks=[];let bytes=0,settled=false,timerId=null;
  function cleanup(){if(timerId!==null)clear(timerId);stream.getTracks().forEach(t=>t.stop?.())}
  function fail(reason){if(settled)return;settled=true;cleanup();reject(Error(reason))}
  rec.ondataavailable=e=>{
   if(!e?.data||e.data.size<=0)return;
   bytes+=e.data.size;
   if(bytes>48*1024*1024){try{if(rec.state!=="inactive")rec.stop()}catch{}fail("VIDEO_CAPTURE_TOO_LARGE");return}
   chunks.push(e.data);
  };
  rec.onerror=()=>fail("VIDEO_RECORDING_FAILED");
  rec.onstop=()=>{
   if(settled)return;
   cleanup();settled=true;
   if(!bytes)return reject(Error("VIDEO_CAPTURE_EMPTY"));
   resolve(Object.freeze({blob:new Blob(chunks,{type:mime}),mimeType:mime,
     size:bytes,seconds,format:"WEBM_LOCAL_NOT_UPLOADED"}));
  };
  try{
   rec.start(250);
   timerId=timer(()=>{try{if(rec.state!=="inactive")rec.stop()}catch{fail("VIDEO_STOP_FAILED")}},seconds*1000);
  }catch{fail("VIDEO_RECORDING_FAILED")}
 });
}
