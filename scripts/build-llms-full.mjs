/*
  Builds llms-full.txt: the readable text of every page in sitemap.xml, in
  one file, so an AI crawler can take the whole site in one request. Pages
  keep their title, URL and description, then the main content as plain text
  with headings and lists preserved. Run after any content change; commit the
  file with it.

    node scripts/build-llms-full.mjs
*/
import fs from 'node:fs';
import path from 'node:path';

const SITE = {
  "root": "site/www",
  "blogDir": "blog",
  "url": "https://codecartographer.dev",
  "title": "The Cartographer blog",
  "description": "Short, cited articles from Team Cartographer on working with coding agents, with sources.",
  "author": "Team Cartographer",
  "name": "Cartographer",
  "summary": "An open source tool that reads the session history a coding agent keeps and turns it into a map of how a project was built. By Situated Strategies LLC."
};
const root = path.resolve(process.cwd(), SITE.root);

const unesc = (s) => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ').replace(/&Prime;/g, '"').replace(/&ntilde;/g, 'n').replace(/&copy;/g, '(c)').replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)));

function textOf(html) {
  let h = html.replace(/<!--[\s\S]*?-->/g, '');
  for (const tag of ['script', 'style', 'noscript', 'svg', 'form', 'nav', 'header', 'footer', 'aside', 'template']) {
    h = h.replace(new RegExp(`<${tag}\\b[\\s\\S]*?<\\/${tag}>`, 'gi'), ' ');
  }
  const main = h.match(/<main\b[\s\S]*?<\/main>/i);
  if (main) h = main[0];
  else { const body = h.match(/<body\b[\s\S]*?<\/body>/i); if (body) h = body[0]; }
  h = h.replace(/<(h[1-6])\b[^>]*>/gi, (_, t) => '\n\n' + '#'.repeat(Number(t[1])) + ' ')
       .replace(/<\/h[1-6]>/gi, '\n')
       .replace(/<li\b[^>]*>/gi, '\n- ').replace(/<\/(p|div|section|article|li|ul|ol|tr|blockquote|figcaption|dd|dt)>/gi, '\n')
       .replace(/<br\s*\/?>/gi, '\n').replace(/<\/?(td|th)\b[^>]*>/gi, ' | ')
       .replace(/<[^>]+>/g, '');
  return unesc(h).split('\n').map((l) => l.replace(/[ \t]+/g, ' ').trim()).join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

const sitemap = fs.readFileSync(path.join(root, 'sitemap.xml'), 'utf8');
const urls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
const base = SITE.url.replace(/\/$/, '');
const parts = [];
for (const url of urls) {
  let rel = url.replace(base, '').replace(/^\//, '');
  const candidates = rel === '' ? ['index.html'] : [rel, rel + '.html', rel.replace(/\/$/, '') + '/index.html', rel.replace(/\/$/, '') + '.html'];
  const file = candidates.map((c) => path.join(root, c)).find((f) => fs.existsSync(f) && fs.statSync(f).isFile());
  if (!file) { console.warn('no file for', url); continue; }
  const html = fs.readFileSync(file, 'utf8');
  const title = unesc((html.match(/<title>([\s\S]*?)<\/title>/) || [, rel])[1].trim());
  const desc = unesc((html.match(/<meta name="description" content="([^"]*)"/) || [, ''])[1]);
  parts.push(`# ${title}\nURL: ${url}\n${desc ? 'Description: ' + desc + '\n' : ''}\n${textOf(html)}`);
}
const header = `# ${SITE.name}: full text\n\n> ${SITE.summary}\n> Every page below is also served at its URL. This file is the same content in one place, for assistants and crawlers. See also /llms.txt for the short index.\n> Generated ${new Date().toISOString().slice(0, 10)}.\n`;
const out = header + '\n\n---\n\n' + parts.join('\n\n---\n\n') + '\n';
fs.writeFileSync(path.join(root, 'llms-full.txt'), out);
console.log(`llms-full.txt: ${parts.length} pages, ${(out.length / 1024).toFixed(0)} KB`);
