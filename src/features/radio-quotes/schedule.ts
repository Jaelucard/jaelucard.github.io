// Singapore observes UTC+8 year-round, so its calendar days can be calculated
// without depending on the visitor's timezone or locale.
const DAY_MS = 24 * 60 * 60 * 1000;
const SINGAPORE_OFFSET_MS = 8 * 60 * 60 * 1000;
const MAX_TIMESTAMP_MS = 8_640_000_000_000_000 - DAY_MS;

function singaporeDay(timestampMs: number): number {
  if (!Number.isFinite(timestampMs) || Math.abs(timestampMs) > MAX_TIMESTAMP_MS) {
    throw new RangeError('timestampMs must be within the supported date range');
  }

  return Math.floor((timestampMs + SINGAPORE_OFFSET_MS) / DAY_MS);
}

/** Return the quote index for the Singapore calendar day containing timestampMs. */
export function dailyIndex(timestampMs: number, count: number): number {
  if (!Number.isSafeInteger(count) || count <= 0) {
    throw new RangeError('count must be a positive safe integer');
  }

  const remainder = singaporeDay(timestampMs) % count;
  return remainder === 0 ? 0 : remainder < 0 ? remainder + count : remainder;
}

/** Return the first Singapore midnight strictly after timestampMs, in epoch milliseconds. */
export function nextSingaporeMidnight(timestampMs: number): number {
  return (singaporeDay(timestampMs) + 1) * DAY_MS - SINGAPORE_OFFSET_MS;
}
