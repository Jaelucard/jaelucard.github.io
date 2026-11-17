import { MIN_LAP_TIME } from './simulation.ts';

export const BEST_LAP_KEY = 'jarrod:marina-bay:19-turns:arcade-v1:best';
const SCHEMA_VERSION = 1;
const LAYOUT = 'marina-bay-19-turns';

export type BestLapStorage = {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
};

function browserStorage(): BestLapStorage | null {
  try { return typeof window === 'undefined' ? null : window.localStorage; }
  catch { return null; }
}

export function readBestLap(storage: BestLapStorage | null = browserStorage()): number | null {
  try {
    const raw = storage?.getItem(BEST_LAP_KEY);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== 'object') return null;
    const record = value as Record<string, unknown>;
    return record.version === SCHEMA_VERSION && record.layout === LAYOUT
      && record.rules === 'arcade-v1' && typeof record.seconds === 'number'
      && Number.isFinite(record.seconds) && record.seconds >= MIN_LAP_TIME ? record.seconds : null;
  } catch { return null; }
}

/** Keep an existing faster result, including one saved by another browser tab. */
export function saveBestLap(seconds: number, storage: BestLapStorage | null = browserStorage()): boolean {
  if (!storage || !Number.isFinite(seconds) || seconds < MIN_LAP_TIME) return false;
  try {
    const previous = readBestLap(storage);
    if (previous !== null && previous <= seconds) return true;
    storage.setItem(BEST_LAP_KEY, JSON.stringify({
      version: SCHEMA_VERSION, layout: LAYOUT, rules: 'arcade-v1', seconds,
    }));
    return true;
  } catch { return false; }
}
