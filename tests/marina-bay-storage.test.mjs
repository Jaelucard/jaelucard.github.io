import test from 'node:test';
import assert from 'node:assert/strict';
import { BEST_LAP_KEY, readBestLap, saveBestLap } from '../src/features/marina-bay/storage.ts';

function memoryStorage(initial = null) {
  let value = initial;
  let writes = 0;
  return {
    getItem(key) { assert.equal(key, BEST_LAP_KEY); return value; },
    setItem(key, next) { assert.equal(key, BEST_LAP_KEY); value = next; writes++; },
    get writes() { return writes; },
  };
}
const record = (seconds = 120.42) => ({ version: 1, layout: 'marina-bay-19-turns', rules: 'arcade-v1', seconds });

test('best lap round-trips while a slower or equal result cannot replace it', () => {
  const storage = memoryStorage();
  assert.equal(readBestLap(storage), null);
  assert.equal(saveBestLap(120.42, storage), true);
  assert.equal(readBestLap(storage), 120.42);
  assert.equal(saveBestLap(130, storage), true);
  assert.equal(saveBestLap(120.42, storage), true);
  assert.equal(storage.writes, 1);
  assert.equal(saveBestLap(119.01, storage), true);
  assert.equal(readBestLap(storage), 119.01);
  assert.equal(storage.writes, 2);
});

test('ignores corrupt records and incompatible layouts, schemas and rules', () => {
  const records = ['not json', 'null', '120', '[]', '{}',
    JSON.stringify({ ...record(), version: 2 }), JSON.stringify({ ...record(), layout: 'other-track' }),
    JSON.stringify({ ...record(), rules: 'old-physics' }), JSON.stringify(record('120')),
    JSON.stringify(record(-1)), JSON.stringify(record(0)), JSON.stringify(record(0.1)), JSON.stringify(record(null)),
    '{"version":1,"layout":"marina-bay-19-turns","rules":"arcade-v1","seconds":1e999}'];
  for (const raw of records) assert.equal(readBestLap(memoryStorage(raw)), null, raw);
  assert.equal(readBestLap(memoryStorage(JSON.stringify(record()))), 120.42);
});

test('storage failures and server-side calls never prevent playing', () => {
  const blocked = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('quota'); } };
  assert.equal(readBestLap(blocked), null);
  assert.equal(saveBestLap(100, blocked), false);
  assert.equal(readBestLap(null), null);
  assert.equal(saveBestLap(100, null), false);
  assert.equal(readBestLap(), null);
  assert.equal(saveBestLap(100), false);
});

test('invalid new times are not persisted and corrupt records can be replaced', () => {
  const storage = memoryStorage('broken');
  for (const value of [NaN, Infinity, -Infinity, 0, 0.1, -3]) assert.equal(saveBestLap(value, storage), false);
  assert.equal(storage.writes, 0);
  assert.equal(saveBestLap(123.4, storage), true);
  assert.equal(readBestLap(storage), 123.4);
});

test('an impossible stored record cannot prevent a legitimate new best', () => {
  const storage = memoryStorage(JSON.stringify(record(0.1)));
  assert.equal(readBestLap(storage), null);
  assert.equal(saveBestLap(104.16, storage), true);
  assert.equal(readBestLap(storage), 104.16);
});
