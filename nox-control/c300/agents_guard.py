#!/usr/bin/env python3
"""Диспетчер-2 (страж): держит lease диспетчера-1, при пропуске >35 с или упавшем /health перезапускает сервис."""
import os, time, sqlite3, subprocess, urllib.request, sys
W='/workspace/nox'; A=W+'/agents'; HB=W+'/state/agents_guard.hb'
if os.path.exists(HB) and time.time()-os.path.getmtime(HB) < 15 and os.environ.get('G_FORCE')!='1':
    pass
def alive():
    try: return b'"ok":true' in urllib.request.urlopen('http://127.0.0.1:8810/health', timeout=5).read().replace(b' ', b'')
    except Exception: return False
def lease_age():
    try:
        c=sqlite3.connect(A+'/book.sqlite', timeout=5); r=c.execute('select ts from lease where k="disp1"').fetchone(); return time.time()-r[0] if r else 9e9
    except Exception: return 9e9
def restart():
    subprocess.run(['pkill','-f',A+'/nox_agents.py'])
    time.sleep(2)
    subprocess.Popen(['setsid','nohup',A+'/venv/bin/python',A+'/nox_agents.py'], stdin=subprocess.DEVNULL, stdout=open(A+'/service.log','a'), stderr=subprocess.STDOUT, cwd=A, start_new_session=True)
bad=0
while True:
    open(HB,'a').close(); os.utime(HB)
    if not alive(): bad+=1
    else: bad=0
    if bad>=3 or (alive() and lease_age()>35):
        restart(); bad=0; time.sleep(20)
    time.sleep(10)
