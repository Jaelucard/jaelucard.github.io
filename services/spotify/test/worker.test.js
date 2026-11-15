import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

// Node can't load Cloudflare's built-in module. Substitute only its base class;
// the actual Worker and adapter code run unchanged against mocked state/fetch.
const workerFile = new URL('../src/worker.js', import.meta.url);
const adapterFile = new URL('../src/spotify.js', import.meta.url);
const source = (await readFile(workerFile, 'utf8'))
  .replace("import { DurableObject } from 'cloudflare:workers';", 'class DurableObject { constructor(ctx, env) { this.ctx = ctx; this.env = env; } }')
  .replace("from './spotify.js'", `from '${adapterFile.href}'`);
const { default: worker, SpotifySession } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

const SITE = 'https://jarrodlow.com';
const initialNow = Date.parse('2026-11-16T12:00:00.000Z');
const env = () => ({
  SPOTIFY_CLIENT_ID: 'client-id-private', SPOTIFY_CLIENT_SECRET: 'client-secret-private',
  SPOTIFY_REFRESH_TOKEN: 'refresh-token-private', SPOTIFY_CREDENTIAL_GENERATION: 'generation-1', SITE_ORIGIN: SITE,
});
const copy = (v) => v === undefined ? undefined : structuredClone(v);
class FakeStorage {
  constructor() { this.values = new Map(); this.failWrites = false; }
  async get(key) { return copy(this.values.get(key)); }
  async put(key, value) {
    if (this.failWrites) throw new Error('storage write failure');
    this.values.set(key, copy(value));
  }
}
const makeSession = (e = env(), storage = new FakeStorage()) => ({
  session: new SpotifySession({ storage }, e), storage,
});
const runSession = async (session) => (await session.fetch(new Request('https://internal/internal/now-playing'))).json();
const json = (data, status = 200, headers = {}) => new Response(JSON.stringify(data), { status, headers });
const track = {
  is_playing: true, currently_playing_type: 'track', progress_ms: 23000,
  item: { name: 'Example', artists: [{ name: 'Artist' }], duration_ms: 120000,
    external_urls: { spotify: 'https://open.spotify.com/track/example' }, album: { images: [] } },
};

function mockSpotify(t, opts = {}) {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push({ url: String(url), init });
    if (String(url).includes('accounts.spotify.com')) {
      if (opts.refresh) return opts.refresh(url, init);
      return json({ access_token: 'access-token-private', expires_in: 3600 });
    }
    if (opts.playback) return opts.playback(url, init);
    return json(track);
  });
  return calls;
}

test('coalesces concurrent requests, caches data and never exposes credentials', async (t) => {
  t.mock.method(Date, 'now', () => initialNow);
  const calls = mockSpotify(t);
  const { session } = makeSession();
  const results = await Promise.all(Array.from({ length: 8 }, () => runSession(session)));
  assert.equal(calls.length, 2);
  assert.ok(results.every((v) => v.status === 'playing' && v.fetchedAt === new Date(initialNow).toISOString()));
  assert.ok(!JSON.stringify(results).includes('private'));
  const next = await runSession(session);
  assert.equal(next.status, 'playing');
  assert.equal(calls.length, 2);
});

test('serves cached playback for ten seconds, then fetches a changed track', async (t) => {
  let now = initialNow;
  t.mock.method(Date, 'now', () => now);
  let playbackCalls = 0;
  mockSpotify(t, { playback: () => {
    playbackCalls++;
    return json(playbackCalls === 1 ? track : {
      ...track,
      item: { ...track.item, name: 'Next track', external_urls: { spotify: 'https://open.spotify.com/track/next' } },
    });
  } });
  const { session, storage } = makeSession();

  assert.equal((await runSession(session)).track.title, 'Example');
  now += 9_999;
  assert.equal((await runSession(session)).track.title, 'Example');
  assert.equal(playbackCalls, 1, 'the cache prevents early Spotify requests');
  assert.equal((await storage.get('spotify-session')).nextPollAt, initialNow + 10_000);
  now++;
  const next = await runSession(session);
  assert.equal(next.track.title, 'Next track');
  assert.equal(next.fetchedAt, new Date(now).toISOString());
  assert.equal(playbackCalls, 2, 'the changed track is fetched at the deadline');
});

