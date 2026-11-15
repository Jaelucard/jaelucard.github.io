import assert from 'node:assert/strict';
import { setImmediate as flush } from 'node:timers/promises';
import test from 'node:test';

import { startPlaybackPolling } from '../src/features/spotify/polling.ts';

function browser(t) {
  const oldDocument = globalThis.document;
  const oldWindow = globalThis.window;
  const document = Object.assign(new EventTarget(), { visibilityState: 'visible' });
  const window = new EventTarget();
  globalThis.document = document;
  globalThis.window = window;
  t.after(() => {
    if (oldDocument === undefined) delete globalThis.document;
    else globalThis.document = oldDocument;
    if (oldWindow === undefined) delete globalThis.window;
    else globalThis.window = oldWindow;
  });
  return { document, window };
}

test('a mounted tracker picks up a new track on the next scheduled check', async (t) => {
  browser(t);
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let current = { status: 'playing', track: { title: 'Track A' } };
  const shown = [];
  const stop = startPlaybackPolling(async () => current, (playback) => shown.push(playback.track.title));
  await flush();
  assert.deepEqual(shown, ['Track A']);
  current = { status: 'playing', track: { title: 'Track B' } };
  t.mock.timers.tick(4_999);
  await flush();
  assert.deepEqual(shown, ['Track A']);
  t.mock.timers.tick(1);
  await flush();
  assert.deepEqual(shown, ['Track A', 'Track B']);
  stop();
});

test('returning to the page refreshes immediately without overlapping requests', async (t) => {
  const { document, window } = browser(t);
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let resolveFirst;
  let calls = 0;
  let active = 0;
  let maxActive = 0;
  const shown = [];
  const stop = startPlaybackPolling(async () => {
    calls++;
    active++;
    maxActive = Math.max(maxActive, active);
    if (calls === 1) await new Promise((resolve) => { resolveFirst = resolve; });
    active--;
    return { status: 'playing', track: { title: calls === 1 ? 'Track A' : 'Track B' } };
  }, (playback) => shown.push(playback.track.title));

  document.visibilityState = 'hidden';
  document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(calls, 1);
  document.visibilityState = 'visible';
  document.dispatchEvent(new Event('visibilitychange'));
  window.dispatchEvent(new Event('pageshow'));
  assert.equal(calls, 1);
  resolveFirst();
  await flush();
  assert.equal(calls, 2);
  assert.equal(maxActive, 1);
  assert.deepEqual(shown, ['Track A', 'Track B']);

  window.dispatchEvent(new Event('pageshow'));
  await flush();
  assert.equal(calls, 3);
  stop();
});

test('cleanup aborts an in-flight request and prevents updates and later checks', async (t) => {
  const { document, window } = browser(t);
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let resolveRequest;
  let signal;
  let calls = 0;
  let updates = 0;
  const stop = startPlaybackPolling((requestSignal) => {
    calls++;
    signal = requestSignal;
    return new Promise((resolve) => { resolveRequest = resolve; });
  }, () => { updates++; });
  stop();
  assert.equal(signal.aborted, true);
  resolveRequest({ status: 'offline' });
  await flush();
  t.mock.timers.tick(30_000);
  document.dispatchEvent(new Event('visibilitychange'));
  window.dispatchEvent(new Event('pageshow'));
  await flush();
  assert.equal(calls, 1);
  assert.equal(updates, 0);
});

test('a failed request reports unavailable and still schedules another check', async (t) => {
  browser(t);
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const shown = [];
  let calls = 0;
  const stop = startPlaybackPolling(async () => {
    calls++;
    if (calls === 1) throw new Error('network error');
    return { status: 'offline' };
  }, (playback) => shown.push(playback?.status ?? 'unavailable'));
  await flush();
  t.mock.timers.tick(5_000);
  await flush();
  assert.deepEqual(shown, ['unavailable', 'offline']);
  stop();
});
