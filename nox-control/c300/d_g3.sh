echo "C300: d_g3"
export PATH=/workspace/nox/tools/node/bin:$PATH; cd /workspace/nox/web/build
mkdir -p /workspace/nox/web/site/vendor/jupyterlite && cp -rn jl_out/. /workspace/nox/web/site/vendor/jupyterlite/ && echo jl copied
cat > dbg.mjs <<'X'
import {build} from '/workspace/nox/web/build/node_modules/esbuild/lib/main.js';
for (const p of ['@arwes/frames','@arwes/animated','circuitsvis','@cosmos.gl/graph','@schedule-x/calendar','vis-timeline','@rjsf/core']) {
 try { await build({stdin:{contents:`export * from '${p}'`,resolveDir:'/workspace/nox/web/build'},bundle:true,write:false,format:'esm',logLevel:'silent',platform:'browser',define:{'process.env.NODE_ENV':'"production"'}}); console.log('OK',p);} catch(e){ console.log('ERR',p,(e.errors||[]).slice(0,2).map(x=>x.text+' @'+(x.location&&x.location.file)).join(' | ').slice(0,300)); }
}
X
node dbg.mjs
N=node_modules; ls $N/maplibre-gl/dist | head; ls $N/@blocknote/core/ $N/@blocknote/core/dist 2>/dev/null| head -20; ls $N/katex/dist | head -20; ls $N/vidstack/player/styles 2>/dev/null | head
ls $N/@arwes/frames; cat $N/@arwes/frames/package.json | grep -E '"(main|module|exports|type)"' | head
