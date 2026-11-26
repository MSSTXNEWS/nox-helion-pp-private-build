import sys
p=sys.argv[1]; s=open(p,encoding='utf-8').read()
if 'CH-SW-RELOAD' in s: print('already'); sys.exit()
a="  const base = location.pathname.replace(/[^/]*$/, '');\n"
b=a+"  /* CH-SW-RELOAD: при смене SW (обновление) вкладка один раз перезагружается; первый визит не трогаем */\n  const hadCtl = !!navigator.serviceWorker.controller;\n  navigator.serviceWorker.addEventListener('controllerchange', () => { try { if (!hadCtl || sessionStorage.getItem('noxSwReload')) return; sessionStorage.setItem('noxSwReload', '1'); location.reload(); } catch (e) { } });\n  document.addEventListener('visibilitychange', () => { if (!document.hidden) navigator.serviceWorker.getRegistration(base).then((r) => r && r.update()).catch(() => { }); });\n"
assert a in s; open(p,'w',encoding='utf-8').write(s.replace(a,b,1)); print('patched')
