/* S4 · Загрузки: файловый менеджер Filebrowser (прокси /svc/filebrowser/) в раскладке Dropbox/Filebrowser, рядом очередь загрузок панели. */
(function () {
  const wrap = document.querySelector('.wrap'); if (!wrap) return;
  const sec = document.createElement('section'); sec.className = 'card s4dl';
  sec.innerHTML = '<h2>Файлы <span class="r mono" id="s4fs">проверка…</span></h2><div class="s4fb"><sl-button size="medium" id="s4fo"><sl-icon slot="prefix" library="tabler" name="external-link"></sl-icon>Открыть отдельно</sl-button><sl-button size="medium" id="s4fr"><sl-icon slot="prefix" library="tabler" name="refresh"></sl-icon>Обновить</sl-button></div><iframe id="s4fi" title="Filebrowser" loading="lazy" referrerpolicy="same-origin"></iframe><p class="muted" id="s4fe" hidden>Файловый менеджер недоступен: /svc/filebrowser/ не отвечает. Подключите службу Filebrowser.</p>';
  wrap.insertBefore(sec, wrap.querySelector('section.card') || null);
  const fr = sec.querySelector('#s4fi'), st = sec.querySelector('#s4fs');
  const load = () => fetch('/svc/filebrowser/', { cache: 'no-store' }).then((r) => { if (!r.ok) throw new Error(r.status); st.textContent = 'на связи'; sec.querySelector('#s4fe').hidden = true; fr.hidden = false; fr.src = '/svc/filebrowser/?t=' + Date.now(); })
    .catch((e) => { st.textContent = 'нет связи (' + e.message + ')'; fr.hidden = true; sec.querySelector('#s4fe').hidden = false; });
  sec.querySelector('#s4fo').onclick = () => window.open('/svc/filebrowser/', '_blank', 'noopener');
  sec.querySelector('#s4fr').onclick = load; load();
})();
