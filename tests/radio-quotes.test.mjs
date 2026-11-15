import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import test from 'node:test';

import { dailyIndex, nextSingaporeMidnight } from '../src/features/radio-quotes/schedule.ts';

const DAY_MS = 24 * 60 * 60 * 1000;
const timestamp = (value) => Date.parse(value);

test('the quote changes at midnight Singapore time and remains stable between midnights', () => {
  const midnight = timestamp('2026-05-01T16:00:00.000Z');
  const before = dailyIndex(midnight - 1, 11);
  const after = dailyIndex(midnight, 11);

  assert.equal(after, (before + 1) % 11);
  assert.equal(dailyIndex(midnight + DAY_MS - 1, 11), after);
  assert.equal(nextSingaporeMidnight(midnight - 1), midnight);
  assert.equal(nextSingaporeMidnight(midnight), midnight + DAY_MS);
});

test('Singapore midnight handles the year rollover', () => {
  const beforeNewYear = timestamp('2026-12-31T15:59:59.999Z');
  const newYear = timestamp('2026-12-31T16:00:00.000Z');

  assert.equal(nextSingaporeMidnight(beforeNewYear), newYear);
  assert.equal(nextSingaporeMidnight(newYear), timestamp('2027-01-01T16:00:00.000Z'));
  assert.equal(dailyIndex(newYear, 9), (dailyIndex(beforeNewYear, 9) + 1) % 9);
});

test('negative epoch days use a nonnegative index and the list repeats', () => {
  const start = timestamp('1969-12-31T16:00:00.000Z');

  assert.equal(dailyIndex(start - 1, 7), 6);
  assert.equal(dailyIndex(start, 7), 0);
  assert.equal(nextSingaporeMidnight(start - 1), start);
  assert.equal(dailyIndex(start + 7 * DAY_MS, 7), dailyIndex(start, 7));
  assert.equal(dailyIndex(start - 7 * DAY_MS, 7), dailyIndex(start, 7));
});

test('invalid quote counts and unsupported timestamps are rejected', () => {
  for (const count of [0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => dailyIndex(0, count), RangeError);
  }
  for (const time of [NaN, Infinity, -Infinity, Number.MAX_VALUE]) {
    assert.throws(() => dailyIndex(time, 3), RangeError);
    assert.throws(() => nextSingaporeMidnight(time), RangeError);
  }
});

test('the same UTC instant produces the same result in different host timezones', () => {
  const moduleUrl = new URL('../src/features/radio-quotes/schedule.ts', import.meta.url).href;
  const script = `import { dailyIndex, nextSingaporeMidnight } from ${JSON.stringify(moduleUrl)};
    const time = Date.parse('2026-12-31T16:00:00.000Z');
    console.log(JSON.stringify([dailyIndex(time, 9), nextSingaporeMidnight(time)]));`;
  const results = ['UTC', 'Asia/Singapore', 'America/New_York'].map((timezone) => {
    const child = spawnSync(process.execPath, ['--input-type=module', '-e', script], {
      encoding: 'utf8',
      env: { ...process.env, TZ: timezone },
    });
    assert.equal(child.status, 0, child.stderr);
    return child.stdout.trim();
  });

  assert.equal(results[0], results[1]);
  assert.equal(results[1], results[2]);
});
