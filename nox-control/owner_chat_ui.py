"""Activate the existing graphical Resonance for authenticated NOX owners."""
from __future__ import annotations
import asyncio,json,os,re,stat,time
from pathlib import Path
from html.parser import HTMLParser
from fastapi import Request
from fastapi.responses import JSONResponse,RedirectResponse
from fastapi.routing import APIRoute

ROOT=Path('/root/nox')
DEST='/nox-web-v29/pc/resonance.html'
PAGES={'pc/resonance.html','pc/v22/resonance.template.html'}
BUILD='NOX_OWNER_LIVE_RESONANCE_20261116'


class _LiveOwnerAssetScanner(HTMLParser):
    """Only executable, non-inert HTML tags can satisfy owner asset checks."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.inert_stack=[]
        self.raw_text_tag=None
        self.has_build=False
        self.scripts=set()

    def handle_starttag(self, tag, attrs):
        # HTMLParser tokenizes markup inside some HTML raw-text elements, but
        # browsers treat it as inert text. It cannot load our owner scripts.
        if self.raw_text_tag is not None:
            return
        if tag in ('textarea', 'title', 'xmp', 'iframe', 'noembed', 'noframes'):
            self.raw_text_tag=tag
            return
        # Nested inert elements remain inert until their *matching* close.
        # Track exact inert tag names, not just a depth. An unmatched closing
        # </noscript> inside <template> must not expose a fake executable asset.
        if tag in ('template', 'noscript'):
            self.inert_stack.append(tag)
            return
        if self.inert_stack:
            return
        attributes=dict(attrs)
        if tag=='meta' and attributes.get('name','').lower()=='nox-live-build':
            self.has_build=True
        if tag=='script':
            kind=attributes.get('type') or ''
            if kind.strip().lower() not in ('', 'text/javascript', 'application/javascript', 'module'):
                return
            url=attributes.get('src')
            if isinstance(url,str) and re.fullmatch(
                r'/nox-web-v29/[A-Za-z0-9_.-]+\.js(?:\?[^"\'<>\s]*)?',url
            ):
                self.scripts.add(url.split('?',1)[0])

    def handle_startendtag(self, tag, attrs):
        # HTML void syntax is not honored on non-void elements. In HTML5,
        # <template/>, <noscript/> and <textarea/> are opening tags, not
        # closed tags. HTMLParser otherwise calls start AND end here, making
        # browser-inert owner assets appear executable to this source check.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.raw_text_tag is not None:
            if tag==self.raw_text_tag:
                self.raw_text_tag=None
            return
        if self.inert_stack and tag==self.inert_stack[-1]:
            self.inert_stack.pop()

def decorate_html(raw,path):
    if path.lstrip('/') not in PAGES:return raw
    # HTML closing tags are case-insensitive, including in older WEB archives.
    # Keep the original tag spelling/spacing rather than rewriting archive HTML.
    head_closers=list(re.finditer(r'</head\s*>',raw,re.I))
    if len(head_closers)!=1:raise ValueError('HOLD_RESONANCE_HEAD')
    head_close=head_closers[0].group(0)
    # The original archive assumes hosting at /. Our owner-only mount is nested.
    raw=raw.replace('="/pc/','="/nox-web-v29/pc/').replace("='/pc/","='/nox-web-v29/pc/")
    # The legacy shell otherwise inserts a second, unmounted /pc/v25 CSS URL.
    # Mark only its exact, already relocated stylesheet; preserve the asset.
    def shell_css(match):
        tag=match.group(0)
        if (re.search(r'\bhref\s*=\s*([\"\'])/nox-web-v29/pc/v25/nox-shell-v25\.css(?:\?[^\"\']*)?\1',tag,re.I)
                and not re.search(r'\bdata-n25-css(?:\s*=|\s|/?>)',tag,re.I)):
            end='/>' if tag.endswith('/>') else '>'
            return tag[:-len(end)]+' data-n25-css="1"'+end
        return tag
    raw=re.sub(r'<link\b[^>]*>',shell_css,raw,flags=re.I)
    # An archived <template>, <noscript>, commented tag or non-executable
    # <script type=application/json> cannot load the required live owner JS.
    # Inspect active HTML tags without rewriting any original archive bytes.
    scanner=_LiveOwnerAssetScanner()
    scanner.feed(raw)
    extra=''
    if not scanner.has_build:
        extra='\n<meta name="nox-live-build" content="'+BUILD+'">\n'
    for name in ('nox-v135-resonance-owner-bridge.js','nox-v137-owner-self-status.js','owner-chat-ui.js','owner-presence.js'):
        if '/nox-web-v29/'+name in scanner.scripts:
            continue
        extra+='<script defer src="/nox-web-v29/'+name+'" data-nox-live-owner="1"></script>\n'
    return raw.replace(head_close,extra+head_close,1) if extra else raw

def owner_maintenance_gate():
    """Read-only, fail-closed owner maintenance indicator; never grants a lease."""
    parent = ROOT / 'state'
    # A missing/unreadable state directory is UNKNOWN, not an absent owner STOP.
    # Anchor the marker lookup to one non-symlink directory FD.
    try:
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return 'UNKNOWN'
    try:
        opened = os.fstat(fd)
        if not stat.S_ISDIR(opened.st_mode):
            return 'UNKNOWN'
        try:
            flag = os.stat('OWNER_MAINTENANCE.flag', dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            status = 'ABSENT'
        except OSError:
            return 'UNKNOWN'
        else:
            status = 'PRESENT' if stat.S_ISREG(flag.st_mode) else 'UNKNOWN'
        # A swapped directory must not be classified using stale evidence.
        try:
            current = parent.lstat()
        except OSError:
            return 'UNKNOWN'
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            return 'UNKNOWN'
        return status
    finally:
        os.close(fd)


def _owner_status_pairs_unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError('HOLD_EXECUTOR_STATUS_DUPLICATE_KEY')
        result[key]=value
    return result


def _owner_status_no_nonfinite(value):
    raise ValueError('HOLD_EXECUTOR_STATUS_NONFINITE')


def workers():
    """Read a single bounded descriptor-pinned worker snapshot, fail closed on races."""
    result={'schema':'NOX_OWNER_EXECUTORS_V1','state':'UNAVAILABLE','workers':[],
            'configured':None,'observed_at':None,'training_held':(ROOT/'state/TRAIN_HOLD.flag').exists()}
    maintenance=owner_maintenance_gate()
    result['owner_maintenance']=maintenance
    if maintenance!='ABSENT':
        result['state']='MODEL_UPDATE' if maintenance=='PRESENT' else 'HOLD_MAINTENANCE_UNKNOWN'
        return result
    try:
        directory=ROOT/'status'
        parent_fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            anchor=os.fstat(parent_fd)
            file_fd=os.open('agents_t856u.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent_fd)
            try:
                before=os.fstat(file_fd)
                if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid()
                        or before.st_mode & 0o022 or not 0<before.st_size<=750000):
                    return result
                raw=os.read(file_fd,750001)
                after=os.fstat(file_fd)
                # A valid descriptor does not prove the current pathname still
                # refers to it: an atomic rename can replace a native status
                # snapshot while the read is in progress.
                current=os.stat('agents_t856u.json',dir_fd=parent_fd,
                                follow_symlinks=False)
                identity=lambda st:(
                    st.st_dev,st.st_ino,st.st_uid,st.st_mode,st.st_size,
                    st.st_mtime_ns,st.st_ctime_ns
                )
                if (len(raw)!=before.st_size or identity(before)!=identity(after)
                        or identity(current)!=identity(before)):return result
            finally:
                os.close(file_fd)
            current=directory.lstat()
            if not stat.S_ISDIR(current.st_mode) or (
                current.st_dev,current.st_ino
            )!=(anchor.st_dev,anchor.st_ino):return result
        finally:
            os.close(parent_fd)
        value=json.loads(raw,object_pairs_hook=_owner_status_pairs_unique,
                         parse_constant=_owner_status_no_nonfinite)
        stamp=before.st_mtime
        if not isinstance(value,dict):return result
        rows=value.get('workers')
        # The native OneHost contract caps physical workers at three;
        # a 4+ worker report is not trustworthy capacity evidence.
        if (not isinstance(rows,list) or not 1<=len(rows)<=3 or type(value.get('n')) is not int
                or value['n']!=len(rows)):return result
        if any(not isinstance(row,dict) or not isinstance(row.get('id'),str)
               or not re.fullmatch(r'nox-agent-[0-9]{2}',row['id'])
               or row.get('status') not in ('idle','busy') for row in rows):return result
        if len({row['id'] for row in rows})!=len(rows):return result
        claims=[row.get('current_task',{}).get('id') for row in rows if isinstance(row.get('current_task'),dict)]
        if (any(type(claim) is not str or not 1<=len(claim)<=100
                or claim!=claim.strip() or not claim.isprintable()
                for claim in claims) or len(set(claims))!=len(claims)):
            return result
        if any((row['status']=='busy')!=isinstance(row.get('current_task'),dict) for row in rows):return result
        # A maintenance transition during snapshot reading invalidates even valid data.
        maintenance=owner_maintenance_gate()
        if maintenance!='ABSENT':
            result['owner_maintenance']=maintenance
            result['state']='MODEL_UPDATE' if maintenance=='PRESENT' else 'HOLD_MAINTENANCE_UNKNOWN'
            return result
        for row in rows:
            task=row.get('current_task')
            result['workers'].append({'id':str(row.get('id',''))[:60],
                'status':str(row.get('status','unknown'))[:30],
                'task_id':str(task.get('id',''))[:100] if isinstance(task,dict) else None})
        result.update(state='OBSERVED' if -5<=time.time()-stamp<=45 else 'STALE',
                      configured=value.get('n'),observed_at=stamp)
    except (OSError,ValueError,TypeError):pass
    return result

def register_owner_chat_ui(app,trusted):
    check=trusted.get('_session_ok');reject=trusted.get('_unauthorized');legacy=trusted.get('chat_page')
    if not all(callable(x) for x in (check,reject,legacy)):raise RuntimeError('HOLD_ORIGINAL_CHAT_CALLBACKS')
    app.router.routes[:]=[route for route in app.router.routes if not (
        isinstance(route,APIRoute) and route.path in ('/','/chat') and route.methods=={'GET'})]
    @app.get('/')
    async def owner_home(request:Request):
        return RedirectResponse(DEST if check(request) else '/chat',status_code=302,headers={'Cache-Control':'no-store'})
    @app.get('/chat')
    async def owner_chat(request:Request):
        if check(request):return RedirectResponse(DEST,status_code=302,headers={'Cache-Control':'no-store'})
        return await legacy()
    @app.get('/api/ui/executors')
    async def owner_executors(request:Request):
        if not check(request):return reject()
        return JSONResponse(await asyncio.to_thread(workers),headers={'Cache-Control':'no-store'})
    @app.get('/api/ui/downloads')
    async def owner_downloads(request:Request):
        if not check(request):return reject()
        from owner_download_status import snapshot
        return JSONResponse(await asyncio.to_thread(snapshot),headers={'Cache-Control':'no-store'})
    return {'home':DEST,'build':BUILD,'authentication':'EXISTING_OWNER_SESSION'}
