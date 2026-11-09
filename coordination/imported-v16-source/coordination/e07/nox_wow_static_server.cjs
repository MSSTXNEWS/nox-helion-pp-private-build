/* NOX WOW CI-only static server, correct .mjs MIME across Windows and Linux.
 * Loopback only; no API, state, writes or external proxy. */
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const root=process.cwd();
const mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8',
 '.js':'text/javascript; charset=utf-8','.mjs':'text/javascript; charset=utf-8',
 '.json':'application/json','.svg':'image/svg+xml','.png':'image/png',
 '.jpg':'image/jpeg','.woff':'font/woff','.woff2':'font/woff2'};
http.createServer((req,res)=>{
 let pathname;
 try{pathname=decodeURIComponent(new URL(req.url,'http://127.0.0.1').pathname);}
 catch{res.writeHead(400);return res.end();}
 const location=path.resolve(root,'.'+pathname);
 if(location!==root&&!location.startsWith(root+path.sep)){
  res.writeHead(403);return res.end();
 }
 fs.stat(location,(err,st)=>{
  if(err||!st.isFile()){res.writeHead(404);return res.end();}
  res.writeHead(200,{'Content-Type':mime[path.extname(location).toLowerCase()]||'application/octet-stream',
   'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});
  fs.createReadStream(location).pipe(res);
 });
}).listen(8765,'127.0.0.1',()=>console.log('NOX WOW localhost static server ready'));
