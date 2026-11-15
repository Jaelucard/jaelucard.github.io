import { createServer } from 'node:http';
import { randomBytes, randomUUID, timingSafeEqual } from 'node:crypto';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const REDIRECT_URI = 'http://127.0.0.1:8888/callback';
const AUTH_URL = 'https://accounts.spotify.com/authorize';
const TOKEN_URL = 'https://accounts.spotify.com/api/token';
const REQUIRED_SCOPE = 'user-read-currently-playing';
const CONFIG_PATH = fileURLToPath(new URL('../wrangler.jsonc', import.meta.url));

export function newState() {
  return randomBytes(32).toString('base64url');
}

export function authorizationUrl(clientId, state) {
  const url = new URL(AUTH_URL);
  url.search = new URLSearchParams({ client_id: clientId, response_type: 'code', redirect_uri: REDIRECT_URI, scope: REQUIRED_SCOPE, state }).toString();
  return url.toString();
}

function equalState(a, b) {
  const left = Buffer.from(a, 'utf8');
  const right = Buffer.from(b, 'utf8');
  return left.length === right.length && timingSafeEqual(left, right);
}

/** Parse an incoming callback without exposing an authorization code to logs. */
export function parseCallback(rawUrl, expectedState) {
  let url;
  try { url = new URL(rawUrl, REDIRECT_URI); } catch { return { status: 'invalid' }; }
  if (url.pathname !== '/callback') return { status: 'not_found' };
  const states = url.searchParams.getAll('state');
  if (states.length !== 1 || !equalState(states[0], expectedState)) return { status: 'invalid' };
  const errors = url.searchParams.getAll('error');
  const codes = url.searchParams.getAll('code');
  if (errors.length === 1 && !codes.length) return { status: 'denied' };
  if (errors.length || codes.length !== 1 || !codes[0] || codes[0].length > 4096) return { status: 'invalid' };
  return { status: 'success', code: codes[0] };
}

/** Listen only on loopback and expire the callback after five minutes. */
export async function startCallbackServer(expectedState, { timeoutMs = 300_000, port = 8888 } = {}) {
  let settle;
  const result = new Promise((resolve) => { settle = resolve; });
  let settled = false;
  let timer;
  let boundPort = port;
  const finish = (value) => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    settle(value);
    server.close();
  };
  const server = createServer((request, response) => {
    response.setHeader('Cache-Control', 'no-store');
    response.setHeader('Referrer-Policy', 'no-referrer');
    response.setHeader('X-Content-Type-Options', 'nosniff');
    response.setHeader('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'");
    if (request.method !== 'GET' || request.headers.host !== `127.0.0.1:${boundPort}`) {
      response.writeHead(400, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('Invalid request.');
      return;
    }
    const parsed = parseCallback(request.url, expectedState);
    if (parsed.status === 'not_found' || parsed.status === 'invalid') {
      response.writeHead(parsed.status === 'not_found' ? 404 : 400, { 'Content-Type': 'text/plain; charset=utf-8' });
      response.end('Invalid or expired authorization request.');
      return;
    }
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    response.end(`<!doctype html><meta charset="utf-8"><title>Spotify authorization</title><script>history.replaceState(null,'','/');</script><p>${parsed.status === 'success' ? 'Authorization received. You can close this tab and return to your terminal.' : 'Authorization was not granted. You can close this tab.'}</p>`);
    finish(parsed);
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => { server.off('error', reject); resolve(); });
  });
  boundPort = server.address().port;
  timer = setTimeout(() => finish({ status: 'expired' }), timeoutMs);
  return { result, port: boundPort, close: () => finish({ status: 'cancelled' }) };
}

/** Exchange the callback code; errors are deliberately non-sensitive. */
export async function exchangeCode({ clientId, clientSecret, code, fetchImpl = fetch, timeoutMs = 10_000 }) {
  try {
    const response = await fetchImpl(TOKEN_URL, {
      method: 'POST',
      headers: { Authorization: `Basic ${Buffer.from(`${clientId}:${clientSecret}`).toString('base64')}`, 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ grant_type: 'authorization_code', code, redirect_uri: REDIRECT_URI }),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) return { ok: false };
    const body = await response.json();
    if (typeof body.refresh_token !== 'string' || !body.refresh_token.trim()) return { ok: false };
    if (typeof body.scope !== 'string' || !body.scope.split(/\s+/).includes(REQUIRED_SCOPE)) return { ok: false };
    return { ok: true, refreshToken: body.refresh_token };
  } catch {
    return { ok: false };
  }
}

/** Push credentials directly to Wrangler stdin; never expose process output. */
/** The target account must be explicitly supplied, never inherited implicitly. */
export function wranglerEnvironment(accountId, inherited = process.env) {
  if (typeof accountId !== 'string' || !/^[0-9a-f]{32}$/.test(accountId)) return null;
  return { ...inherited, CLOUDFLARE_ACCOUNT_ID: accountId };
}

/** Restrict the chosen name to values that also work as a workers.dev label. */
export function validWorkerName(value) {
  return typeof value === 'string' && value.length <= 63 && /^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$/.test(value);
}

export async function uploadSecrets({ accountId, workerName, clientId, clientSecret, refreshToken, spawnImpl = spawn, generation = randomUUID() }) {
  const env = wranglerEnvironment(accountId);
  if (!env || !validWorkerName(workerName)) return false;
  return new Promise((resolve) => {
    let child;
    try {
      child = spawnImpl('wrangler', ['secret', 'bulk', '--name', workerName, '--config', CONFIG_PATH], { stdio: ['pipe', 'ignore', 'ignore'], shell: false, env });
      child.once('error', () => resolve(false));
      child.once('close', (code) => resolve(code === 0));
      child.stdin.on('error', () => resolve(false));
      child.stdin.end(JSON.stringify({ SPOTIFY_CLIENT_ID: clientId, SPOTIFY_CLIENT_SECRET: clientSecret, SPOTIFY_REFRESH_TOKEN: refreshToken, SPOTIFY_CREDENTIAL_GENERATION: generation }));
    } catch {
      resolve(false);
    }
  });
}
