import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { REDIRECT_URI, authorizationUrl, newState, parseCallback, startCallbackServer, exchangeCode, uploadSecrets, validWorkerName, wranglerEnvironment } from '../scripts/authorize-lib.mjs';

const accountId = 'a'.repeat(32);
const workerName = 'example-radio-worker';

test('Cloudflare account must be a supplied canonical account ID', () => {
  for (const invalid of [undefined, null, '', 'a'.repeat(31), 'a'.repeat(33), 'g'.repeat(32), 'A'.repeat(32), `${accountId}\n`]) {
    assert.equal(wranglerEnvironment(invalid, { CLOUDFLARE_ACCOUNT_ID: 'existing' }), null);
  }
  assert.deepEqual(wranglerEnvironment(accountId, { PATH: '/bin', CLOUDFLARE_ACCOUNT_ID: 'wrong-account' }), {
    PATH: '/bin', CLOUDFLARE_ACCOUNT_ID: accountId,
  });
});

test('invalid account IDs never launch Wrangler', async () => {
  let spawned = false;
  const result = await uploadSecrets({ accountId: 'not-an-account', workerName, clientId: 'c', clientSecret: 's', refreshToken: 'r', spawnImpl: () => { spawned = true; } });
  assert.equal(result, false);
  assert.equal(spawned, false);
});

test('Worker name must be explicit and safe for workers.dev', async () => {
  for (const value of ['a', workerName, 'a'.repeat(63), 'Worker42']) assert.equal(validWorkerName(value), true);
  for (const value of [undefined, '', '-start', 'end-', 'with_underscore', 'with space', 'a'.repeat(64), 'name\n', '--config']) {
    assert.equal(validWorkerName(value), false);
    let spawned = false;
    const result = await uploadSecrets({ accountId, workerName: value, clientId: 'c', clientSecret: 's', refreshToken: 'r', spawnImpl: () => { spawned = true; } });
    assert.equal(result, false);
    assert.equal(spawned, false);
  }
});

test('authorization URL uses the minimal scope and explicit loopback', () => {
  const first = newState();
  const second = newState();
  assert.notEqual(first, second);
  assert.ok(first.length >= 40);
  const url = new URL(authorizationUrl('client-id', first));
  assert.equal(url.origin, 'https://accounts.spotify.com');
  assert.equal(url.searchParams.get('scope'), 'user-read-currently-playing');
  assert.equal(url.searchParams.get('redirect_uri'), REDIRECT_URI);
  assert.equal(url.searchParams.get('state'), first);
});

test('callback requires exact state, one code and no error', () => {
  assert.deepEqual(parseCallback('/callback?state=bad&code=secret-code', 'good'), { status: 'invalid' });
  assert.deepEqual(parseCallback('/callback?state=good&state=good&code=secret-code', 'good'), { status: 'invalid' });
  assert.deepEqual(parseCallback('/callback?state=good&code=a&code=b', 'good'), { status: 'invalid' });
  assert.deepEqual(parseCallback('/callback?state=good&error=access_denied', 'good'), { status: 'denied' });
  assert.deepEqual(parseCallback('/callback?state=good&code=secret-code', 'good'), { status: 'success', code: 'secret-code' });
  assert.deepEqual(parseCallback('/wrong?state=good&code=secret-code', 'good'), { status: 'not_found' });
});

test('loopback listener rejects a mismatch, then accepts the valid callback without echoing secrets', async () => {
  const callback = await startCallbackServer('correct-state', { port: 0, timeoutMs: 1000 });
  const base = `http://127.0.0.1:${callback.port}`;
  const bad = await fetch(`${base}/callback?state=bad&code=private-code`);
  assert.equal(bad.status, 400);
  assert.ok(!(await bad.text()).includes('private-code'));
  const good = await fetch(`${base}/callback?state=correct-state&code=private-code`);
  assert.equal(good.status, 200);
  assert.equal(good.headers.get('cache-control'), 'no-store');
  assert.equal(good.headers.get('referrer-policy'), 'no-referrer');
  assert.ok(!(await good.text()).includes('private-code'));
  assert.deepEqual(await callback.result, { status: 'success', code: 'private-code' });
});

test('callback expires and closes automatically', async () => {
  const callback = await startCallbackServer('state', { port: 0, timeoutMs: 20 });
  assert.deepEqual(await callback.result, { status: 'expired' });
});

test('code exchange verifies scope and keeps errors sanitized', async () => {
  const args = { clientId: 'client', clientSecret: 'private-secret', code: 'private-code' };
  const result = await exchangeCode({ ...args, fetchImpl: async (url, init) => {
    assert.equal(url, 'https://accounts.spotify.com/api/token');
    assert.equal(init.method, 'POST');
    assert.equal(init.body.get('redirect_uri'), REDIRECT_URI);
    assert.equal(init.body.get('code'), args.code);
    return new Response(JSON.stringify({ refresh_token: 'private-refresh', scope: 'user-read-currently-playing' }), { status: 200 });
  } });
  assert.deepEqual(result, { ok: true, refreshToken: 'private-refresh' });
  const missingScope = await exchangeCode({ ...args, fetchImpl: async () => new Response(JSON.stringify({ refresh_token: 'secret', scope: 'other' })) });
  assert.deepEqual(missingScope, { ok: false });
  const upstreamError = await exchangeCode({ ...args, fetchImpl: async () => { throw new Error('private-secret private-code'); } });
  assert.deepEqual(upstreamError, { ok: false });
  const malformed = await exchangeCode({ ...args, fetchImpl: async () => new Response('bad JSON') });
  assert.deepEqual(malformed, { ok: false });
});

test('secrets go only to Wrangler stdin, never arguments or displayed output', async () => {
  let args, options, body = '';
  const child = new EventEmitter();
  child.stdin = new PassThrough();
  child.stdin.on('data', (chunk) => { body += chunk; });
  child.stdin.on('end', () => child.emit('close', 0));
  const ok = await uploadSecrets({ accountId, workerName, clientId: 'client', clientSecret: 'private-secret', refreshToken: 'private-refresh', generation: 'new-generation', spawnImpl: (cmd, argv, opts) => {
    assert.equal(cmd, 'wrangler'); args = argv; options = opts; return child;
  } });
  assert.equal(ok, true);
  assert.deepEqual(args.slice(0, 4), ['secret', 'bulk', '--name', workerName]);
  assert.equal(args.includes('private-secret'), false);
  assert.equal(args.includes('private-refresh'), false);
  assert.deepEqual(options.stdio, ['pipe', 'ignore', 'ignore']);
  assert.equal(options.shell, false);
  assert.equal(options.env.CLOUDFLARE_ACCOUNT_ID, accountId);
  assert.deepEqual(JSON.parse(body), { SPOTIFY_CLIENT_ID: 'client', SPOTIFY_CLIENT_SECRET: 'private-secret', SPOTIFY_REFRESH_TOKEN: 'private-refresh', SPOTIFY_CREDENTIAL_GENERATION: 'new-generation' });
});

test('Wrangler launch errors fail without leaking provider content', async () => {
  const ok = await uploadSecrets({ accountId, workerName, clientId: 'c', clientSecret: 'private', refreshToken: 'private', spawnImpl: () => { throw new Error('private'); } });
  assert.equal(ok, false);
});
