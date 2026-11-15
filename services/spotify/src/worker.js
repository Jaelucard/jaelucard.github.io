import { DurableObject } from 'cloudflare:workers';
import { getCurrentlyPlaying, refreshAccessToken } from './spotify.js';

const CACHE_MS = 10_000;
const FAILURE_BACKOFF_MS = 30_000;
const MAX_BACKOFF_MS = 86_400_000;
const RECORD_KEY = 'spotify-session';
const UNAVAILABLE = { status: 'unavailable' };

function configured(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function retryDelay(result) {
  const seconds = result.reason === 'rate_limited' ? result.retryAfterSeconds : undefined;
  return Math.min(MAX_BACKOFF_MS, Math.max(FAILURE_BACKOFF_MS, (seconds ?? 0) * 1000));
}

/** One object coordinates a single account's token and cached playback. */
export class SpotifySession extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.inFlight = null;
    this.accessToken = null;
    this.accessExpiresAt = 0;
    this.generation = null;
    // Keep Spotify metadata only in memory: it disappears on eviction.
    this.cache = null;
    this.cacheUntil = 0;
    this.localBackoffUntil = 0;
  }

  async fetch(request) {
    if (request.method !== 'GET' || new URL(request.url).pathname !== '/internal/now-playing') {
      return new Response('Not found', { status: 404 });
    }
    // Requests that overlap one upstream request share it, rather than rotating
    // tokens or hitting Spotify independently for each website visitor.
    if (!this.inFlight) {
      this.inFlight = this.readPlayback().catch(() => {
        this.localBackoffUntil = Date.now() + FAILURE_BACKOFF_MS;
        return UNAVAILABLE;
      }).finally(() => { this.inFlight = null; });
    }
    return Response.json(await this.inFlight, { headers: { 'Cache-Control': 'no-store' } });
  }

  async readPlayback() {
    const { SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN, SPOTIFY_CREDENTIAL_GENERATION } = this.env;
    if (![SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN, SPOTIFY_CREDENTIAL_GENERATION].every(configured)) return UNAVAILABLE;
    const now = Date.now();
    if (this.generation !== SPOTIFY_CREDENTIAL_GENERATION) {
      this.accessToken = null;
      this.accessExpiresAt = 0;
      this.cache = null;
      this.cacheUntil = 0;
      this.localBackoffUntil = 0;
      this.generation = SPOTIFY_CREDENTIAL_GENERATION;
    }
    if (now < this.localBackoffUntil) return UNAVAILABLE;

    let record = await this.ctx.storage.get(RECORD_KEY);
    if (!record || record.generation !== SPOTIFY_CREDENTIAL_GENERATION) {
      record = { generation: SPOTIFY_CREDENTIAL_GENERATION, refreshToken: SPOTIFY_REFRESH_TOKEN };
      await this.ctx.storage.put(RECORD_KEY, record);
    }
    if (!configured(record.refreshToken) || record.authInvalid || now < (record.backoffUntil || 0)) return UNAVAILABLE;
    if (this.cache && now < this.cacheUntil) return this.cache;
    // The object may have been evicted, losing its in-memory cache. Retain
    // only a non-content deadline so cold starts cannot repeatedly poll Spotify.
    if (now < (record.nextPollAt || 0)) return UNAVAILABLE;
    record = { ...record, nextPollAt: now + CACHE_MS };
    await this.ctx.storage.put(RECORD_KEY, record);

    const refresh = async () => {
      const result = await refreshAccessToken({
        clientId: SPOTIFY_CLIENT_ID,
        clientSecret: SPOTIFY_CLIENT_SECRET,
        refreshToken: record.refreshToken,
      });
      if (!result.ok) {
        this.cache = null;
        this.cacheUntil = 0;
        record = { ...record,
          ...(result.reason === 'reauthorization_required' ? { authInvalid: true } : { backoffUntil: Date.now() + retryDelay(result) }) };
        await this.ctx.storage.put(RECORD_KEY, record);
        return false;
      }
      // Persist any rotated token before the new access token is used or a
      // successful response is returned. Never expose either token to clients.
      if (record.refreshToken !== result.refreshToken) {
        record = { ...record, refreshToken: result.refreshToken };
        await this.ctx.storage.put(RECORD_KEY, record);
      }
      this.accessToken = result.accessToken;
      // Refresh early to avoid issuing requests close to expiry.
      this.accessExpiresAt = Date.now() + Math.max(0, result.expiresIn * 1000 - 60_000);
      return true;
    };

    if ((!this.accessToken || Date.now() >= this.accessExpiresAt) && !await refresh()) return UNAVAILABLE;
    let result = await getCurrentlyPlaying({ accessToken: this.accessToken });
    if (!result.ok && result.reason === 'unauthorized') {
      this.accessToken = null;
      this.accessExpiresAt = 0;
      if (!await refresh()) return UNAVAILABLE;
      result = await getCurrentlyPlaying({ accessToken: this.accessToken });
    }
    if (!result.ok) {
      this.cache = null;
      this.cacheUntil = 0;
      record = { ...record, backoffUntil: Date.now() + retryDelay(result) };
      await this.ctx.storage.put(RECORD_KEY, record);
      return UNAVAILABLE;
    }
    const cacheUntil = Date.now() + CACHE_MS;
    // Extend the deadline from completion time, including time spent awaiting
    // Spotify; no Spotify content is written to durable storage.
    record = { ...record, nextPollAt: cacheUntil };
    await this.ctx.storage.put(RECORD_KEY, record);
    this.cache = result.data;
    this.cacheUntil = cacheUntil;
    return result.data;
  }
}

function response(data, status, origin) {
  const headers = new Headers({
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Vary': 'Origin',
  });
  if (origin) headers.set('Access-Control-Allow-Origin', origin);
  return new Response(JSON.stringify(data), { status, headers });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin');
    // CORS is a browser policy, not authentication; this endpoint is public.
    const allowedOrigin = configured(env.SITE_ORIGIN) && origin === env.SITE_ORIGIN ? origin : null;
    if (url.pathname !== '/now-playing') return response({ error: 'Not found' }, 404, allowedOrigin);
    if (origin && !allowedOrigin) return response({ error: 'Origin not allowed' }, 403, null);
    if (request.method === 'OPTIONS') {
      if (!allowedOrigin) return response({ error: 'Origin not allowed' }, 403, null);
      return new Response(null, { status: 204, headers: {
        'Access-Control-Allow-Origin': allowedOrigin,
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Cache-Control, Pragma',
        'Access-Control-Max-Age': '600',
        'Vary': 'Origin',
      } });
    }
    if (request.method !== 'GET') return response({ error: 'Method not allowed' }, 405, allowedOrigin);
    try {
      const id = env.SPOTIFY_SESSION.idFromName('portfolio-owner');
      const stub = env.SPOTIFY_SESSION.get(id);
      const upstream = await stub.fetch('https://internal/internal/now-playing');
      if (!upstream.ok) return response(UNAVAILABLE, 503, allowedOrigin);
      return response(await upstream.json(), 200, allowedOrigin);
    } catch {
      return response(UNAVAILABLE, 503, allowedOrigin);
    }
  },
};
