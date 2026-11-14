/**
 * NOX HELION V16 WOW5 / five opt-in micro-interactions.
 * Presentation-only adapter, no DOM construction, network, persistence, timers,
 * navigation, event bus, or authorization decisions. Original UI belongs to #1.
 * ONLY call this module with origin-validated events from host owner #6.
 * Event field validation is defensive and does not authenticate the caller.
 */
const FRESH_MS = 120_000;
const MAX_CLOCK_SKEW_MS = 5_000;
const KINDS = new Set(['chat.token', 'chat.completed', 'chat.stopped', 'chat.failed']);
const ACK = new Set(['action.ack', 'action.error']);
function target(element) {
  if (!element?.dataset) throw new TypeError('Existing approved element required');
}
function isHostEvidence(event, now = Date.now(), freshness = FRESH_MS) {
  if (!event || typeof event !== 'object' ||
      event.source !== 'events.v3' ||
      typeof event.runId !== 'string' || !event.runId.trim() ||
      typeof event.timestamp !== 'string') return false;
  const timestamp = Date.parse(event.timestamp);
  return Number.isFinite(timestamp) && Number.isFinite(now) &&
    timestamp <= now + MAX_CLOCK_SKEW_MS &&
    timestamp >= now - freshness;
}
/** 1: verified CoreID progress ring accent; never alters the original progress geometry. */
export function applyCoreRingEvidence(element, evidence, now = Date.now()) {
  target(element);
  const good = isHostEvidence(evidence, now) &&
    evidence.state === 'VERIFIED' &&
    typeof evidence.coreId === 'string' && Boolean(evidence.coreId.trim()) &&
    typeof evidence.receiptId === 'string' && Boolean(evidence.receiptId.trim()) &&
    typeof evidence.percent === 'number' && Number.isFinite(evidence.percent) &&
    evidence.percent >= 0 && evidence.percent <= 100;
  element.dataset.noxWowRing = good ? 'verified' : 'unknown';
  if (element.style?.setProperty) {
    if (good) element.style.setProperty('--nox-wow-verified-level', String(evidence.percent / 100));
    else element.style.removeProperty?.('--nox-wow-verified-level');
  }
  return good;
}
/** 2: precision keyboard/mouse focus is CSS-only; bind no synthetic focus. */

/** 3: pulse only while a real streaming event has been received. */
export function applyStreamEvent(element, event, now = Date.now()) {
  target(element);
  const good = isHostEvidence(event, now) && KINDS.has(event.kind) &&
    typeof event.streamId === 'string' && Boolean(event.streamId.trim());
  if (!good) {
    element.dataset.noxWowStream = 'unknown';
    return false;
  }
  element.dataset.noxWowStream = event.kind === 'chat.token' ? 'active' :
    event.kind === 'chat.failed' ? 'error' : 'idle';
  return true;
}
/** 4: action ACK from host ONLY: no successful status for request/dispatch events. */
export function applyActionAck(element, event, now = Date.now()) {
  target(element);
  const good = isHostEvidence(event, now) && ACK.has(event.kind) &&
    typeof event.actionId === 'string' && Boolean(event.actionId.trim()) &&
    event.confirmed === true;
  element.dataset.noxWowAck = good ? (event.kind === 'action.ack' ? 'success' : 'error') : 'unknown';
  return good;
}
/** 5: source freshness, not HTTP fetch time. Missing timestamps must stay unknown. */
export function applyFeedFreshness(element, snapshot, now = Date.now()) {
  target(element);
  let state = 'unknown';
  if (snapshot && typeof snapshot.provider === 'string' && snapshot.provider.trim() &&
      typeof snapshot.sourceTimestamp === 'string') {
    const timestamp = Date.parse(snapshot.sourceTimestamp);
    if (Number.isFinite(timestamp) && timestamp <= now + MAX_CLOCK_SKEW_MS &&
        typeof snapshot.maxAgeMs === 'number' &&
        Number.isFinite(snapshot.maxAgeMs) && snapshot.maxAgeMs > 0 &&
        snapshot.maxAgeMs <= 86_400_000) {
      if (snapshot.status === 'OFFLINE' || snapshot.status === 'OFFLINE_CACHE') state = 'offline';
      else if (now - timestamp > snapshot.maxAgeMs) state = 'stale';
      else if (snapshot.status === 'CACHE') state = 'cached';
      else if (snapshot.status === 'LIVE') state = 'fresh';
    }
  }
  element.dataset.noxWowFeedState = state;
  return state;
}
/** One opt-in switch shared by all five. Setting does NOT enable WOW2 automatically. */
export function setWow5Enabled(root, enabled) {
  target(root);
  root.dataset.noxWow5 = enabled === true ? 'on' : 'off';
}
/** Host invokes when suspending, navigating away, unloading, or losing event trust. */
export function resetTransientSignals({ stream, ack } = {}) {
  if (stream) { target(stream); stream.dataset.noxWowStream = 'unknown'; }
  if (ack) { target(ack); ack.dataset.noxWowAck = 'unknown'; }
}
