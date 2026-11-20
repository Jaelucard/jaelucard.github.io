import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import { extname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const directory = resolve(fileURLToPath(new URL('../out/', import.meta.url)));
const host = '127.0.0.1';
const port = Number(process.env.PORT ?? 4173);
const types = {
  '.css': 'text/css', '.html': 'text/html; charset=utf-8', '.js': 'text/javascript',
  '.json': 'application/json', '.txt': 'text/plain; charset=utf-8', '.svg': 'image/svg+xml',
  '.jpeg': 'image/jpeg', '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp',
  '.mp4': 'video/mp4', '.webm': 'video/webm', '.woff2': 'font/woff2',
};

try {
  await stat(resolve(directory, 'index.html'));
} catch {
  console.error('Run npm run build before previewing the static export.');
  process.exit(1);
}

createServer(async (request, response) => {
  try {
    const { pathname } = new URL(request.url, `http://${host}`);
    const path = resolve(directory, `.${decodeURIComponent(pathname)}${pathname.endsWith('/') ? 'index.html' : ''}`);
    if (!path.startsWith(directory + sep)) {
      response.writeHead(404).end();
      return;
    }
    const file = await stat(path);
    if (!file.isFile()) {
      response.writeHead(404).end();
      return;
    }

    const headers = {
      'Content-Type': types[extname(path)] ?? 'application/octet-stream',
      'Content-Length': file.size,
      'Accept-Ranges': 'bytes',
    };
    const range = request.headers.range?.match(/^bytes=(\d+)-(\d*)$/);
    if (range) {
      const start = Number(range[1]);
      const end = range[2] ? Math.min(Number(range[2]), file.size - 1) : file.size - 1;
      if (start > end) {
        response.writeHead(416, { 'Content-Range': `bytes */${file.size}` }).end();
        return;
      }
      response.writeHead(206, { ...headers, 'Content-Length': end - start + 1, 'Content-Range': `bytes ${start}-${end}/${file.size}` });
      if (request.method === 'HEAD') response.end();
      else createReadStream(path, { start, end }).pipe(response);
      return;
    }
    response.writeHead(200, headers);
    if (request.method === 'HEAD') response.end();
    else createReadStream(path).pipe(response);
  } catch {
    response.writeHead(404).end();
  }
}).listen(port, host, () => {
  console.log(`Portfolio preview on http://${host}:${port}`);
});
