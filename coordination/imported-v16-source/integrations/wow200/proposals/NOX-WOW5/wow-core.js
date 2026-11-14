/* NOX WOW5: dependency-free safe presentation helpers. No host privilege. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.NoxWow5Core = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const SCHEMA = "NOX-INSTALLER-EVENT-v3";
  const STORAGE_KEY = "nox.wow5.view.v1";
  const MAX_AGE_MS = 30000;
  const MAX_STORE_AGE_MS = 86400000;
  const ERROR_HINTS = Object.freeze({
    OLLAMA_UNAVAILABLE: "Проверьте локальную службу Ollama; автоматический запуск не выполняется.",
    RAG_INDEX_LOCKED: "Индекс занят. Подождите завершения текущей операции.",
    GPU_TEMPERATURE_UNAVAILABLE: "Температура GPU недоступна: не запускать обучение без проверки.",
    DATASET_RIGHTS_UNVERIFIED: "Обучение заблокировано до подтверждения прав на данные.",
    CHECKPOINT_IDENTITY_MISMATCH: "Контрольная точка принадлежит другой модели или конфигурации.",
    MODEL_NOT_FOUND: "Локальная модель не обнаружена. Проверьте каталог моделей.",
    HTTP_TIMEOUT: "Истекло время ожидания. Проверьте подключение и повторите безопасно."
  });
  function str(v, max) {
    return typeof v === "string" ? v.replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, max) : "";
  }
  function validRun(v) { return typeof v === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$/.test(v); }
  function validHex(v) { return typeof v === "string" && /^[a-f0-9]{64}$/i.test(v); }
  function normalizeEvent(e, now) {
    if (!e || typeof e !== "object" || e.schema !== SCHEMA || !validRun(e.run_id)) return null;
    const t = Date.parse(e.timestamp_utc);
    if (!Number.isFinite(t) || t > now + 5000 || now - t > MAX_AGE_MS || !Number.isSafeInteger(e.event_sequence) || e.event_sequence < 0) return null;
    const kind = str(e.event_type, 64);
    if (!/^[a-z][a-z0-9._-]{0,63}$/.test(kind)) return null;
    return Object.freeze({runId:e.run_id, seq:e.event_sequence, type:kind, state:str(e.state,32),
      at:e.timestamp_utc, taskId:str(e.task_id,128),
      evidenceVerified:e.evidence_verified === true && validHex(e.receipt_sha256),
      receiptSha:e.evidence_verified === true && validHex(e.receipt_sha256) ? e.receipt_sha256.toLowerCase() : null});
  }
  function normalizedCitations(citations) {
    if (!Array.isArray(citations)) return [];
    return citations.slice(0, 12).flatMap((c) => {
      if (!c || typeof c !== "object" || !validHex(c.chunk_sha256) || !validHex(c.source_sha256)) return [];
      const title = str(c.file_name, 120);
      const id = str(c.source_id, 120);
      if (!title || !id) return [];
      const score = typeof c.score === "number" && Number.isFinite(c.score) ? Math.max(-1,Math.min(1,c.score)) : null;
      return [{title, id, sha:c.chunk_sha256.toLowerCase(), sourceSha:c.source_sha256.toLowerCase(), score}];
    });
  }
  function diagnostic(code, runId) {
    const name = str(code,64);
    if (!/^[A-Z][A-Z0-9_]{2,63}$/.test(name)) return null;
    return {code:name, runId:validRun(runId)?runId:"N/D",
      hint:ERROR_HINTS[name] || "Подробности в локальном журнале ошибок. Не повторяйте опасные операции автоматически."};
  }
  function allowedIds(ids) {
    if (!Array.isArray(ids) || ids.length !== 8 || new Set(ids).size !== 8 ||
      ids.some(x => typeof x !== "string" || !/^[A-Za-z0-9_-]{1,48}$/.test(x))) throw new Error("CORE_IDS_MUST_BE_EXACTLY_EIGHT");
    return ids.slice();
  }
  function restoreView(storage, ids, now) {
    try {
      const data = JSON.parse(storage.getItem(STORAGE_KEY) || "null");
      if (!data || data.v !== 1 || !Number.isFinite(data.ts) || data.ts > now || now - data.ts > MAX_STORE_AGE_MS) return {panel:null,focus:false};
      return {panel:ids.includes(data.panel) ? data.panel : null, focus:data.focus === true};
    } catch {return {panel:null,focus:false};}
  }
  function storeView(storage, ids, panel, focus, now) {
    if (panel !== null && !ids.includes(panel)) return false;
    try {storage.setItem(STORAGE_KEY, JSON.stringify({v:1,ts:now,panel,focus:focus===true})); return true;}
    catch {return false;}
  }
  return Object.freeze({SCHEMA, STORAGE_KEY, ERROR_HINTS, validRun, normalizeEvent,
    normalizedCitations, diagnostic, allowedIds, restoreView, storeView});
});
