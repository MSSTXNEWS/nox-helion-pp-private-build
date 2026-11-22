import os,sys,subprocess,time,signal
port=sys.argv[1]; log=sys.argv[2]
out=subprocess.run("ss -ltnp | grep ':%s ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2"%port,shell=True,capture_output=True,text=True).stdout.strip()
pid=int(out); cmd=open('/proc/%d/cmdline'%pid,'rb').read().split(b'\0')[:-1]; cmd=[c.decode() for c in cmd]
env=dict(l.split('=',1) for l in open('/proc/%d/environ'%pid,'rb').read().decode(errors='replace').split('\0') if '=' in l)
cwd=os.readlink('/proc/%d/cwd'%pid)
os.kill(pid,signal.SIGTERM)
for _ in range(20):
    time.sleep(.5)
    if not os.path.exists('/proc/%d'%pid): break
else: os.kill(pid,signal.SIGKILL); time.sleep(1)
subprocess.Popen(cmd,cwd=cwd,env=env,stdout=open(log,'ab'),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
print('restarted',port,cmd[:3])
