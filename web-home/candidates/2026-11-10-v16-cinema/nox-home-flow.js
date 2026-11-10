/* NOX HELION V18 — HOME flow layout companion, reconstructed from missing source.
   Decorative visual system only. No fabricated telemetry, progress or model activity.
   One static SVG graph with gentle CSS motion; zero additional GPU renderers. */
(()=>{'use strict';
 if(window.NOX_HOME_FLOW)return;
 const network=document.querySelector('.nox-flow-network');
 if(!network||document.body.dataset.page!=='index')return;
 const svgNS='http://www.w3.org/2000/svg';
 const paths=network.querySelector('.nox-flow-links');
 const nodes=network.querySelector('.nox-flow-nodes');
 if(!paths||!nodes)return;
 const points=[[16,86],[51,38],[53,135],[93,84],[136,32],[138,139],[197,69],[232,118]];
 const edges=[[0,1],[0,2],[0,3],[1,3],[1,4],[2,3],[2,5],[3,4],[3,5],[3,6],[4,6],[5,6],[5,7],[6,7]];
 function el(tag,attrs){const e=document.createElementNS(svgNS,tag);for(const [key,value] of Object.entries(attrs))e.setAttribute(key,String(value));return e}
 for(const [a,b] of edges){const [x1,y1]=points[a],[x2,y2]=points[b];const line=el('path',{d:'M'+x1+','+y1+'L'+x2+','+y2,class:'nox-flow-connection'});paths.appendChild(line)}
 for(let i=0;i<points.length;i++){
  const [cx,cy]=points[i];const g=el('g',{class:'nox-flow-point',transform:'translate('+cx+' '+cy+')'});
  g.style.setProperty('--point-delay',String(((i*7)%11)*-0.43)+'s');
  g.appendChild(el('circle',{r:7.2,class:'nox-flow-point-halo'}));
  g.appendChild(el('circle',{r:2.5,class:'nox-flow-point-core'}));
  nodes.appendChild(g);
 }
 const reduce=matchMedia('(prefers-reduced-motion: reduce)');
 function update(){network.classList.toggle('nox-flow-still',document.hidden||reduce.matches)}
 document.addEventListener('visibilitychange',update,{passive:true});
 if(reduce.addEventListener)reduce.addEventListener('change',update);else if(reduce.addListener)reduce.addListener(update);
 update();
 window.NOX_HOME_FLOW=Object.freeze({type:'DECORATIVE_ONLY',nodeCount:points.length,linkCount:edges.length,get paused(){return document.hidden||reduce.matches}});
})();