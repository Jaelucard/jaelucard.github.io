export type PlaybackStatus = 'playing' | 'paused' | 'offline' | 'unavailable';

export interface Track {
  title: string;
  artist: string;
  spotifyUrl: string;
  artworkUrl?: string;
  durationMs?: number;
  progressMs?: number;
}

export interface Playback {
  status: PlaybackStatus;
  track?: Track;
  fetchedAt?: string;
}

const validStatus = new Set<PlaybackStatus>(['playing', 'paused', 'offline', 'unavailable']);

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function spotifyUrl(value: unknown, image = false): string | undefined {
  if (typeof value !== 'string') return undefined;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    const allowed = image
      ? host === 'i.scdn.co' || host.endsWith('.scdn.co') || host.endsWith('.spotifycdn.com')
      : host === 'open.spotify.com';
    return url.protocol === 'https:' && allowed && !url.username && !url.password ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function milliseconds(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : undefined;
}

/** Validate the public endpoint before using its data in the page. */
export function parsePlayback(value: unknown, receivedAt = Date.now()): Playback | null {
  if (!object(value) || typeof value.status !== 'string' || !validStatus.has(value.status as PlaybackStatus)) return null;
  const status = value.status as PlaybackStatus;
  const fetchedAt = typeof value.fetchedAt === 'string' && Number.isFinite(Date.parse(value.fetchedAt)) ? value.fetchedAt : undefined;
  if (status !== 'playing' && status !== 'paused') return { status, fetchedAt };
  // Never treat an undated or implausibly future observation as live.
  if (!fetchedAt || Date.parse(fetchedAt) > receivedAt + 30_000) return null;
  if (!object(value.track)) return null;
  const { title, artist } = value.track;
  const link = spotifyUrl(value.track.spotifyUrl);
  if (typeof title !== 'string' || !title.trim() || typeof artist !== 'string' || !artist.trim() || !link) return null;
  const durationMs = milliseconds(value.track.durationMs);
  let progressMs = milliseconds(value.track.progressMs);
  if (progressMs !== undefined && durationMs !== undefined) progressMs = Math.min(progressMs, durationMs);
  return { status, fetchedAt, track: { title, artist, spotifyUrl: link, artworkUrl: spotifyUrl(value.track.artworkUrl, true), durationMs, progressMs } };
}

export function formatTime(value: number): string {
  const seconds = Math.floor(Math.max(0, value) / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

/** A dated observation must not remain live beyond the allowed age. */
export function isStale(playback: Playback, now: number, staleMs: number): boolean {
  return playback.fetchedAt !== undefined && now - Date.parse(playback.fetchedAt) > staleMs;
}