test('persists replacement refresh token before querying playback', async (t) => {
  t.mock.method(Date, 'now', () => initialNow);
  const { session, storage } = makeSession();
  mockSpotify(t, {
    refresh: () => json({ access_token: 'access-private', refresh_token: 'replacement-private', expires_in: 3600 }),
    playback: async () => {
      assert.equal((await storage.get('spotify-session')).refreshToken, 'replacement-private');
      return json(track);
    },
  });
  const result = await runSession(session);
  assert.equal(result.status, 'playing');
  assert.ok(!JSON.stringify(result).includes('private'));
});

test('a storage failure during rotation fails closed without playback access', async (t) => {
  t.mock.method(Date, 'now', () => initialNow);
  const { session, storage } = makeSession();
  let playbackCalls = 0;
  mockSpotify(t, {
    refresh: () => { storage.failWrites = true; return json({ access_token: 'access-private', refresh_token: 'replacement-private', expires_in: 3600 }); },
    playback: () => { playbackCalls++; return json(track); },
  });
  assert.deepEqual(await runSession(session), { status: 'unavailable' });
  assert.equal(playbackCalls, 0);
});

test('cold restart observes persisted deadline, then refetches with the rotated token', async (t) => {
  let now = initialNow;
  t.mock.method(Date, 'now', () => now);
  const { session, storage } = makeSession();
  const observedTokens = [];
  const calls = mockSpotify(t, { refresh: (_url, init) => {
    observedTokens.push(init.body.get('refresh_token'));
    return json({ access_token: 'access-private', refresh_token: 'replacement-private', expires_in: 3600 });
  } });
  await runSession(session);
  const restarted = makeSession(env(), storage).session;
  assert.deepEqual(await runSession(restarted), { status: 'unavailable' }, 'a cold object cannot serve the lost cache');
  assert.equal(calls.length, 2, 'a cold object must not re-poll before the deadline');
  assert.equal((await storage.get('spotify-session')).cache, undefined, 'Spotify content is not persisted');
  now += 10000;
  assert.equal((await runSession(restarted)).status, 'playing');
  assert.deepEqual(observedTokens, ['refresh-token-private', 'replacement-private']);
  assert.equal(calls.length, 4, 'a new object refreshes once after the deadline');
});

test('a new credential generation resets rotation, failure state and cached track', async (t) => {
  t.mock.method(Date, 'now', () => initialNow);
  const first = env();
  const { session, storage } = makeSession(first);
  const tokens = [];
  mockSpotify(t, { refresh: (_url, init) => {
    tokens.push(init.body.get('refresh_token'));
    return json({ access_token: 'access-private', refresh_token: 'rotated-private', expires_in: 3600 });
  } });
  await runSession(session);
  const second = { ...first, SPOTIFY_CREDENTIAL_GENERATION: 'generation-2', SPOTIFY_REFRESH_TOKEN: 'new-bootstrap-private' };
  assert.equal((await runSession(makeSession(second, storage).session)).status, 'playing');
  assert.deepEqual(tokens, ['refresh-token-private', 'new-bootstrap-private']);
});

test('invalid grant persists a fail-closed state until credentials change', async (t) => {
  t.mock.method(Date, 'now', () => initialNow);
  let attempts = 0;
  mockSpotify(t, { refresh: () => { attempts++; return json({ error: 'invalid_grant', error_description: 'secret' }, 400); } });
  const { session, storage } = makeSession();
  assert.deepEqual(await runSession(session), { status: 'unavailable' });
  assert.deepEqual(await runSession(makeSession(env(), storage).session), { status: 'unavailable' });
  assert.equal(attempts, 1);
});

