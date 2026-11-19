'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');

const source = fs.readFileSync(path.join(__dirname, 'workspace-owner-capabilities.js'), 'utf8');
const originalSHA = '9b77c5011da892769c7332826c4b35bce581fb121960c13694638657735fc0ae';
const cap = settings => ({schema: 'NOX_NATIVE_UI_WORKSPACE_V1', settings, projects: false, tools: []});
const server = {stored: true, settings: {theme: 'amber'}, capabilities: {settings: true}, storage_scope: 'SERVER_SETTINGS'};

function runtime(native, respond, saved = {}) {
  const calls = [], storage = new Map(Object.entries(saved)), events = new Map();
  const root = {dataset: {}};
  const window = {
    NOX_NATIVE_OWNER: native,
    addEventListener(type, fn) { events.set(type, fn); },
    dispatchEvent(event) { events.get(event.type)?.(event); }
  };
  const context = vm.createContext({
    window, document: {documentElement: root, hidden: false},
    localStorage: {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, String(value))},
    matchMedia: () => ({matches: false}), setInterval: () => 1, setTimeout: () => 1, clearTimeout() {},
    CustomEvent: function(type, options) { this.type = type; this.detail = options.detail; },
    fetch: async (url, options = {}) => {
      const call = {url, method: options.method || 'GET', options}; calls.push(call);
      const result = await respond(call);
      assert.ok(result && Number.isInteger(result.status), 'fixture response required');
      return {ok: result.status >= 200 && result.status < 300, status: result.status, json: async () => result.body};
    }
  });
  vm.runInContext(source, context, {timeout: 1000});
  return {api: window.NoxWorkspace, calls, storage, root};
}

