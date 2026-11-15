import readline from 'node:readline/promises';
import { stdin, stdout } from 'node:process';
import { spawnSync } from 'node:child_process';
import { newState, authorizationUrl, startCallbackServer, exchangeCode, uploadSecrets, validWorkerName, wranglerEnvironment, REDIRECT_URI } from './authorize-lib.mjs';

function readSecret(prompt) {
  return new Promise((resolve, reject) => {
    const wasRaw = Boolean(stdin.isRaw);
    let value = '';
    stdout.write(prompt);
    const cleanup = () => {
      stdin.off('data', onData);
      stdin.setRawMode(wasRaw);
      stdin.pause();
      stdout.write('\n');
    };
    const onData = (data) => {
      for (const char of data.toString('utf8')) {
        if (char === '\r' || char === '\n') { cleanup(); resolve(value); return; }
        if (char === '\u0003' || char === '\u0004') { cleanup(); reject(new Error('cancelled')); return; }
        if (char === '\u007f' || char === '\b') { value = value.slice(0, -1); continue; }
        if (char >= ' ' && char !== '\u007f' && value.length < 512) value += char;
      }
    };
    stdin.setRawMode(true);
    stdin.on('data', onData);
    stdin.resume();
  });
}

async function main() {
  if (!stdin.isTTY || !stdout.isTTY) throw new Error('Run this helper directly in a local terminal.');
  stdout.write('This helper authorizes your Spotify account and updates secrets on your Cloudflare Worker.\n');
  stdout.write('The update creates a new Worker version. Run it only when you intend to make that remote change.\n');
  stdout.write(`Register this exact Spotify redirect URI first: ${REDIRECT_URI}\n`);
  const rl = readline.createInterface({ input: stdin, output: stdout });
  const accountId = (await rl.question('Intended Cloudflare account ID (32 lowercase hexadecimal characters): ')).trim();
  const env = wranglerEnvironment(accountId);
  if (!env) {
    rl.close();
    throw new Error('A valid 32-character lowercase hexadecimal Cloudflare account ID is required.');
  }
  const workerName = (await rl.question('Name of your verified Spotify Worker: ')).trim();
  if (!validWorkerName(workerName)) {
    rl.close();
    throw new Error('A valid Worker name is required: 1–63 letters, digits or hyphens, beginning and ending with a letter or digit.');
  }
  stdout.write(`The Worker secrets will be updated for Worker "${workerName}" in Cloudflare account ${accountId}.\n`);
  stdout.write('Verify that this Worker is the Spotify tracker and belongs to this account.\n');
  const confirm = (await rl.question('Are both the account and Worker correct? [y/N] ')).trim().toLowerCase();
  if (confirm !== 'y' && confirm !== 'yes') {
    rl.close();
    throw new Error('Cloudflare target selection was cancelled.');
  }
  const wrangler = spawnSync('wrangler', ['--version'], { stdio: 'ignore', shell: false, timeout: 5000, env });
  if (wrangler.error || wrangler.status !== 0) {
    rl.close();
    throw new Error('Wrangler is not available. Install it and sign in before running this helper.');
  }
  const clientId = (await rl.question('Spotify client ID: ')).trim();
  rl.close();
  const clientSecret = (await readSecret('Spotify client secret (hidden): ')).trim();
  if (!clientId || !clientSecret || clientId.includes(':')) throw new Error('A valid client ID and secret are required.');

  const state = newState();
  const callback = await startCallbackServer(state);
  stdout.write(`\nOpen this link in your browser and approve the Spotify permission:\n${authorizationUrl(clientId, state)}\n`);
  stdout.write('Waiting for authorization on this computer (five-minute limit)...\n');
  const result = await callback.result;
  if (result.status !== 'success') throw new Error('Authorization was denied, cancelled, or expired.');
  const token = await exchangeCode({ clientId, clientSecret, code: result.code });
  if (!token.ok) throw new Error('Spotify did not return a valid authorization. Check the app settings and try again.');
  stdout.write('Updating the Worker secrets through Wrangler...\n');
  const updated = await uploadSecrets({ accountId, workerName, clientId, clientSecret, refreshToken: token.refreshToken });
  if (!updated) throw new Error('Wrangler could not update the Worker. Verify Wrangler is installed and signed in, then retry authorization.');
  stdout.write('Worker secrets updated. You can close the Spotify authorization tab.\n');
}

main().catch((error) => {
  // Errors are deliberately chosen generic messages; never include provider responses.
  const safe = new Set([
    'Run this helper directly in a local terminal.',
    'Wrangler is not available. Install it and sign in before running this helper.',
    'A valid 32-character lowercase hexadecimal Cloudflare account ID is required.',
    'Cloudflare target selection was cancelled.',
    'A valid Worker name is required: 1–63 letters, digits or hyphens, beginning and ending with a letter or digit.',
    'A valid client ID and secret are required.',
    'Authorization was denied, cancelled, or expired.',
    'Spotify did not return a valid authorization. Check the app settings and try again.',
    'Wrangler could not update the Worker. Verify Wrangler is installed and signed in, then retry authorization.',
  ]);
  process.stderr.write(`${safe.has(error?.message) ? error.message : 'Authorization could not be completed. Check that port 8888 is available and retry.'}\n`);
  process.exitCode = 1;
});
