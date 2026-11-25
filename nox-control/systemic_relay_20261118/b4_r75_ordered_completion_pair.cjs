'use strict';
const {classifyCompletionPair}=require('./b4_r74_completion_pair.cjs');
// Sequential browser acceptance requires a common authenticated monotonic clock.
// Different time origins cannot establish order. Never rebase measured times or
// infer a cross-clock witness from candidate data. Such pairs remain HOLD.
function classifyOrderedCompletionPair(turns,quality){
 const hold=()=>Object.freeze({status:'HOLD_COMPLETION_PAIR',samples:Object.freeze([]),native_accepted:false});
 try{
  const result=classifyCompletionPair(turns,quality);
  if(result.status!=='VERIFIED_COMPLETION_PAIR')return result;
  const [a,b]=turns.map(x=>x.trusted.proof);
  if(a.clock_id!==b.clock_id)return hold();
  return result;
 }catch{return hold();}
}
module.exports={classifyOrderedCompletionPair};
