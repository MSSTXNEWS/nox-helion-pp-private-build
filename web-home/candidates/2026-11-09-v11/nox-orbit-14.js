/* NOX HELION HOME — real PBR planets and NASA Bennu with 9 lighting scenes,
   three independent understated choice dots, original NOX D02/functional routes preserved. */
(()=>{const s=document.createElement("script");s.src="./nox-orbit-original.js";s.onload=()=>{
const styles=["./nox-appearance.css","./vendor/nox-liquid-glass/liquid-glass.css","./nox-glass-home.css","./nox-glass-film.css","./nox-world-themes.css","./nox-cinematic-scenes.css","./nox-clear-cinema.css","./nox-selection-v6.css","./nox-selection-corrective-v7.css"];
for(const href of styles){const l=document.createElement("link");l.rel="stylesheet";l.href=href;document.head.appendChild(l);}
 // Keep the approved corrective sheet after all imported legacy sheets without duplicating it.
 const approvedSheet=[...document.querySelectorAll('link[rel="stylesheet"]')].find(x=>x.getAttribute('href')?.includes("nox-home-recovery.css"));
 if(approvedSheet)document.head.appendChild(approvedSheet);

import("./nox-style-sync.mjs").then(()=>import("./nox-cinematic-director.mjs")).catch(e=>console.error("NOX_THEME_DIRECTOR",e));
import("./nox-engines/physical-worlds-v7.mjs").catch(e=>console.error("NOX_PHYSICAL_WORLDS_V7",e));
import("./nox-glass-init.mjs").catch(e=>console.error("NOX_GLASS",e));
if(new URLSearchParams(location.search).has("nox_visual_audit"))import("./nox-visual-audit-v7.mjs").catch(e=>console.error("NOX_VISUAL_AUDIT",e));
};document.body.appendChild(s)})();