const tests = [
  ['only native capability load and pending-write guards differ from frozen9b77', async () => {
    const marker = '    // Native owner settings are selected by the existing authenticated capability route.\n';
    const next = "    try{response=await request('/api/settings');}";
    assert.equal(source.split(marker).length, 2);
    const a = source.indexOf(marker), b = source.indexOf(next, a);
    assert.ok(b > a);
    let inverse = source.slice(0, a) + source.slice(b);
    for (const line of [
      '  let nativeSettingsSupport=null;\n',
      "    if(native&&nativeSettingsSupport===null)throw Error('NATIVE_CAPABILITIES_PENDING_OR_UNVERIFIED');\n"
    ]) {
      assert.equal(inverse.split(line).length, 2);
      inverse = inverse.replace(line, '');
    }
    assert.equal(crypto.createHash('sha256').update(inverse).digest('hex'), originalSHA);
  }],
  ['native settingsfalse uses existing visual whitelist with zero legacy GET or POST', async () => {
    const r = runtime(true, call => {
      assert.equal(call.url, '/api/ui/capabilities'); assert.equal(call.method, 'GET');
      assert.equal(call.options.credentials, 'same-origin');
      return {status: 200, body: cap(false)};
    }, {'nox.native.visual.prefs': JSON.stringify({theme: 'arctic', motion: 'system', secret: 'excluded'})});
    const settings = await r.api.ready;
    assert.equal(settings.theme, 'arctic'); assert.equal(r.api.storageScope, 'BROWSER_VISUAL_PREFS');
    assert.equal(r.api.capabilities.settings, false);
    await r.api.set({motion: 'reduce'});
    assert.equal(r.api.settings.motion, 'reduce');
    await assert.rejects(r.api.set({notifications: true}), /NATIVE_SETTINGS_NOT_MOUNTED/);
    assert.deepEqual(r.calls.map(x => [x.method, x.url]), [['GET', '/api/ui/capabilities']]);
    assert.equal(JSON.parse(r.storage.get('nox.native.visual.prefs')).secret, undefined);
  }],
  ['unauthorized capabilities stays a visible rejection without settings request', async () => {
    const r = runtime(true, () => ({status: 401, body: {reason: 'OWNER_AUTH_REQUIRED'}}));
    await assert.rejects(r.api.ready, /OWNER_AUTH_REQUIRED/);
    await assert.rejects(r.api.set({theme: 'arctic'}), /NATIVE_CAPABILITIES_PENDING_OR_UNVERIFIED/);
    assert.equal(r.root.dataset.settingsError, 'OWNER_AUTH_REQUIRED');
    assert.equal(r.api.settings, undefined); assert.equal(r.api.storageScope, 'NATIVE_OWNER_PENDING');
    assert.deepEqual(r.calls.map(x => x.url), ['/api/ui/capabilities']);
  }],
  ['only exact schema and literal settings boolean admit a native branch', async () => {
    for (const body of [null, [], {}, cap('false'), cap(0), cap(null), {...cap(false), schema: 'OTHER'}]) {
      const r = runtime(true, () => ({status: 200, body}));
      await assert.rejects(r.api.ready, /NATIVE_UI_CAPABILITIES_UNVERIFIED/);
      await assert.rejects(r.api.set({theme: 'arctic'}), /NATIVE_CAPABILITIES_PENDING_OR_UNVERIFIED/);
      assert.equal(r.root.dataset.settingsError, 'NATIVE_UI_CAPABILITIES_UNVERIFIED');
      assert.equal(r.api.settings, undefined);
      assert.deepEqual(r.calls.map(x => x.url), ['/api/ui/capabilities']);
    }
  }],
  ['explicit native settings support retains the original server path', async () => {
    const r = runtime(true, call => ({status: 200, body: call.url === '/api/ui/capabilities' ? cap(true) : server}));
    await r.api.ready; await r.api.set({theme: 'arctic'});
    assert.equal(r.api.storageScope, 'SERVER_SETTINGS');
    assert.deepEqual(r.calls.map(x => [x.method, x.url]), [
      ['GET', '/api/ui/capabilities'], ['GET', '/api/settings'], ['POST', '/api/settings']]);
    assert.equal(r.calls[2].options.headers['X-NOX-Session'], undefined);
  }],
  ['non-native settings and session write behavior remain unchanged', async () => {
    const r = runtime(false, call => ({status: 200, body: call.url === '/api/nox/session' ? {token: 'public-fixture'} : server}));
    await r.api.ready; await r.api.set({theme: 'arctic'});
    assert.deepEqual(r.calls.map(x => [x.method, x.url]), [
      ['GET', '/api/settings'], ['GET', '/api/nox/session'], ['POST', '/api/settings']]);
    assert.equal(r.calls[2].options.headers['X-NOX-Session'], 'public-fixture');
  }],
  ['native pending capability request cannot send an early legacy settings write', async () => {
    let release;
    const pending = new Promise(resolve => { release = resolve; });
    const r = runtime(true, () => pending);
    await assert.rejects(r.api.set({theme: 'arctic'}), /NATIVE_CAPABILITIES_PENDING_OR_UNVERIFIED/);
    assert.deepEqual(r.calls.map(x => [x.method, x.url]), [['GET', '/api/ui/capabilities']]);
    release({status: 200, body: cap(false)});
    await r.api.ready; await r.api.set({theme: 'arctic'});
    assert.equal(r.api.settings.theme, 'arctic');
    assert.equal(r.calls.length, 1);
  }],
  ['supported native migration can write within load without waiting for its own ready promise', async () => {
    const r = runtime(true, call => ({status: 200, body: call.url === '/api/ui/capabilities' ? cap(true) :
      call.method === 'GET' ? {...server, stored: false} : server}), {'nox.fx': 'MAX'});
    let timer;
    try {
      await Promise.race([r.api.ready, new Promise((_, reject) => { timer = setTimeout(() => reject(Error('migration deadlock')), 200); })]);
    } finally { clearTimeout(timer); }
    assert.deepEqual(r.calls.map(x => [x.method, x.url]), [
      ['GET', '/api/ui/capabilities'], ['GET', '/api/settings'], ['POST', '/api/settings']]);
    assert.equal(JSON.parse(r.calls[2].options.body).mode, 'MAX');
  }]
];

(async () => {
  for (const [name, run] of tests) { await run(); process.stdout.write('PASS ' + name + '\n'); }
  process.stdout.write(`${tests.length}/${tests.length} PASS\n`);
})().catch(error => { process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1; });
