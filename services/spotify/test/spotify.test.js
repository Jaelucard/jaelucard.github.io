import test from 'node:test';
import assert from 'node:assert/strict';
import { getCurrentlyPlaying, mapPlayback, refreshAccessToken } from '../src/spotify.js';

const at = '2026-11-16T00:00:00.000Z';
const now = () => Date.parse(at);
const json = (value, status = 200, headers = {}) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json', ...headers } });
const track = (overrides = {}) => ({
  is_playing: true,
  currently_playing_type: 'track',
  progress_ms: 84000,
  item: {
    name: 'A song',
    artists: [{ name: 'First Artist' }, { name: 'Second Artist' }],
    external_urls: { spotify: 'https://open.spotify.com/track/123' },
    album: { images: [{ url: 'https://i.scdn.co/image/abc' }] },
    duration_ms: 192000,
    ...overrides,
  },
});

const mockPlayback = (response) => getCurrentlyPlaying({ accessToken: 'secret-access-token', fetchImpl: async () => response, now });

test('playing data is mapped using the time observed, with artists and approved URLs', async () => {
  const result = await mockPlayback(json(track()));
  assert.deepEqual(result, { ok: true, data: {
    status: 'playing', fetchedAt: at,
    track: { title: 'A song', artist: 'First Artist, Second Artist', spotifyUrl: 'https://open.spotify.com/track/123', artworkUrl: 'https://i.scdn.co/image/abc', durationMs: 192000, progressMs: 84000 },
  } });
});

test('paused track keeps its status and nullable progress is not fabricated', () => {
  const data = mapPlayback({ ...track(), is_playing: false, progress_ms: null }, at);
  assert.equal(data.status, 'paused');
  assert.equal(data.track.progressMs, undefined);
});

test('204 represents no active playback and is not an error', async () => {
  assert.deepEqual(await mockPlayback(new Response(null, { status: 204 })), { ok: true, data: { status: 'offline', fetchedAt: at } });
});

test('maps episodes using the show and episode cover', () => {
  const data = mapPlayback({ is_playing: true, currently_playing_type: 'episode', progress_ms: 10, item: {
    name: 'Episode name', show: { name: 'Show name' }, duration_ms: 8000,
    external_urls: { spotify: 'https://open.spotify.com/episode/123' }, images: [{ url: 'https://i.scdn.co/image/show' }],
  } }, at);
  assert.deepEqual(data.track, { title: 'Episode name', artist: 'Show name', spotifyUrl: 'https://open.spotify.com/episode/123', artworkUrl: 'https://i.scdn.co/image/show', durationMs: 8000, progressMs: 10 });
});

test('unsupported, unlinked or malformed items fail closed', () => {
  for (const body of [
    null, {}, { ...track(), item: null }, { ...track(), currently_playing_type: 'ad' },
    track({ is_local: true }), track({ external_urls: { spotify: 'https://open.spotify.com.evil.test/track' } }),
    track({ external_urls: { spotify: 'javascript:alert(1)' } }), track({ artists: [] }),
  ]) assert.deepEqual(mapPlayback(body, at), { status: 'unavailable', fetchedAt: at });
});

test('untrusted art, invalid progress and invalid duration are omitted', () => {
  const body = track({ duration_ms: -1, album: { images: [{ url: 'https://evil.test/cover' }] } });
  body.progress_ms = -8;
  const { track: result } = mapPlayback(body, at);
  assert.equal(result.artworkUrl, undefined);
  assert.equal(result.progressMs, undefined);
  assert.equal(result.durationMs, undefined);
  const exceeded = mapPlayback({ ...track(), progress_ms: 192001 }, at);
  assert.equal(exceeded.track.progressMs, undefined);
});

test('playback uses a private bearer and supports episodes', async () => {
  const result = await getCurrentlyPlaying({ accessToken: 'private-token', now, fetchImpl: async (url, init) => {
    assert.equal(url, 'https://api.spotify.com/v1/me/player/currently-playing?additional_types=episode');
    assert.equal(init.headers.Authorization, 'Bearer private-token');
    return json(track());
  } });
  assert.equal(result.data.status, 'playing');
  assert.ok(!JSON.stringify(result).includes('private-token'));
});

test('upstream failures are sanitized and 429 conveys retry interval', async () => {
  for (const [status, reason] of [[401, 'unauthorized'], [403, 'upstream_error'], [500, 'upstream_error']]) {
    const value = await mockPlayback(json({ access_token: 'secret' }, status));
    assert.deepEqual(value, { ok: false, reason });
    assert.ok(!JSON.stringify(value).includes('secret'));
  }
  assert.deepEqual(await mockPlayback(json({}, 429, { 'Retry-After': '12' })), { ok: false, reason: 'rate_limited', retryAfterSeconds: 12 });
  assert.deepEqual(await mockPlayback(json({}, 429)), { ok: false, reason: 'rate_limited' });
});

test('malformed JSON and network failures remain sanitized', async () => {
  assert.deepEqual(await mockPlayback(new Response('not json', { status: 200 })), { ok: false, reason: 'invalid_response' });
  const failed = await getCurrentlyPlaying({ accessToken: 'my-token', fetchImpl: async () => { throw new Error('my-token'); } });
  assert.deepEqual(failed, { ok: false, reason: 'network_error' });
});

test('requests time out even when fetch ignores abort', async () => {
  const result = await getCurrentlyPlaying({ accessToken: 'token', fetchImpl: () => new Promise(() => {}), timeoutMs: 10 });
  assert.deepEqual(result, { ok: false, reason: 'network_error' });
});

const creds = { clientId: 'client', clientSecret: 'secret', refreshToken: 'old-token' };

test('refresh uses Spotify token endpoint and retains previous token if no replacement is returned', async () => {
  const result = await refreshAccessToken({ ...creds, fetchImpl: async (url, init) => {
    assert.equal(url, 'https://accounts.spotify.com/api/token');
    assert.equal(init.method, 'POST');
    assert.equal(init.headers.Authorization, `Basic ${btoa('client:secret')}`);
    assert.equal(init.body.get('refresh_token'), 'old-token');
    return json({ access_token: 'new-access', expires_in: 3600 });
  } });
  assert.deepEqual(result, { ok: true, accessToken: 'new-access', refreshToken: 'old-token', expiresIn: 3600 });
});

test('refresh exposes rotated token internally for secure persistence', async () => {
  const result = await refreshAccessToken({ ...creds, fetchImpl: async () => json({ access_token: 'new-access', refresh_token: 'rotated', expires_in: 3600 }) });
  assert.deepEqual(result, { ok: true, accessToken: 'new-access', refreshToken: 'rotated', expiresIn: 3600 });
});

test('refresh errors do not expose credentials or response content', async () => {
  const expired = await refreshAccessToken({ ...creds, fetchImpl: async () => json({ error: 'invalid_grant', error_description: 'secret' }, 400) });
  assert.deepEqual(expired, { ok: false, reason: 'reauthorization_required' });
  const limited = await refreshAccessToken({ ...creds, fetchImpl: async () => json({ secret: 'old-token' }, 429, { 'Retry-After': '5' }) });
  assert.deepEqual(limited, { ok: false, reason: 'rate_limited', retryAfterSeconds: 5 });
  const invalid = await refreshAccessToken({ ...creds, fetchImpl: async () => json({ access_token: 'new', refresh_token: '', expires_in: 3600 }) });
  assert.deepEqual(invalid, { ok: false, reason: 'invalid_response' });
});
