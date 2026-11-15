// Hosting-neutral Spotify API adapter. Never send refresh results directly to a client.
const TOKEN_URL = 'https://accounts.spotify.com/api/token';
const PLAYBACK_URL = 'https://api.spotify.com/v1/me/player/currently-playing?additional_types=episode';
const DEFAULT_TIMEOUT_MS = 8000;

function plainString(value) {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function safeUrl(value, hostAllowed) {
  if (typeof value !== 'string') return undefined;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password || url.port || !hostAllowed(url.hostname)) return undefined;
    return url.href;
  } catch {
    return undefined;
  }
}

const spotifyLink = (value) => safeUrl(value, (hostname) => hostname === 'open.spotify.com');
const spotifyImage = (value) => safeUrl(value, (hostname) => hostname === 'i.scdn.co');

function firstImage(images) {
  if (!Array.isArray(images)) return undefined;
  for (const image of images) {
    const url = spotifyImage(image?.url);
    if (url) return url;
  }
  return undefined;
}

function duration(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : undefined;
}

function observationTime(now) {
  return new Date(now()).toISOString();
}

/** Convert only supported Spotify items into data safe for the public endpoint. */
export function mapPlayback(body, fetchedAt) {
  const unavailable = { status: 'unavailable', fetchedAt };
  if (!body || typeof body !== 'object' || typeof body.is_playing !== 'boolean') return unavailable;
  const item = body.item;
  if (!item || typeof item !== 'object' || !['track', 'episode'].includes(body.currently_playing_type)) return unavailable;
  if (item.is_local === true) return unavailable;

  const title = plainString(item.name);
  const url = spotifyLink(item.external_urls?.spotify);
  let artist;
  let artwork;
  if (body.currently_playing_type === 'track') {
    artist = Array.isArray(item.artists) ? item.artists.map((entry) => plainString(entry?.name)).filter(Boolean).join(', ') : undefined;
    artwork = firstImage(item.album?.images);
  } else {
    artist = plainString(item.show?.name);
    artwork = firstImage(item.images) ?? firstImage(item.show?.images);
  }
  if (!title || !artist || !url) return unavailable;

  const track = { title, artist, spotifyUrl: url };
  if (artwork) track.artworkUrl = artwork;
  const durationMs = duration(item.duration_ms);
  const progressMs = duration(body.progress_ms);
  if (durationMs !== undefined) track.durationMs = durationMs;
  if (progressMs !== undefined && (durationMs === undefined || progressMs <= durationMs)) track.progressMs = progressMs;
  return { status: body.is_playing ? 'playing' : 'paused', track, fetchedAt };
}

function retryAfter(response) {
  const value = response.headers?.get('retry-after');
  if (value && /^\d+$/.test(value)) return Math.min(Number(value), 86400);
  return undefined;
}

function httpFailure(response) {
  if (response.status === 429) {
    const delay = retryAfter(response);
    return delay === undefined ? { ok: false, reason: 'rate_limited' } : { ok: false, reason: 'rate_limited', retryAfterSeconds: delay };
  }
  return { ok: false, reason: response.status === 401 ? 'unauthorized' : 'upstream_error' };
}

async function withTimeout(action, timeoutMs) {
  const controller = new AbortController();
  let timer;
  try {
    return await Promise.race([
      action(controller.signal),
      new Promise((_, reject) => {
        timer = setTimeout(() => {
          controller.abort();
          reject(new Error('timeout'));
        }, timeoutMs);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

/** Fetch the current status; return sanitized failures, never a raw Spotify response. */
export async function getCurrentlyPlaying({ accessToken, fetchImpl = fetch, timeoutMs = DEFAULT_TIMEOUT_MS, now = Date.now }) {
  if (!plainString(accessToken)) return { ok: false, reason: 'unauthorized' };
  try {
    return await withTimeout(async (signal) => {
      const response = await fetchImpl(PLAYBACK_URL, {
        headers: { Authorization: `Bearer ${accessToken}` },
        signal,
      });
      if (response.status === 204) return { ok: true, data: { status: 'offline', fetchedAt: observationTime(now) } };
      if (!response.ok) return httpFailure(response);
      let body;
      try { body = await response.json(); } catch { return { ok: false, reason: 'invalid_response' }; }
      return { ok: true, data: mapPlayback(body, observationTime(now)) };
    }, timeoutMs);
  } catch {
    return { ok: false, reason: 'network_error' };
  }
}

/**
 * Refresh on the server. The returned token values are secret and must be stored
 * securely by the hosting layer; they must never be included in public output.
 */
export async function refreshAccessToken({ clientId, clientSecret, refreshToken, fetchImpl = fetch, timeoutMs = DEFAULT_TIMEOUT_MS }) {
  if (!plainString(clientId) || !plainString(clientSecret) || !plainString(refreshToken)) return { ok: false, reason: 'not_configured' };
  try {
    return await withTimeout(async (signal) => {
      const response = await fetchImpl(TOKEN_URL, {
        method: 'POST',
        headers: {
          Authorization: `Basic ${btoa(`${clientId}:${clientSecret}`)}`,
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({ grant_type: 'refresh_token', refresh_token: refreshToken }),
        signal,
      });
      if (!response.ok) {
        if (response.status === 400) {
          let body;
          try { body = await response.json(); } catch { /* sanitized failure below */ }
          if (body?.error === 'invalid_grant') return { ok: false, reason: 'reauthorization_required' };
        }
        return httpFailure(response);
      }
      let body;
      try { body = await response.json(); } catch { return { ok: false, reason: 'invalid_response' }; }
      const accessToken = plainString(body?.access_token);
      const expiresIn = body?.expires_in;
      if (!accessToken || typeof expiresIn !== 'number' || !Number.isFinite(expiresIn) || expiresIn <= 0) return { ok: false, reason: 'invalid_response' };
      // A present but malformed replacement must never silently discard rotation.
      if (body.refresh_token !== undefined && !plainString(body.refresh_token)) return { ok: false, reason: 'invalid_response' };
      return { ok: true, accessToken, refreshToken: body.refresh_token ?? refreshToken, expiresIn };
    }, timeoutMs);
  } catch {
    return { ok: false, reason: 'network_error' };
  }
}
