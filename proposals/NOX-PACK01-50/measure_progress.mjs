/* NOX V16: evidence-derived source route progress only (NOT product readiness). */
import {readFileSync} from "node:fs";
const map=JSON.parse(readFileSync(new URL("./owner-binding-map.json",import.meta.url),"utf8"));
const weights={1:.20,2:.25,3:.20,4:.25,5:.10};
const owners={};
for(let owner=1;owner<=6;owner++){
  const routes=map.routes.filter(x=>x.owner===owner);
  const withSource=routes.filter(x=>typeof x.sourceBinding==="string"&&x.sourceBinding.length>0);
  const accepted=routes.filter(x=>x.releaseAccepted===true);
  owners[owner]={sourceMethods:withSource.length,scopeRoutes:routes.length,
    sourceCoveragePercent:routes.length?Math.round(10000*withSource.length/routes.length)/100:null,
    sameExeAccepted:accepted.length,stage:owner===6?"HOST_INTEGRATION_HOLD":"OWNER_SOURCE_CANDIDATE"};
}
const weightedSourcePct=Math.round(100*(Object.entries(weights)
  .reduce((sum,[id,w])=>sum+w*(owners[id].sourceCoveragePercent||0),0)))/100;
const accepted=map.routes.filter(x=>x.releaseAccepted===true).length;
const summary={run:"NOX-PACK01-FINAL18-20261028",scope:"FIFTY_ROUTE_SOURCE_COVERAGE_NOT_TOTAL_PROJECT",
  all:map.routes.length,sourceBound:map.routes.filter(x=>x.sourceBinding).length,
  sourceCoveragePercent:Math.round(10000*map.routes.filter(x=>x.sourceBinding).length/map.routes.length)/100,
  weightedSourceCoveragePercent:weightedSourcePct,
  owners,executor7:{sourceCoveragePercent:null,sameExeAccepted:null,stage:"WINDOWS_FINAL_QA_NOT_RUN"},
  finalExeAccepted:accepted,
  acceptedEvidencePercent:Math.round(10000*accepted/map.routes.length)/100,
  remaining:map.routes.filter(x=>!x.sourceBinding).map(x=>({routeId:x.routeId,owner:x.owner,taskId:x.taskId})),
  release:"BLOCKED",notes:[
    "Source method coverage is not proof of executable integration.",
    "Even 100% source mapping does not prove every route is usable.",
    "Actual V16 release readiness remains N/D until canonical all-feature denominator and E07 same-SHA QA."
  ]
};
if(summary.all!==50||summary.sourceBound!==37||summary.remaining.length!==13||summary.finalExeAccepted!==0)
 throw Error("PROGRESS_LEDGER_DRIFT");
console.log(JSON.stringify(summary,null,2));
