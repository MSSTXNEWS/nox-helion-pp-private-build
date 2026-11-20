/* NOX B1: source-only browser/Node bridge for an authenticated readback cursor.
 * No model POST, UI mutation, native S03 connection, or storage implementation.
 * Host MUST provide: independently authorized envelope verification, a fresh
 * owner/STOP/lease gate, and an ATOMIC durable unique-(conversation,exchange)
 * commitTerminalAndAck + readCommitted pair. The record is projected by event_id
 * using an idempotent UI upsert; ACK must only be transmitted after this returns.
 * A JS client cannot independently verify the server's HMAC-SHA256 signature.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.NOXB1ReconnectDedup = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const ID = /^[A-Za-z0-9._:-]{1,128}$/;
  const SHA = /^[0-9a-f]{64}$/;
  const CURSOR = /^[A-Za-z0-9_-]{1,1200}$/;

  class HoldClientReconnect extends Error {
    constructor(code) { super(code); this.name = 'HoldClientReconnect'; this.code = code; }
  }
  const hold = code => { throw new HoldClientReconnect(code); };
  function stringMatch(v, regex, code) {
    if (typeof v !== 'string' || !regex.test(v)) hold(code);
    return v;
  }
  function snapshotPacket(packet, expected) {
    if (!packet || typeof packet !== 'object' || Array.isArray(packet)) hold('HOLD_CLIENT_PACKET');
    if (!expected || typeof expected !== 'object' || Array.isArray(expected)) hold('HOLD_CLIENT_SCOPE');
    const conversation_id = stringMatch(expected.conversation_id, ID, 'HOLD_CLIENT_SCOPE');
    const exchange_id = stringMatch(expected.exchange_id, ID, 'HOLD_CLIENT_SCOPE');
    if (packet.conversation_id !== conversation_id || packet.exchange_id !== exchange_id)
      hold('HOLD_CLIENT_CROSS_TURN');
    if (packet.readback_only !== true || typeof packet.emit_terminal !== 'boolean')
      hold('HOLD_CLIENT_NOT_READBACK');
    // Copy primitive fields BEFORE untrusted async host callbacks can mutate input.
    return Object.freeze({
      conversation_id, exchange_id,
      event_id: stringMatch(packet.event_id, SHA, 'HOLD_CLIENT_EVENT_ID'),
      next_cursor: stringMatch(packet.next_cursor, CURSOR, 'HOLD_CLIENT_CURSOR'),
      response_sha256: stringMatch(packet.response_sha256, SHA, 'HOLD_CLIENT_RESPONSE_PROOF'),
      s03_proof_sha256: stringMatch(packet.s03_proof_sha256, SHA, 'HOLD_CLIENT_S03_PROOF'),
      emit_terminal: packet.emit_terminal,
      readback_only: true
    });
  }
  function recordMatches(record, p) {
    return record && typeof record === 'object' && !Array.isArray(record) &&
      record.conversation_id === p.conversation_id &&
      record.exchange_id === p.exchange_id &&
      record.event_id === p.event_id &&
      record.next_cursor === p.next_cursor &&
      record.response_sha256 === p.response_sha256 &&
      record.s03_proof_sha256 === p.s03_proof_sha256 &&
      record.durable === true;
  }
  async function acceptTerminal(packet, expected, host) {
    const p = snapshotPacket(packet, expected);
    if (!host || typeof host !== 'object' ||
        typeof host.authorizeEnvelope !== 'function' ||
        typeof host.freshPermit !== 'function' ||
        typeof host.commitTerminalAndAck !== 'function' ||
        typeof host.readCommitted !== 'function') hold('HOLD_CLIENT_HOST_CONTRACT');
    // Verification MUST be scoped to a trusted authenticated serving endpoint,
    // not a user-controlled boolean. True in a synthetic test != native proof.
    try {
      if ((await host.freshPermit(p)) !== true) hold('HOLD_CLIENT_OWNER_REVOKED');
      if ((await host.authorizeEnvelope(p)) !== true) hold('HOLD_CLIENT_UNVERIFIED');
      if ((await host.freshPermit(p)) !== true) hold('HOLD_CLIENT_OWNER_REVOKED');
      if (p.emit_terminal) {
        // Atomic commit MUST use UNIQUE(conversation_id, exchange_id) and
        // reject an existing row with a different event_id, proof or cursor.
        // Same-event retries are idempotent. No content or model call here.
        const result = await host.commitTerminalAndAck(p);
        if (result !== 'COMMITTED' && result !== 'ALREADY_COMMITTED')
          hold('HOLD_CLIENT_ATOMIC_COMMIT');
      }
      // Even a 'no terminal' ACK must prove local durable commit, not silently
      // consume a possibly unrendered response.
      const stored = await host.readCommitted(p.conversation_id, p.exchange_id);
      if (!recordMatches(stored, p)) hold('HOLD_CLIENT_ACK_WITNESS');
      if ((await host.freshPermit(p)) !== true) hold('HOLD_CLIENT_OWNER_REVOKED');
      return Object.freeze({
        readback_only: true, conversation_id: p.conversation_id,
        exchange_id: p.exchange_id, projection_event_id: p.event_id,
        ack_cursor: p.next_cursor, safe_to_ack: true, model_post: false
      });
    } catch (e) {
      if (e instanceof HoldClientReconnect) throw e;
      throw new HoldClientReconnect('HOLD_CLIENT_CALLBACK_OR_STORE');
    }
  }
  return Object.freeze({acceptTerminal, HoldClientReconnect});
});
