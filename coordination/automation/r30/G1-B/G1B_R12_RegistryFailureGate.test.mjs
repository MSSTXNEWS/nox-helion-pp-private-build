// G1-B P01 SOURCE-ONLY independent negative regression. Takes a candidate .nsi path.
// Expected RED for R10 (5 unguarded HKCU writes). Does NOT execute NSIS/installer.
import { readFileSync } from "node:fs";
const file=process.argv[2];
if (!file) throw Error("Usage: node G1B_R12_RegistryFailureGate.test.mjs candidate.nsi");
const source=readFileSync(file,"utf8");
const start=source.indexOf("WriteRegStr HKCU");
const end=source.indexOf('SetOutPath "$INSTDIR"',start);
if(start<0||end<=start) throw Error("P01_REGISTRY_WINDOW_UNRESOLVED");
const lines=source.slice(start,end).split(/\r?\n/);
const pos=lines.flatMap((line,i)=>/^\s*WriteReg(?:Str|DWORD)\s+HKCU\b/i.test(line)?[i]:[]);
if(pos.length!==5) throw Error("P01_REGISTRY_WRITE_CARDINALITY_CHANGED:"+pos.length);
const unsafe=pos.filter(i=>!/\bClearErrors\b/.test((lines[i-1]||""))
  ||!/\bIfErrors\b/.test((lines[i+1]||"")));
if(unsafe.length) throw Error("P01_INSTALL_REGISTRY_WRITE_UNGUARDED:"+unsafe.length+"/"+pos.length);
console.log("P01_REGISTRY_WRITE_GUARD_SOURCE_PASS (does not prove transaction recovery)");
