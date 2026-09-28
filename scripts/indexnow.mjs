// IndexNow: tell Bing (and every engine that shares the protocol) which URLs
// changed, the moment a deploy lands. ChatGPT search reads Bing's index, so
// this is the shortest path from "published" to "citable".
//
// Run after a deploy:   node scripts/indexnow.mjs
// Specific URLs only:   node scripts/indexnow.mjs https://example.com/a https://example.com/b
//
// The key is public by design (IndexNow verifies it by fetching
// https://<host>/<key>.txt), so it lives in this file and in that text file.
// No secrets are involved. Node 18 or newer, no dependencies.

import { readFile } from 'node:fs/promises';

const KEY = '23b0a3b250e5546c36f656b68e68e6f2';
const SITEMAP = 'site/www/sitemap.xml';

const argUrls = process.argv.slice(2);
let urls = argUrls;
if (urls.length === 0) {
  const xml = await readFile(SITEMAP, 'utf8');
  urls = [...xml.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/g)].map((m) => m[1]);
}
if (urls.length === 0) {
  console.error('No URLs to submit.');
  process.exit(1);
}

const host = new URL(urls[0]).host;
const body = { host, key: KEY, keyLocation: `https://${host}/${KEY}.txt`, urlList: urls };

const res = await fetch('https://api.indexnow.org/indexnow', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json; charset=utf-8' },
  body: JSON.stringify(body),
});

console.log(`IndexNow: ${res.status} ${res.statusText} for ${urls.length} URL(s) on ${host}`);
if (res.status !== 200 && res.status !== 202) {
  console.error(await res.text());
  process.exit(1);
}
