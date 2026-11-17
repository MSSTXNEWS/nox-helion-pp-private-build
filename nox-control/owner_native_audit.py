#!/usr/bin/env python3
"""Bounded read-only auth/config binding probe. No HTTP, subprocess or native mutation."""
from __future__ import annotations
import ast
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import stat
import time

WEB_SCRIPT=Path('/root/nox/scripts/nox_web29_onehost_18775.py')
EXPECTED_HTML_SHA256='9a5ee14787f4fc529926576339f86e07ce6ec838fe6e34fe6b2523f102719194'
HTML_FILE=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/pc/resonance.html')
CONFIG_FILES=tuple(Path(p) for p in (
 '/root/nox/.env','/root/nox/config.json','/root/nox/config.yaml',
 '/root/nox/config/bridges.json','/root/nox/config/providers.json',
 '/root/nox/config/rclone.conf','/root/.config/rclone/rclone.conf'))
RCLONE_FILES=(Path('/root/nox/config/rclone.conf'),Path('/root/.config/rclone/rclone.conf'))
PIDS=(3368105,3367881)
AUTH_NAME=re.compile(r'(?:AUTH|TOKEN|PASSWORD|PASSWD|COOKIE|SESSION|API_?KEY|OPENROUTER|GROQ|GEMINI|GOOGLE|RCLONE|DRIVE)',re.I)
ENV_NAME=re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,95}')
HTML_SECRETS=(
 re.compile(r'(?i)\b(?:sk-(?:or-v1-)?[a-z0-9_-]{12,}|AIza[a-z0-9_-]{20,}|gh[pousr]_[a-z0-9]{20,})'),
 re.compile(r'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b'),
 re.compile(r'(?i)(?:authorization|auth|api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|cookie|session|token|owner[_-]?key|client[_-]?secret)\s*[\"\']?\s*[:=]\s*[\"\'][^\"\']+'),
 re.compile(r'(?i)Bearer\s+[A-Za-z0-9_./+=-]{8,}|Basic\s+[A-Za-z0-9+/=]{8,}'),
 re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 re.compile(r'(?i)https?://[^\s/\"\']+:[^\s/\"\']+@'),
 re.compile(r'(?i)[?&](?:token|key|password|secret|code|session)=([^&#\s\"\']+)'),
)


def bounded(path,limit):
 try:
  if path.is_symlink() or not path.is_file() or path.stat().st_size>limit:return None
  with path.open('rb') as f:data=f.read(limit+1)
  return data if len(data)<=limit else None
 except OSError:return None


def metadata(path):
 try:
  s=path.lstat()
  return {'path':str(path),'exists':True,'bytes':s.st_size,'mode':oct(stat.S_IMODE(s.st_mode)),
          'mtime_epoch':s.st_mtime,'symlink':stat.S_ISLNK(s.st_mode)}
 except OSError:return {'path':str(path),'exists':False}


def python_view(raw):
 """AST-normalized view: redact ALL value literals, not just familiar key formats.

 Only header/cookie dictionary keys and environment-variable NAMES are retained
 in narrow syntactic positions. No original source lines or literal values escape.
 """
 tree=ast.parse(raw.decode('utf-8'))
 allowed_nodes=set();environment_names=set();header_names=set()
 known_headers={'authorization','cookie','set-cookie','x-api-key','www-authenticate','content-type','origin','host'}
 for node in ast.walk(tree):
  if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute):continue
  owner=node.func.value
  owner_name=owner.attr if isinstance(owner,ast.Attribute) else owner.id if isinstance(owner,ast.Name) else ''
  if node.func.attr not in ('get','getenv') or not node.args:continue
  first=node.args[0]
  if not isinstance(first,ast.Constant) or not isinstance(first.value,str):continue
  if (owner_name=='environ' or (owner_name=='os' and node.func.attr=='getenv')) and ENV_NAME.fullmatch(first.value):
   environment_names.add(first.value);allowed_nodes.add(id(first))
  elif owner_name in ('headers','cookies') and first.value.lower() in known_headers:
   header_names.add(first.value.lower());allowed_nodes.add(id(first))
 class Redact(ast.NodeTransformer):
  def visit_Constant(self,node):
   if id(node) in allowed_nodes:return node
   if node.value is None or isinstance(node.value,bool):return node
   return ast.copy_location(ast.Constant(value='<REDACTED_LITERAL>'),node)
 clean=Redact().visit(tree);ast.fix_missing_locations(clean)
 return {'view_kind':'AST_NORMALIZED_ALL_VALUE_LITERALS_REDACTED','source_view':ast.unparse(clean),
         'environment_variable_names':sorted(environment_names),'auth_header_names':sorted(header_names)}


class HTMLSecretInputs(HTMLParser):
 def __init__(self):super().__init__();self.sensitive=False
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='input' and attrs.get('value') and (attrs.get('type','').lower() in ('password','hidden') or AUTH_NAME.search(attrs.get('name',''))):self.sensitive=True
  if tag=='meta' and attrs.get('content') and AUTH_NAME.search(attrs.get('name','')):self.sensitive=True
  for key,value in attrs.items():
   if value and AUTH_NAME.search(key) and key.startswith('data-'):self.sensitive=True


