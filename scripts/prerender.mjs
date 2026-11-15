import { readFile, writeFile, rm } from 'node:fs/promises';
import { render } from '../.ssr/entry-server.js';

const path = new URL('../dist/index.html', import.meta.url);
const html = await readFile(path, 'utf8');
const placeholder = '<div id="root"></div>';
if (!html.includes(placeholder)) throw new Error('Could not find the app root in dist/index.html');
await writeFile(path, html.replace(placeholder, () => `<div id="root">${render()}</div>`));
await rm(new URL('../.ssr', import.meta.url), { recursive: true, force: true });