test('rate-limited responses respect persisted backoff and never expose the old cache', async (t) => {
  let now = initialNow;
  t.mock.method(Date, 'now', () => now);
  let playCalls = 0;
  mockSpotify(t, { playback: () => {
    playCalls++;
    return playCalls === 1 ? json(track) : json({}, 429, { 'Retry-After': '120' });
  } });
  const { session, storage } = makeSession();
  assert.equal((await runSession(session)).status, 'playing');
  now += 10000;
  assert.deepEqual(await runSession(session), { status: 'unavailable' });
  now += 35000;
  assert.deepEqual(await runSession(makeSession(env(), storage).session), { status: 'unavailable' });
  assert.equal(playCalls, 2);
});

test('unauthorized playback retries token refresh only once', async (t) => {
  t.mock.method(Date, 'now', () => initialNow);
  let refreshCalls = 0;
  let playbackCalls = 0;
  mockSpotify(t, {
    refresh: () => { refreshCalls++; return json({ access_token: `access-${refreshCalls}`, expires_in: 3600 }); },
    playback: () => { playbackCalls++; return playbackCalls === 1 ? json({}, 401) : json(track); },
  });
  assert.equal((await runSession(makeSession().session)).status, 'playing');
  assert.equal(refreshCalls, 2);
  assert.equal(playbackCalls, 2);
});

test('missing secrets or unavailable storage do not reveal details', async (t) => {
  t.mock.method(Date, 'now', () => initialNow);
  const invalid = { ...env(), SPOTIFY_REFRESH_TOKEN: '' };
  assert.deepEqual(await runSession(makeSession(invalid).session), { status: 'unavailable' });
  const { session, storage } = makeSession();
  storage.failWrites = true;
  assert.deepEqual(await runSession(session), { status: 'unavailable' });
});

test('public API allows only GET, exact origin and preflight; no token setter route', async () => {
  let calls = 0;
  const sessionEnv = { ...env(), SPOTIFY_SESSION: { idFromName: () => 'id', get: () => ({ fetch: async () => { calls++; return Response.json({ status: 'offline' }); } }) } };
  const req = (path, method = 'GET', origin = SITE) => new Request('https://worker.example' + path, { method, ...(origin ? { headers: { Origin: origin } } : {}) });
  const ok = await worker.fetch(req('/now-playing'), sessionEnv);
  assert.equal(ok.status, 200);
  assert.equal(ok.headers.get('access-control-allow-origin'), SITE);
  assert.equal(ok.headers.get('cache-control'), 'no-store');
  assert.deepEqual(await ok.json(), { status: 'offline' });
  const preflight = await worker.fetch(req('/now-playing', 'OPTIONS'), sessionEnv);
  assert.equal(preflight.status, 204);
  assert.equal(preflight.headers.get('access-control-allow-headers'), 'Cache-Control, Pragma');
  assert.equal((await worker.fetch(req('/now-playing', 'GET', 'https://evil.example'), sessionEnv)).status, 403);
  assert.equal((await worker.fetch(req('/now-playing', 'POST'), sessionEnv)).status, 405);
  assert.equal((await worker.fetch(req('/token', 'POST'), sessionEnv)).status, 404);
  assert.equal((await worker.fetch(req('/now-playing', 'GET', null), sessionEnv)).status, 200);
  assert.equal(calls, 2);
});

test('public API hides errors and worker configuration', async () => {
  const e = { ...env(), SPOTIFY_SESSION: { idFromName: () => { throw new Error('client-secret-private'); } } };
  const res = await worker.fetch(new Request('https://worker.example/now-playing'), e);
  assert.equal(res.status, 503);
  const body = await res.text();
  assert.equal(body, '{"status":"unavailable"}');
  assert.ok(!body.includes('private'));
});
