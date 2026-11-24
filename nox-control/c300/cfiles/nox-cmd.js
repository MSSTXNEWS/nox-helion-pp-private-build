/* NOX · клиент командной шины: window.NOXcmd(name, params). Опасные команды — через диалог подтверждения в стекле. */
(function () {
  if (window.NOXcmd) return;
  let reg = null;
  const regP = fetch('qa/registry.json', { cache: 'no-cache' }).then((r) => r.json()).then((j) => (reg = j)).catch(() => (reg = { commands: {} }));
  const toast = (msg, bad) => { const d = document.createElement('div'); d.textContent = msg; d.style.cssText = 'position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:2147483600;padding:10px 18px;border-radius:12px;font:300 12px/1.3 inherit;color:#efe6df;background:rgba(16,13,13,.82);border:1px solid ' + (bad ? '#c0392b' : 'rgba(255,255,255,.14)') + ';backdrop-filter:blur(14px)'; document.body.appendChild(d); setTimeout(() => d.remove(), 2600); };
  const ask = (name, desc) => new Promise((ok) => {
    const o = document.createElement('div');
    o.style.cssText = 'position:fixed;inset:0;z-index:2147483500;display:flex;align-items:center;justify-content:center;background:rgba(8,6,6,.55);backdrop-filter:blur(6px)';
    o.innerHTML = '<div style="max-width:420px;padding:22px;border-radius:18px;background:rgba(28,22,22,.72);border:1px solid rgba(255,255,255,.14);backdrop-filter:blur(18px);color:#efe6df;font:300 14px/1.5 inherit"><div style="margin-bottom:14px">Выполнить опасную команду «' + desc + '»? Это действие нельзя отменить из пульта.</div><div style="display:flex;gap:10px;justify-content:flex-end"><button data-n style="padding:8px 14px;border-radius:10px;background:transparent;color:#a89c93;border:1px solid rgba(255,255,255,.14);cursor:pointer">Отмена</button><button data-y style="padding:8px 14px;border-radius:10px;background:#c0392b;color:#fff;border:0;cursor:pointer">Подтвердить</button></div></div>';
    const done = (v) => { o.remove(); ok(v); };
    o.querySelector('[data-n]').onclick = () => done(false);
    o.querySelector('[data-y]').onclick = () => done(true);
    o.addEventListener('click', (e) => { if (e.target === o) done(false); });
    document.body.appendChild(o);
  });
  async function NOXcmd(name, params) {
    if (!reg) await regP;
    const cmd = reg.commands && reg.commands[name];
    if (!cmd) { toast('Команда не в реестре: ' + name, true); return { ok: false, error: 'not_registered' }; }
    const body = { name, params: params || {} };
    if (cmd.confirm) {
      if (!(await ask(name, cmd.desc))) { toast('Отменено'); return { ok: false, error: 'cancelled' }; }
      const c = await fetch('/api/cmd/confirm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, clicked: true }) }).then((r) => r.json()).catch(() => null);
      if (!c || !c.ok) { toast('Не подтверждено', true); return { ok: false, error: 'confirm_failed' }; }
      body.confirm_token = c.confirm_token;
    }
    const r = await fetch('/api/cmd', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(async (x) => ({ status: x.status, j: await x.json().catch(() => ({})) })).catch(() => null);
    const ok = !!(r && r.j && r.j.ok);
    toast(ok ? cmd.desc + ': готово' : cmd.desc + ': ошибка' + (r && r.j && r.j.error ? ' (' + r.j.error + ')' : ''), !ok);
    return ok ? r.j : { ok: false, error: (r && r.j && r.j.error) || 'network' };
  }
  window.NOXcmd = NOXcmd;
  window.NOXcmdRegistry = () => reg;
})();
