/* Панель ползунков личности «Резонанс». Без зависимостей и CDN. Весь текст вставляется через textContent (без innerHTML).
   NoxTraitsPanel.mount(el, {api: "/api/traits", token: () => "..."}) */
(function (root) {
  "use strict";
  var MODES = [["AUTO", "авто"], ["MANUAL_LOCK", "заблокирован"], ["REVIEW_ONLY", "на просмотр"]];

  function h(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function btn(label, cls, fn) {
    var b = h("button", cls, label);
    b.type = "button";
    b.addEventListener("click", fn);
    return b;
  }

  function mount(el, opts) {
    var api = (opts && opts.api) || "/api/traits";
    var tokenFn = (opts && opts.token) || function () { return ""; };
    var state = null, root_ = h("div", "nxt");
    el.textContent = "";
    el.appendChild(root_);

    function headers() {
      var t = tokenFn();
      var hd = {"Content-Type": "application/json"};
      if (t) hd["X-NOX-Token"] = t;
      return hd;
    }
    function call(method, url, body) {
      return fetch(url, {method: method, headers: headers(), body: body ? JSON.stringify(body) : undefined, credentials: "same-origin"})
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.status); return j; }); });
    }
    function act(body) {
      return call("POST", api + "/action", body).then(function (j) { state = j; render(); }).catch(showErr);
    }
    function showErr(e) {
      var old = root_.querySelector(".err");
      if (old) old.remove();
      root_.insertBefore(h("div", "err", "Ошибка: " + e.message), root_.firstChild);
    }

    function traitRow(t) {
      var row = h("div", "row" + (t.mode === "MANUAL_LOCK" ? " lockd" : "") + (t.open ? "" : " closed"));
      var top = h("div", "top");
      top.appendChild(h("span", "nm", t.name));
      if (t.open) {
        var val = h("span", "val", Number(t.value).toFixed(1));
        var rng = h("input");
        rng.type = "range"; rng.min = t.min; rng.max = t.max; rng.step = "0.5"; rng.value = t.value;
        rng.title = "Перетащите и отпустите: значение ставит владелец";
        rng.addEventListener("input", function () { val.textContent = Number(rng.value).toFixed(1); });
        rng.addEventListener("change", function () { act({action: "set_value", id: t.id, value: Number(rng.value), lock: t.mode === "MANUAL_LOCK"}); });
        var sel = h("select");
        MODES.forEach(function (m) { var o = h("option", null, m[1]); o.value = m[0]; if (m[0] === t.mode) o.selected = true; sel.appendChild(o); });
        sel.addEventListener("change", function () { act({action: "set_mode", id: t.id, mode: sel.value}); });
        top.appendChild(rng); top.appendChild(val);
        top.appendChild(h("span", "tag " + (t.earned ? "ok" : "un"), t.earned ? "по опыту" : "не подтверждено"));
        top.appendChild(sel);
      } else {
        top.appendChild(h("span", "tag", "грань закрыта"));
        top.appendChild(btn("открыть", "", function () { act({action: "open", id: t.id}); }));
      }
      row.appendChild(top);
      row.appendChild(h("div", "def", t.definition + (t.scope_note ? " [" + t.scope_note + "]" : "")));
      if (t.open) {
        row.appendChild(h("div", "why", "Почему: " + t.last_reason + " (свидетельств: " + t.evidence_count + ", v" + t.version + ")"));
        if (t.proposal) {
          var pr = h("div", "acts");
          pr.appendChild(h("span", "why", "Предложено значение " + Number(t.proposal.value).toFixed(1) + " - " + t.proposal.why));
          pr.appendChild(btn("утвердить", "yes", function () { act({action: "approve_change", id: t.id}); }));
          pr.appendChild(btn("отклонить", "no", function () { act({action: "reject_change", id: t.id}); }));
          row.appendChild(pr);
        }
        var ac = h("div", "acts");
        ac.appendChild(btn("откатить последнее", "", function () { act({action: "undo", id: t.id}); }));
        if (t.kind === "discovered") ac.appendChild(btn("удалить грань", "no", function () { act({action: "archive", id: t.id}); }));
        row.appendChild(ac);
      } else if (t.missing && t.missing.length) {
        row.appendChild(h("div", "miss", "До открытия: " + t.missing.join("; ")));
      }
      return row;
    }

    function proposalCard(p) {
      var c = h("div", "row prop");
      c.appendChild(h("div", "nm", "NOX предлагает новую грань: " + p.label_ru + (p.status === "REVIEW" ? " (на просмотре)" : "")));
      c.appendChild(h("div", "def", p.definition_ru + " | группа: " + p.category + " | уверенность " + Math.round(p.confidence * 100) + "%"));
      c.appendChild(h("div", "why", "Причина: " + p.reason));
      c.appendChild(h("div", "why", "Якоря: 1 - " + p.anchors["1"] + "; 5 - " + p.anchors["5"] + "; 10 - " + p.anchors["10"]));
      var ul = h("ul");
      p.episodes.forEach(function (e) { ul.appendChild(h("li", null, "[" + e.id + "] " + e.text)); });
      c.appendChild(ul);
      var ac = h("div", "acts");
      ac.appendChild(btn("утвердить", "yes", function () { act({action: "proposal", id: p.id, decision: "approve"}); }));
      ac.appendChild(btn("заблокировать", "no", function () { act({action: "proposal", id: p.id, decision: "block"}); }));
      if (p.status !== "REVIEW") ac.appendChild(btn("оставить на просмотр", "", function () { act({action: "proposal", id: p.id, decision: "review"}); }));
      c.appendChild(ac);
      return c;
    }

    function group(title, rows) {
      var wrap = h("div");
      wrap.appendChild(h("h3", null, title + " (" + rows.length + ")"));
      rows.forEach(function (r) { wrap.appendChild(r); });
      return wrap;
    }

    function render() {
      root_.textContent = "";
      var hd = h("div", "hd");
      hd.appendChild(h("h2", null, "Резонанс: ползунки личности"));
      hd.appendChild(h("span", null, "стадия: " + (state.phase_ru || "?") + " | открыто " + state.counts.open + " из " + state.counts.total +
        " | новых граней: " + state.counts.discovered));
      root_.appendChild(hd);
      if (state.proposals.length) {
        var pw = h("div");
        pw.appendChild(h("h3", null, "NOX предлагает новую грань (" + state.proposals.length + ")"));
        state.proposals.forEach(function (p) { pw.appendChild(proposalCard(p)); });
        root_.appendChild(pw);
      }
      var open = state.traits.filter(function (t) { return t.open; });
      var base = open.filter(function (t) { return t.base; });
      var facets = open.filter(function (t) { return !t.base; });
      root_.appendChild(group("Базовые (с рождения)", base.map(traitRow)));
      if (facets.length) root_.appendChild(group("Открытые грани", facets.map(traitRow)));
      var closed = state.traits.filter(function (t) { return !t.open; });
      if (closed.length) {
        var d = h("details");
        d.appendChild(h("summary", null, "Закрытые грани: " + closed.length + " (откроются сами по мере развития)"));
        closed.forEach(function (t) { d.appendChild(traitRow(t)); });
        root_.appendChild(d);
      }
      if (state.axes) {
        root_.appendChild(h("h3", null, "Оси характера = агрегаты черт"));
        var g = h("div", "axes");
        state.axes.forEach(function (a) {
          var x = h("div", "ax");
          x.appendChild(h("div", null, a.name + ": " + a.value.toFixed(2) + (a.target == null ? " (черты ещё не заработаны)" : " (цель " + a.target.toFixed(2) + ")")));
          var b = h("div", "bar"), i = h("i");
          i.style.width = Math.round(a.value * 100) + "%";
          b.appendChild(i); x.appendChild(b); g.appendChild(x);
        });
        root_.appendChild(g);
      }
      var ft = h("div", "acts");
      ft.appendChild(btn("обновить", "", load));
      ft.appendChild(btn("откат к последнему снапшоту", "no", function () { if (root.confirm("Откатить все черты к последнему снапшоту?")) act({action: "rollback"}); }));
      var lab = h("label", "why"), cb = h("input");
      cb.type = "checkbox"; cb.checked = !!state.autonomy;
      cb.addEventListener("change", function () { act({action: "autonomy", on: cb.checked}); });
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" NOX сам регистрирует безопасные новые грани (не ценности и не отношения)"));
      ft.appendChild(lab);
      root_.appendChild(ft);
    }

    function load() { return call("GET", api).then(function (j) { state = j; render(); }).catch(showErr); }
    load();
    return {reload: load};
  }

  root.NoxTraitsPanel = {mount: mount};
})(typeof window !== "undefined" ? window : this);
