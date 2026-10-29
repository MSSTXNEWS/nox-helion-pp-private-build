"""NOX E06: repair original R13 HTML chatLog TDZ in disposable WPF build tree."""
from pathlib import Path
import hashlib,json,sys
D02={'home.png':'382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a',
'menu.png':'4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9',
'core01.png':'343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97',
'menu_sections.png':'7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4'}
DECL=("const chatModel=document.getElementById('chat-model'),chatLog=document.getElementById('chat-log'),"
"chatInput=document.getElementById('chat-input'),chatState=document.getElementById('chat-state'),"
"chatSend=document.getElementById('chat-send'),chatStop=document.getElementById('chat-stop'),"
"chatProvider=document.getElementById('chat-provider'),openAiModel=document.getElementById('openai-model');")
ANCHOR='let chatScrollFrame=0;function cancelScheduledChatScroll()'
WHEEL="chatLog.addEventListener('wheel',cancelScheduledChatScroll"
def sha(b):return hashlib.sha256(b).hexdigest()
def stage(directory):
 root=Path(directory).resolve(strict=True)
 html=root/'Assets/index.html'
 if not (root/'NOX.P01.Shell.csproj').is_file() or not html.is_file() or html.is_symlink():raise ValueError('WPF_SOURCE_HOLD')
 for name,want in D02.items():
  f=root/'Assets'/name
  if not f.is_file() or f.is_symlink() or sha(f.read_bytes())!=want:raise ValueError('D02_SOURCE_SHA_HOLD:'+name)
 before=html.read_bytes();bom=b'\xef\xbb\xbf' if before.startswith(b'\xef\xbb\xbf') else b''
 text=before[len(bom):].decode('utf-8')
 if text.count(DECL)!=1 or text.count(ANCHOR)!=1 or text.count(WHEEL)!=1:raise ValueError('R13_CHAT_PREIMAGE_DRIFT')
 if not all(x in text for x in ('nox-orbit-stage','CONSCIOUSNESS','FORGE','chat-log','chat-send')):raise ValueError('R13_OWNER_UI_HOLD')
 if text.index(DECL)<text.index(WHEEL):return {'state':'ALREADY_FIXED','post_sha256':sha(before)}
 if text.index(ANCHOR)>text.index(WHEEL):raise ValueError('WRONG_CHAT_SCROLL_ANCHOR')
 after=text.replace(DECL,'',1).replace(ANCHOR,DECL+ANCHOR,1)
 if len(after)!=len(text) or after.count(DECL)!=1 or after.index(DECL)>after.index(WHEEL):raise ValueError('R13_CHAT_POSTIMAGE_DRIFT')
 dst=bom+after.encode('utf-8')
 receipt=root.parent/'E06_CHAT_TDZ_RECEIPT.json'
 if receipt.exists():raise ValueError('E06_RECEIPT_OVERWRITE_HOLD')
 proof={'schema':'NOX_E06_R13_CHAT_TDZ_V1','pre_sha256':sha(before),'post_sha256':sha(dst),
        'same_bytes':len(before)==len(dst),'d02_original_sha256':D02,
        'source_only':True,'windows_accepted':False,'release_accepted':False}
 try:
  html.write_bytes(dst)
  if sha(html.read_bytes())!=sha(dst):raise ValueError('R13_CHAT_READBACK_HOLD')
  for name,want in D02.items():
   if sha((root/'Assets'/name).read_bytes())!=want:raise ValueError('D02_POST_SHA_HOLD')
  receipt.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 except BaseException:
  html.write_bytes(before)
  raise
 return proof
if __name__=='__main__':
 if len(sys.argv)!=2:raise SystemExit('USAGE: fix_r13_chat_init.py DISPOSABLE_R11')
 print(json.dumps(stage(sys.argv[1]),ensure_ascii=False))
