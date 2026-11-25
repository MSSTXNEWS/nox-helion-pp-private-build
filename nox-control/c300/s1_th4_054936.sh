cd /tmp; sed -i "s#pg.on('pageerror'#pg.on('response',lambda r:errs.append('404 '+r.url[-90:]) if r.status==404 else None); pg.on('pageerror'#; s#await pg.wait_for_timeout(25000)#await pg.wait_for_timeout(8000)#; s#errs\[:5\]#errs[:12]#" /tmp/th3.py
/workspace/nox/venv/bin/python /tmp/th3.py 2>&1 | grep -v "^[A-Za-z0-9+/=]\{150,\}$"
ls /workspace/nox/web/site/vendor/three/addons /workspace/nox/web/site/vendor/three/addons/libs 2>&1 | head -20
