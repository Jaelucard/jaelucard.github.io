# Spotify now-playing service

This service supplies the portfolio's Radio Check component. A Cloudflare Worker exposes a read-only `/now-playing` endpoint; one SQLite-backed Durable Object coordinates requests for the owner's Spotify account. Spotify credentials stay in Worker secrets and private Durable Object storage, not in the website bundle.

The endpoint is public: CORS permits browser requests from `SITE_ORIGIN`, but CORS is not authentication. Anyone who knows the endpoint can request the public playback status. Only the intended track, artist, artwork, Spotify link, timing and status are returned; device information and credentials are not returned.

## Local checks

From the repository root:

```sh
npm test
npm run build
```

The test suite uses fictional Spotify responses and mock Durable Object storage. A build without `VITE_SPOTIFY_STATUS_URL` displays an unavailable state and does not connect to Spotify. To test the frontend against a local service, set `VITE_SPOTIFY_STATUS_URL` to that service's public status URL before running Vite. Never put Spotify credentials in a `VITE_` variable: its value is included in browser code.

## Setup for a real account

These steps change external account settings or deploy a Worker. Run them only when you intend to publish the service. They have not been performed by the test suite.

1. In Spotify for Developers, create an app owned by a Premium account. Register **exactly** `http://127.0.0.1:8888/callback` as a redirect URI. The helper requests only the `user-read-currently-playing` scope. Keep the client secret private.
2. Install the official Cloudflare Wrangler CLI in a local environment and sign in to the intended Cloudflare account. The helper expects `wrangler` on your terminal's `PATH`. Wrangler is not included in this repository's dependencies. Use `wrangler whoami` or the Cloudflare dashboard to verify the intended account ID, and check its Workers and Durable Objects plan and limits before deploying.
3. In the Cloudflare dashboard, check whether the Worker name in `services/spotify/wrangler.jsonc` is already in use. Choose a unique name in that file if it belongs to another Worker; deploying over an existing name would update that Worker. After verifying the account and name, deploy the initially unconfigured service from the repository root:

   ```sh
   export CLOUDFLARE_ACCOUNT_ID="your-verified-account-id"
   wrangler deploy --config services/spotify/wrangler.jsonc
   ```

   Without credentials, it returns `unavailable`. The configuration attaches the Worker to `radio.jarrodlow.com` as a custom domain; Cloudflare creates its DNS record and certificate. It also permits browser access from `https://jarrodlow.com`; adjust `SITE_ORIGIN` if the production origin changes.
4. In a local terminal, run:

   ```sh
   node services/spotify/scripts/authorize.mjs
   ```

   Enter the verified Cloudflare account ID and the exact name of the Worker you deployed, then the Spotify client ID and client secret when prompted. Confirm the account and Worker identity before the helper uploads any secrets. The helper hides secret entry, listens only on `127.0.0.1`, validates the OAuth state, and sends the resulting credentials and a fresh generation marker to `wrangler secret bulk` via standard input. It does not write them to a file. **The secret update creates a new Worker version.** Do not paste credentials, authorization codes, or callback URLs into chat or commit them.
5. Set the GitHub Actions repository variable `SPOTIFY_STATUS_URL` to `https://radio.jarrodlow.com/now-playing` and `SPOTIFY_FALLBACK_URL` to the Worker's `workers.dev` URL ending in `/now-playing`, then publish the website change through the repository's authorized deployment process. The Pages workflow passes these non-secret URLs to the Vite build as `VITE_SPOTIFY_STATUS_URL` and `VITE_SPOTIFY_FALLBACK_URL`. The frontend uses the fallback only when the primary endpoint cannot be reached or returns an HTTP error; valid offline and unavailable states are not retried.
6. Check the deployed endpoint and website against your Spotify playback. Browser visitors need no Spotify login to view the public state.

The Worker expects the secrets `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REFRESH_TOKEN` and `SPOTIFY_CREDENTIAL_GENERATION`. The helper updates them together. The Durable Object stores a rotated refresh token privately and uses the generation marker to replace it after reauthorization. Spotify refresh tokens expire after six months; rerun the helper to authorize again. See [Spotify's refresh-token documentation](https://developer.spotify.com/documentation/web-api/tutorials/refreshing-tokens).

The service coalesces concurrent requests and caches playback in memory for 10 seconds. With the website checking every 5 seconds, a change generally appears within about 15 seconds while the page is active, plus network and Spotify delays. The shorter cache can result in up to twice as many Spotify requests as the previous 20-second cache during continuous use; it still protects Spotify from a separate request for every visitor. Cache data does not survive Durable Object eviction; a persisted poll deadline limits calls after a restart and may temporarily show `unavailable`. Rate limits and upstream errors also fail closed, so updates can take longer. The visualizer is decorative: it is controlled by playback state, not by audio or a song's beat.
