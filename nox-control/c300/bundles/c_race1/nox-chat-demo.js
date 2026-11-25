/* C: первый запуск: колонка чтения 760px (панель «Заготовки» свёрнута на экранах < 1700px) и демо-диалог, где видно «проверено судьями», источники, уверенность и «Додумал». Показывается только при пустой истории; удалить: localStorage nox.demo.off=1. */
(function () {
  'use strict';
  try {
    if (localStorage.getItem('nox.demo.off') === '1') return;
    if (!localStorage.getItem('nox.cx5.col')) localStorage.setItem('nox.cx5.col', JSON.stringify({ cmd: 1, pr: innerWidth >= 1700 ? 1 : 0, sys: 1 }));
    let th = []; try { th = JSON.parse(localStorage.getItem('nox.wow.threads') || '[]'); } catch (e) { th = []; }
    if (th.length) return;
    const now = Date.now();
    const demo = { id: 'demo-wow', title: 'Демо: проверка, источники, уверенность', ts: now, srv: false, msgs: [
      { role: 'user', content: 'Какая столица Австралии и почему не Сидней?', ts: now - 60000 },
      { role: 'assistant', ts: now - 30000, content: 'Столица Австралии — **Канберра**. Сидней — крупнейший город, но столицей с 1913 года стала специально построенная Канберра: так сняли соперничество Сиднея и Мельбурна.\n\n- Канберра расположена между Сиднеем и Мельбурном.\n- Парламент и правительство находятся там.\n\n*Это демо-пример: под ответом видны проверка судьями, источники, уверенность и блок «Додумал».*' } ] };
    localStorage.setItem('nox.wow.threads', JSON.stringify([demo])); localStorage.setItem('nox.wow.cur', 'demo-wow'); localStorage.setItem('nox.demo.shown', '1');
  } catch (e) { return; }
  const meta = { sources: ['сеть', 'советник'], judges: 11, judged: true, confidence: 0.91, thought: 'Проверка по сети подтверждает: столица — Канберра (с 1913 года). Сидней остаётся крупнейшим городом.', quick: ['Подробнее', 'Коротко'] };
  let n = 0; const t = setInterval(() => { n++; if (n > 80) { clearInterval(t); return; } if (document.querySelector('#feed .m.a .bubble') && window.__rqRender && !document.querySelector('.rq-meta') && !document.querySelector('.m.a.lv-live,.think')) { try { window.__rqRender(meta, null); } catch (e) { } } }, 500);
})();
