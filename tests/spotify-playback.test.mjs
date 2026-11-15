import test from 'node:test';
import assert from 'node:assert/strict';
import { fetchPlayback, formatTime, isStale, parsePlayback } from '../src/features/spotify/playback.ts';

const now = Date.parse('2026-11-16T00:00:00Z');
const valid = () => ({
  status: 'playing', fetchedAt: new Date(now).toISOString(),
  track: { title: 'Sample Track', artist: 'Sample Artist', spotifyUrl: 'https://open.spotify.com/track/example', artworkUrl: 'https://i.scdn.co/image/example', progressMs: 1000, durationMs: 10000 },
});

test('accepts valid playing and paused track data with Spotify links', () => {
  const input = valid();
  assert.equal(parsePlayback(input, now)?.track?.title, 'Sample Track');
  input.status = 'paused';
  assert.equal(parsePlayback(input, now)?.status, 'paused');
});

test('requires an observation time for track states and rejects future observations', () => {
  const input = valid();
  delete input.fetchedAt;
  assert.equal(parsePlayback(input, now), null);
  input.fetchedAt = new Date(now + 31000).toISOString();
  assert.equal(parsePlayback(input, now), null);
  input.fetchedAt = 'invalid';
  assert.equal(parsePlayback(input, now), null);
});

test('does not render unsafe or spoofed Spotify URLs', () => {
  for (const spotifyUrl of ['javascript:alert(1)', 'http://open.spotify.com/track/x', 'https://open.spotify.com.attacker.test/track/x', 'https://user:pass@open.spotify.com/track/x']) {
    const input = valid();
    input.track.spotifyUrl = spotifyUrl;
    assert.equal(parsePlayback(input, now), null);
  }
  const input = valid();
  input.track.artworkUrl = 'https://cdn.attacker.test/art.png';
  assert.equal(parsePlayback(input, now)?.track?.artworkUrl, undefined);
});

test('clamps excessive progress and omits invalid timing', () => {
  const input = valid();
  input.track.progressMs = 20000;
  assert.equal(parsePlayback(input, now)?.track?.progressMs, 10000);
  input.track.progressMs = -1;
  input.track.durationMs = NaN;
  const result = parsePlayback(input, now);
  assert.equal(result?.track?.progressMs, undefined);
  assert.equal(result?.track?.durationMs, undefined);
});

test('accepts offline states but rejects malformed playing data', () => {
  assert.equal(parsePlayback({status:'offline'}, now)?.status, 'offline');
  assert.equal(parsePlayback({status:'unavailable'}, now)?.status, 'unavailable');
  assert.equal(parsePlayback({status:'playing'}, now), null);
  assert.equal(parsePlayback({status:'unexpected'}, now), null);
  assert.equal(formatTime(84000), '1:24');
});

test('treats an epoch timestamp as stale instead of missing', () => {
  const input = valid();
  input.fetchedAt = '1970-01-01T00:00:00.000Z';
  const playback = parsePlayback(input, now);
  assert.equal(isStale(playback, now, 90000), true);
  assert.equal(isStale(parsePlayback(valid(), now), now, 90000), false);
});


const primary = 'https://radio.example.test/now-playing';
const backup = 'https://worker.example.test/now-playing';
const response = (value, status = 200) => new Response(JSON.stringify(value), { status });

test('uses backup when primary network request fails', async () => {
  const urls = [];
  const result = await fetchPlayback(primary, backup, new AbortController().signal, { fetchImpl: async (url, options) => {
    urls.push(url);
    assert.equal(options.cache, 'no-store');
    if (url === primary) throw new Error('network failure');
    return response({ status: 'offline' });
  } });
  assert.equal(result?.status, 'offline');
  assert.deepEqual(urls, [primary, backup]);
});

test('uses backup after primary HTTP error; both failures return no data', async () => {
  let calls = 0;
  const result = await fetchPlayback(primary, backup, new AbortController().signal, { fetchImpl: async () => {
    calls++;
    return calls === 1 ? response({}, 503) : response({ status: 'offline' });
  } });
  assert.equal(result?.status, 'offline');
  assert.equal(calls, 2);
  const failed = await fetchPlayback(primary, backup, new AbortController().signal, { fetchImpl: async () => { throw new Error('private diagnostic'); } });
  assert.equal(failed, null);
});

test('successful offline or unavailable response does not query backup', async () => {
  for (const status of ['offline', 'unavailable']) {
    let calls = 0;
    const result = await fetchPlayback(primary, backup, new AbortController().signal, { fetchImpl: async () => { calls++; return response({ status }); } });
    assert.equal(result?.status, status);
    assert.equal(calls, 1);
  }
});

test('malformed and stale primary results do not trigger fallback', async () => {
  let calls = 0;
  const malformed = await fetchPlayback(primary, backup, new AbortController().signal, { fetchImpl: async () => { calls++; return new Response('not JSON'); } });
  assert.equal(malformed, null);
  assert.equal(calls, 1);
  const input = valid();
  input.fetchedAt = '1970-01-01T00:00:00.000Z';
  const stale = await fetchPlayback(primary, backup, new AbortController().signal, { fetchImpl: async () => { calls++; return response(input); } });
  assert.equal(isStale(stale, Date.now(), 90000), true);
  assert.equal(calls, 2);
});

test('cancelling the primary prevents a backup request', async () => {
  const controller = new AbortController();
  let calls = 0;
  const pending = fetchPlayback(primary, backup, controller.signal, { fetchImpl: () => { calls++; return new Promise(() => {}); } });
  controller.abort();
  assert.equal(await pending, null);
  assert.equal(calls, 1);
});

test('a timed-out primary tries backup and aborts the underlying request', async () => {
  let calls = 0;
  let firstSignal;
  const result = await fetchPlayback(primary, backup, new AbortController().signal, { timeoutMs: 10, fetchImpl: async (_url, options) => {
    calls++;
    if (calls === 1) { firstSignal = options.signal; return new Promise(() => {}); }
    return response({ status: 'offline' });
  } });
  assert.equal(firstSignal.aborted, true);
  assert.equal(result?.status, 'offline');
  assert.equal(calls, 2);
});

test('cancelling during backup stops without hanging', async () => {
  const controller = new AbortController();
  let beginBackup;
  const started = new Promise((resolve) => { beginBackup = resolve; });
  let calls = 0;
  const pending = fetchPlayback(primary, backup, controller.signal, { fetchImpl: async () => {
    calls++;
    if (calls === 1) throw new Error('offline');
    beginBackup();
    return new Promise(() => {});
  } });
  await started;
  controller.abort();
  assert.equal(await pending, null);
  assert.equal(calls, 2);
});

test('equivalent primary and backup URLs are attempted once', async () => {
  let calls = 0;
  const result = await fetchPlayback('https://RADIO.example.test:443/now-playing', 'https://radio.example.test/now-playing', new AbortController().signal, { fetchImpl: async () => { calls++; throw new Error('failed'); } });
  assert.equal(result, null);
  assert.equal(calls, 1);
});
