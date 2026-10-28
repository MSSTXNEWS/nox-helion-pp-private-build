#!/usr/bin/env python3
"""R08 temporary runner-only compiler correction. Verifies exact original bytes.
Never alters original SHA pinned ZIP or persistent user files.
"""
from pathlib import Path
import hashlib, sys, json, re, difflib

if len(sys.argv)!=2: raise SystemExit('expected exactly one extracted R11 root')
root=Path(sys.argv[1]).resolve()
paths={
 'MainWindow.xaml.cs':'b4c20c71380c63cec07c7ea4017c4f44f55077a985d2bfec42ecfe5f1a2b8825',
 'Packages/P02/OpenAI/OpenAiResponsesProvider.cs':'968860590cb112b76b6399ad72d868269eebe6daec545bfead94fecd3e161449',
 'Packages/P03/module/ComponentInstaller.cs':'2ae39faf5a19dd42a9787e1f3b98aaeb8d6efb2cd5165a9c6e59183daef07bf3',
 'Packages/P03/module/ModelCenterEvent.cs':'94e15e68c6bdefc709121ab0b23a8379ffb84bc5d70e9ea40c284b7812a7f3fb',
 'Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs':'ccd0fb325eb8a250323f5aa17c8e7bdad0d281eb681ad381c96ee3a99498814e',
}
receipts=[]
for rel,expected in paths.items():
 p=root/rel
 original=p.read_bytes(); pre=hashlib.sha256(original).hexdigest()
 if pre!=expected:raise SystemExit('HOLD_SOURCE_MISMATCH '+rel+' '+pre)
 s=original.decode('utf-8')
 if rel=='MainWindow.xaml.cs':
  a='using NOX.P01.Packages.P02.OpenAI;'; b='using NoxP01.Packages.P02.OpenAI;'
  if s.count(a)!=1:raise SystemExit('HOLD_NAMESPACE_MISMATCH')
  s=s.replace(a,b)
 elif rel.endswith('OpenAiResponsesProvider.cs'):
  if 'using System.Net.Http;' in s or 'using System.IO;' in s:raise SystemExit('HOLD_ALREADY_PATCHED_P02')
  s='using System.IO;\nusing System.Net.Http;\n'+s
 elif rel.endswith('ComponentInstaller.cs'):
  if 'using System.IO;' in s:raise SystemExit('HOLD_ALREADY_PATCHED_P03')
  s='using System.IO;\n'+s
 elif rel.endswith('ModelCenterEvent.cs'):
  fragment='    public string? OperationId { get; init; }\n'
  if s.count(fragment)!=2 or (fragment+fragment) not in s:raise SystemExit('HOLD_OPERATION_ID_NOT_DUPLICATE')
  s=s.replace(fragment+fragment,fragment,1)
 elif rel.endswith('ModelDownloaderWindow.xaml.cs'):
  # Remove ONLY the second verbatim duplicate of two existing methods,
  # retaining all owner-sensitive first implementations and guard method.
  names=['RefreshComponentActions','ReadComponentOperation']
  for name in names:
   pattern=re.compile(r'(?m)^    private (?:void|ComponentOperation) '+name+r'\(\)\n    \{')
   ms=list(pattern.finditer(s))
   if len(ms)!=2:raise SystemExit('HOLD_UNEXPECTED_DUP_METHOD '+name+':'+str(len(ms)))
   ranges=[]
   for m in ms:
    i=m.end();depth=1
    while depth and i<len(s):
     if s[i]=='{':depth+=1
     elif s[i]=='}':depth-=1
     i+=1
    if depth:raise SystemExit('HOLD_UNCLOSED_DUP '+name)
    ranges.append((m.start(),i))
   first=s[ranges[0][0]:ranges[0][1]]
   second=s[ranges[1][0]:ranges[1][1]]
   if first!=second:raise SystemExit('HOLD_METHOD_NOT_IDENTICAL '+name)
   # remove second only; retained first function is byte exact
   st,en=ranges[1];s=s[:st]+s[en:]
 new=s.encode('utf-8');post=hashlib.sha256(new).hexdigest()
 if original==new:raise SystemExit('HOLD_NO_DIFF '+rel)
 receipts.append({'owner':'E06_DIAGNOSTIC_NO_REPLACEMENT','path':'R11/'+rel,'pre_sha256':pre,'post_sha256':post,
  'source_bytes_preserved_in_immutable_original_zip':True})
 p.write_bytes(new)
# Existing P05 after prior phase already hash-pinned by that phase.
print('NOX_R08_COMPILER_STAGE2_APPLIED '+json.dumps(receipts,separators=(',',':')))