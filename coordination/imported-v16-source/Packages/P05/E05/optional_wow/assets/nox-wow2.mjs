/** NOX V16 WOW2 tiny adaptation API. No polling, no event bus, no DOM creation.
 * Call from the existing approved events.v3 host bridge, never from foreign pages.
 * Nothing is trusted just because it was sent to this function. Unknown -> idle.
 */
const VALID = new Set(['idle','working','training','warning','offline']);
const MAX_AGE_MS = 120_000;
export function bindCoreActivity(element, event, now = Date.now()) {
  if (!element?.dataset) throw new TypeError('Existing core element required');
  const valid = Boolean(event && VALID.has(event.activity) &&
    typeof event.runId === 'string' && event.runId.trim().length > 0 &&
    typeof event.source === 'string' && event.source.trim().length > 0 &&
    typeof event.timestamp === 'string' &&
    Number.isFinite(Date.parse(event.timestamp)) &&
    Date.parse(event.timestamp) <= now + 5_000 &&
    now - Date.parse(event.timestamp) >= 0 &&
    now - Date.parse(event.timestamp) <= MAX_AGE_MS);
  element.dataset.noxWowActivity = valid ? event.activity : 'idle';
  return valid;
}
/** Opt-in toggle only: main shell and full UI remain owned by #1/#6. */
export function setWowEnabled(root, enabled) {
  if (!root?.dataset) throw new TypeError('Existing host root required');
  root.dataset.noxWow = enabled === true ? 'on' : 'off';
}
