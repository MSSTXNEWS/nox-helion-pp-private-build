/* NOX PACK02 -- offline, read-only operations; no host privileges, network, models or files. */
const txt=x=>typeof x==="string"?x:String(x??"");
const ls=s=>txt(s).replace(/\r\n?/g,"\n").split("\n");
const val=s=>JSON.parse(txt(s));
const number=(v,d=0)=>Number.isFinite(Number(v))?Number(v):d;
const bounded=(v,min,max,d)=>Math.min(max,Math.max(min,number(v,d)));
const keys=o=>Object.keys(o??{});
const wordlist=s=>txt(s).match(/[\p{L}\p{N}]+/gu)||[];
const stamp=x=>{const m=/^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$/.exec(x);if(!m||+m[2]>59||+m[3]>59)throw Error("BAD_TIMESTAMP");return ((+m[1]*3600)+(+m[2]*60)+(+m[3]))*1000+(+m[4])};
const fmt=(v,sep=",")=>{const n=Math.max(0,Math.round(v)),s=Math.floor(n/1000);return String(Math.floor(s/3600)).padStart(2,"0")+":"+String(Math.floor(s/60)%60).padStart(2,"0")+":"+String(s%60).padStart(2,"0")+sep+String(n%1000).padStart(3,"0")};
const cues=s=>txt(s).trim().replace(/^WEBVTT[^\n]*\n/i,"").split(/\n\s*\n/).filter(Boolean).map((b,i)=>{const a=ls(b),k=a.findIndex(x=>x.includes("-->"));if(k<0)throw Error("MISSING_TIMECODE");const m=/(\d{2}:\d{2}:\d{2}[,.]\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}[,.]\d{3})/.exec(a[k]);if(!m)throw Error("INVALID_TIMECODE");const start=stamp(m[1]),end=stamp(m[2]);if(end<=start)throw Error("BAD_DURATION");return {n:i+1,start,end,text:a.slice(k+1).join("\n")}});
const printCues=(a,vtt=false)=>(vtt?"WEBVTT\n\n":"")+a.map((c,i)=>(vtt?"":String(i+1)+"\n")+fmt(c.start,vtt?".":",")+" --> "+fmt(c.end,vtt?".":",")+"\n"+c.text).join("\n\n")+"\n";
function csv(s){let rows=[],row=[],cell="",quote=false,closed=false;const z=txt(s).replace(/\r\n?/g,"\n");for(let i=0;i<z.length;i++){const c=z[i];if(c==='"'){if(quote&&z[i+1]==='"'){cell+='"';i++}else if(quote){quote=false;closed=true}else if(!cell&&!closed){quote=true}else throw Error("BAD_CSV_QUOTE")}else if(c===","&&!quote){row.push(cell);cell="";closed=false}else if(c==="\n"&&!quote){if(row.length||cell!==""||closed){row.push(cell);rows.push(row)}row=[];cell="";closed=false}else{if(closed&&!quote)throw Error("BAD_CSV_QUOTE");cell+=c}}if(quote)throw Error("BAD_CSV_QUOTE");if(cell||row.length||closed){row.push(cell);rows.push(row)}if(!rows.length)return [];const h=rows.shift();if(h.some(x=>!x)||new Set(h).size!==h.length)throw Error("INVALID_CSV_HEADER");const parsed=rows.map(r=>{if(r.length!==h.length)throw Error("CSV_WIDTH_MISMATCH");return Object.fromEntries(h.map((k,i)=>[k,r[i]]))});Object.defineProperty(parsed,"columns",{value:h.slice(),enumerable:false});return parsed}
const csvField=(rows,field)=>{if(typeof field!=="string"||!(rows.columns||keys(rows[0])).includes(field))throw Error("UNKNOWN_CSV_FIELD");return field};
function csvOut(a){if(!Array.isArray(a))throw Error("ARRAY_EXPECTED");if(!a.length)return "";const k=keys(a[0]),esc=v=>{const s=txt(v);return /[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s};return [k.map(esc).join(","),...a.map(r=>k.map(x=>esc(r[x])).join(","))].join("\n")}
function flat(o,p="",out={},dep=0){if(dep>20)throw Error("JSON_DEPTH_LIMIT");if(o&&typeof o==="object")for(const [k,v] of Object.entries(o))flat(v,p?p+"."+k:k,out,dep+1);else if(!o||typeof o!=="object")out[p]=o;return out}
const tasklist=s=>ls(s).filter(x=>x.trim()).map((x,i)=>{const m=/^\s*(?:[-*]\s*)?(?:\[(x|X| )\]\s*)?(.*)$/.exec(x),a=m[2].split("|").map(y=>y.trim()),o=Object.fromEntries(a.slice(1).map(y=>y.split("=",2).map(z=>z.trim())).filter(z=>z.length===2));return {id:i+1,title:a[0],done:!!m[1]&&m[1].toLowerCase()==="x",owner:o.owner||"unassigned",status:o.status||"todo",weight:bounded(o.weight,0,10000,1),minutes:bounded(o.minutes,0,100000,0)}});
const base64=s=>{const b=new TextEncoder().encode(s);return btoa(Array.from(b,x=>String.fromCharCode(x)).join(""))};
const unbase=s=>new TextDecoder("utf-8",{fatal:true}).decode(Uint8Array.from(atob(s.trim()),x=>x.charCodeAt(0)));
const hex=s=>Array.from(new TextEncoder().encode(s),x=>x.toString(16).padStart(2,"0")).join("");
const unhex=s=>{const t=s.trim();if(t.length%2||!/^(?:[a-fA-F0-9]{2})*$/.test(t))throw Error("INVALID_HEX");return new TextDecoder("utf-8",{fatal:true}).decode(Uint8Array.from(t.match(/.{2}/g)||[],x=>parseInt(x,16)))};
export const OPS=Object.freeze({
"media.srt.parse":s=>cues(s),
"media.srt.to_vtt":s=>printCues(cues(s),true),
"media.vtt.to_srt":s=>printCues(cues(s)),
"media.subtitles.shift":(s,o)=>{if(o.seconds===undefined||o.seconds===null||!Number.isFinite(Number(o.seconds)))throw Error("SHIFT_NUMBER_REQUIRED");const shift=Number(o.seconds)*1000;return printCues(cues(s).map(c=>{if(c.start+shift<0||c.end+shift<=0)throw Error("SHIFT_BEFORE_ZERO");return {...c,start:c.start+shift,end:c.end+shift}}))},
"media.subtitles.strip":s=>cues(s).map(c=>c.text).join("\n"),
"media.subtitles.search":(s,o)=>cues(s).filter(c=>c.text.toLowerCase().includes(txt(o.term).toLowerCase())),
"media.subtitles.duration":s=>cues(s).reduce((n,c)=>n+c.end-c.start,0)/1000,
"media.subtitles.overlaps":s=>{const a=cues(s);return a.slice(1).flatMap((c,i)=>c.start<a[i].end?[{previous:i+1,current:i+2,ms:a[i].end-c.start}]:[])},
"media.subtitles.renumber":s=>printCues(cues(s)),
"media.transcript.speakers":s=>{let r=Object.create(null);for(const l of ls(s)){const m=/^([^:\n]{1,50}):\s+(.+)$/.exec(l);if(m)r[m[1]]=(r[m[1]]||0)+1}return r},
"docs.words.count":s=>({words:wordlist(s).length,characters:s.length,lines:ls(s).length}),
"docs.paragraphs.list":s=>s.trim().split(/\n\s*\n/).filter(Boolean),
"docs.sentences.split":s=>s.trim().split(/(?<=[.!?])\s+/u).filter(Boolean),
"docs.lines.dedupe":s=>[...new Set(ls(s))].join("\n"),
"docs.whitespace.normalize":s=>ls(s).map(l=>l.trim().replace(/[ \t]+/g," ")).join("\n").replace(/\n{3,}/g,"\n\n"),
"docs.text.titlecase":s=>s.replace(/\p{L}+/gu,x=>x[0].toLocaleUpperCase()+x.slice(1).toLocaleLowerCase()),
"docs.slug.make":s=>s.trim().normalize("NFKD").toLocaleLowerCase().replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9а-яё]+/gu,"-").replace(/^-|-$/g,""),
"docs.urls.extract":s=>[...new Set(s.match(/https?:\/\/[^\s<>"']+/g)||[])],
"docs.emails.extract":s=>[...new Set(s.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi)||[])],
"docs.text.chunks":(s,o)=>{let a=[],n=bounded(o.size,100,4000,400),parts=Array.from(s);for(let i=0;i<parts.length;i+=n)a.push(parts.slice(i,i+n).join(""));return a},
"data.csv.parse":s=>csv(s),
"data.csv.stringify":s=>csvOut(val(s)),
"data.csv.select":(s,o)=>{const data=csv(s),k=txt(o.fields).split(",").map(x=>x.trim()).filter(Boolean),headers=data.columns||[];if(!k.length||new Set(k).size!==k.length||k.some(x=>!headers.includes(x)))throw Error("UNKNOWN_CSV_FIELD");const selected=data.map(r=>Object.fromEntries(k.map(x=>[x,r[x]])));Object.defineProperty(selected,"columns",{value:k,enumerable:false});return selected},
"data.csv.filter":(s,o)=>{const rows=csv(s),field=csvField(rows,o.field);return rows.filter(r=>txt(r[field]).toLocaleLowerCase().includes(txt(o.term).toLocaleLowerCase()))},
"data.csv.sort":(s,o)=>{const rows=csv(s),field=csvField(rows,o.field);return rows.sort((a,b)=>txt(a[field]).localeCompare(txt(b[field]),"ru",{numeric:true})*(o.desc?-1:1))},
"data.csv.dedupe":s=>[...new Map(csv(s).map(x=>[JSON.stringify(x),x])).values()],
"data.csv.stats":s=>{const a=csv(s);return {rows:a.length,columns:a.columns||keys(a[0]),emptyCells:a.reduce((n,r)=>n+Object.values(r).filter(x=>x==="").length,0)}},
"data.json.pretty":s=>JSON.stringify(val(s),null,2),
"data.json.flatten":s=>flat(val(s)),
"data.json.keys":s=>keys(val(s)),
"dev.diff.lines":(s,o)=>{const a=ls(s),b=ls(txt(o.compare));return Array.from({length:Math.max(a.length,b.length)},(_,i)=>a[i]===b[i]?null:{line:i+1,before:a[i]??null,after:b[i]??null}).filter(Boolean)},
"dev.json.compare":(s,o)=>{const a=flat(val(s)),b=flat(val(txt(o.compare)));return [...new Set([...keys(a),...keys(b)])].filter(k=>JSON.stringify(a[k])!==JSON.stringify(b[k])).map(k=>({path:k,before:a[k]??null,after:b[k]??null}))},
"dev.json.validate":s=>{try{val(s);return {valid:true}}catch{return {valid:false,error:"INVALID_JSON"}}},
"dev.url.inspect":s=>{const u=new URL(s.trim());if(!["https:","http:"].includes(u.protocol))throw Error("HTTP_ONLY");return {scheme:u.protocol,host:u.hostname,path:u.pathname,query:[...u.searchParams],fragment:u.hash}},
"dev.url.query_encode":s=>{const o=val(s);if(!o||typeof o!=="object"||Array.isArray(o))throw Error("OBJECT_REQUIRED");return new URLSearchParams(Object.entries(o).map(([k,v])=>[k,txt(v)])).toString()},
"dev.url.query_decode":s=>Object.fromEntries(new URLSearchParams(s.trim().replace(/^\?/,""))),
"dev.base64.encode":s=>base64(s),
"dev.base64.decode":s=>unbase(s),
"dev.hex.encode":s=>hex(s),
"dev.hex.decode":s=>unhex(s),
"workflow.checklist.parse":s=>tasklist(s),
"workflow.checklist.format":s=>tasklist(s).map(t=>"- ["+(t.done?"x":" ")+"] "+t.title).join("\n"),
"workflow.tasks.kanban":s=>{let r={todo:[],doing:[],done:[]};for(const t of tasklist(s))r[t.done?"done":t.status==="doing"?"doing":"todo"].push(t);return r},
"workflow.tasks.sort":s=>tasklist(s).sort((a,b)=>b.weight-a.weight||a.id-b.id),
"workflow.tasks.group":s=>{let r=Object.create(null);for(const t of tasklist(s))(r[t.owner]??=[]).push(t);return r},
"workflow.tasks.duration":s=>({minutes:tasklist(s).reduce((n,t)=>n+t.minutes,0)}),
"workflow.progress.weighted":s=>{const a=tasklist(s),w=a.reduce((n,t)=>n+t.weight,0);return {weightedPercent:w?Math.round(10000*a.filter(t=>t.done).reduce((n,t)=>n+t.weight,0)/w)/100:null,completed:a.filter(t=>t.done).length,total:a.length}},
"workflow.receipt.inspect":s=>{const o=val(s);return {hasRunId:typeof o.run_id==="string"&&o.run_id.length>1,sha256Valid:/^[a-f0-9]{64}$/i.test(o.sha256??o.post_sha256??""),fields:keys(o)}},
"workflow.manifest.compare":(s,o)=>{const a=val(s),b=val(txt(o.compare)),ka=new Set(keys(a)),kb=new Set(keys(b));return {missing:[...ka].filter(k=>!kb.has(k)),added:[...kb].filter(k=>!ka.has(k)),changed:[...ka].filter(k=>kb.has(k)&&JSON.stringify(a[k])!==JSON.stringify(b[k]))}},
"workflow.runid.validate":s=>({valid:/^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$/.test(s.trim())})
});
export const IDS=Object.freeze(keys(OPS));
if(IDS.length!==50)throw Error("FIFTY_FUNCTIONS_REQUIRED");
export function execute(id,input,options={}){
 if(typeof id!=="string"||!Object.prototype.hasOwnProperty.call(OPS,id))throw Error("UNKNOWN_FUNCTION");
 if(typeof input!=="string"||input.length>100000)throw Error("INPUT_SIZE");
 if(!options||typeof options!=="object"||Array.isArray(options))throw Error("OPTIONS_INVALID");
 const result=OPS[id](input,options),data=JSON.stringify(result);
 if(data===undefined||data.length>200000)throw Error("OUTPUT_SIZE");
 return {id,status:"OK",result};
}