def html_view(raw):
 try:text=raw.decode('utf-8')
 except UnicodeDecodeError:return {'source_exported':False,'reason':'NON_UTF8'}
 if any(pattern.search(text) for pattern in HTML_SECRETS):return {'source_exported':False,'reason':'SECRET_PATTERN_PRESENT'}
 parser=HTMLSecretInputs()
 try:parser.feed(text)
 except (ValueError,RecursionError):return {'source_exported':False,'reason':'HTML_PARSE_HOLD'}
 if parser.sensitive:return {'source_exported':False,'reason':'SENSITIVE_INPUT_OR_DATA_ATTRIBUTE'}
 return {'source_exported':True,'source':text,'scan_scope':'BOUNDED_STATIC_HTML_SECRET_PATTERNS_AND_INPUTS'}


def environment_metadata(raw,allowed_roots):
 names=[];paths=[]
 for entry in raw.split(b'\0'):
  key,sep,value=entry.partition(b'=')
  if not sep:continue
  name=key.decode('ascii','ignore')
  if not ENV_NAME.fullmatch(name):continue
  if AUTH_NAME.search(name):names.append(name)
  if not re.search(r'(?:CONFIG|CONF|CREDENTIAL|RCLONE|DRIVE|AUTH_FILE)',name,re.I):continue
  try:
   path=Path(value.decode('utf-8'))
   if not path.is_absolute() or len(str(path))>512 or '\n' in str(path) or '\x00' in str(path):continue
   # No resolving arbitrary symlinks or reading the selected file here.
   if '..' in path.parts:continue
   if any(path==root or root in path.parents for root in allowed_roots):paths.append({'variable':name,'config_path':str(path)})
  except (ValueError,UnicodeDecodeError):continue
 return {'auth_provider_variable_names':sorted(set(names)),'allowed_config_paths':paths[:20],
         'credential_values_exported':False}


def rclone_metadata(raw):
 if raw.startswith(b'RCLONE_ENCRYPT_V'):return {'encrypted':True,'remotes':[]}
 remotes=[];current=None
 for line in raw.decode('utf-8','replace').splitlines():
  section=re.fullmatch(r'\s*\[([A-Za-z0-9_. -]{1,80})\]\s*',line)
  if section:
   current={'remote':section.group(1),'type':None};remotes.append(current);continue
  typed=re.fullmatch(r'\s*type\s*=\s*([A-Za-z0-9_-]{1,40})\s*',line)
  if typed and current is not None:current['type']=typed.group(1)
 return {'encrypted':False,'remotes':remotes[:32],'tokens_exported':False}


def run_probe(web=WEB_SCRIPT,html=HTML_FILE,configs=CONFIG_FILES,rclones=RCLONE_FILES,
              proc_root=Path('/proc'),allowed_roots=(Path('/root/nox'),Path('/root/.config/rclone'))):
 out={'schema':'NOX_AUTH_BINDING_READONLY_AUDIT_V1','observed_at_epoch':time.time(),
      'http_requests':0,'subprocesses':0,'native_mutations':False,'credential_values_exported':False}
 for label,path,limit,reader in (('web_script',web,16384,python_view),('resonance_html',html,32768,html_view)):
  info=metadata(path);raw=bounded(path,limit)
  if raw is not None:
   info['sha256']=hashlib.sha256(raw).hexdigest()
   try:
    if label=='resonance_html' and path==HTML_FILE and info['sha256']!=EXPECTED_HTML_SHA256:
     info.update(source_exported=False,reason='HOLD_HTML_HASH_CHANGED')
    else:info.update(reader(raw))
   except (SyntaxError,UnicodeDecodeError,ValueError,RecursionError):info.update(source_exported=False,reason='PARSE_HOLD')
  else:info.update(source_exported=False,reason='MISSING_OR_NOT_BOUNDED')
  out[label]=info
 out['fixed_config_metadata']=[metadata(path) for path in configs]
 out['process_environment']=[]
 for pid in PIDS:
  raw=bounded(proc_root/str(pid)/'environ',131072)
  if raw is not None:out['process_environment'].append({'pid':pid,**environment_metadata(raw,allowed_roots)})
 out['rclone']=[]
 for path in rclones:
  raw=bounded(path,65536)
  item=metadata(path)
  if raw is not None:item.update(rclone_metadata(raw))
  out['rclone'].append(item)
 return out


def main():
 try:result=run_probe();complete=True
 except Exception:result={'schema':'NOX_AUTH_BINDING_READONLY_AUDIT_V1','status':'BOUNDED_READ_ERROR','credential_values_exported':False};complete=False
 print('NOX_MAINT_AUDIT='+json.dumps(result,ensure_ascii=False,separators=(',',':')))
 print('NOX_MAINT_AUDIT_COMPLETE='+str(complete).lower())

if __name__=='__main__':main()
