import test from 'node:test';
import assert from 'node:assert/strict';
import { formatTime, isStale, parsePlayback } from '../src/features/spotify/playback.ts';

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
