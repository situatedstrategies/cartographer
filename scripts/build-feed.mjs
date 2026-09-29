/*
  Builds the blog's RSS 2.0 feed (blog/feed.xml) and JSON Feed (blog/feed.json)
  from the posts' own pages: title, description, canonical URL and dates come
  from each post's <title>, meta description, <link rel="canonical"> and its
  BlogPosting JSON-LD. Run after adding a post; commit the two files with it.

    node scripts/build-feed.mjs
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
const blogDir = path.join(root, SITE.blogDir);
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const unesc = (s) => String(s).replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ');

function readPost(file) {
  const html = fs.readFileSync(file, 'utf8');
  const ld = [...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)]
    .map((m) => { try { return JSON.parse(m[1]); } catch { return null; } })
    .flatMap((d) => (d && d['@graph'] ? d['@graph'] : [d]))
    .find((d) => d && (d['@type'] === 'BlogPosting' || d['@type'] === 'Article'));
  if (!ld) return null;
  const title = unesc((html.match(/<title>([\s\S]*?)<\/title>/) || [, ld.headline || ''])[1].trim());
  const description = unesc((html.match(/<meta name="description" content="([^"]*)"/) || [, ld.description || ''])[1]);
  const canonical = (html.match(/<link rel="canonical" href="([^"]+)"/) || [, ld.url || ld.mainEntityOfPage || ''])[1];
  const date = ld.datePublished || '';
  if (!canonical || !date) return null;
  return { title: ld.headline || title, description, url: canonical, date, updated: ld.dateModified || date };
}

const posts = fs.existsSync(blogDir)
  ? fs.readdirSync(blogDir).filter((f) => f.endsWith('.html') && f !== 'index.html' && !f.startsWith('_'))
      .map((f) => readPost(path.join(blogDir, f))).filter(Boolean)
      .sort((a, b) => (a.date < b.date ? 1 : -1))
  : [];

const rfc822 = (iso) => new Date(iso + (iso.length === 10 ? 'T12:00:00Z' : '')).toUTCString();
const blogUrl = SITE.url.replace(/\/$/, '') + '/' + SITE.blogDir.replace(/^public\//, '') + '/';
const feedUrl = blogUrl + 'feed.xml';
const now = new Date().toUTCString();

const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>${esc(SITE.title)}</title>
    <link>${esc(blogUrl)}</link>
    <atom:link href="${esc(feedUrl)}" rel="self" type="application/rss+xml"/>
    <description>${esc(SITE.description)}</description>
    <language>en-us</language>
    <lastBuildDate>${now}</lastBuildDate>
${posts.map((p) => `    <item>
      <title>${esc(p.title)}</title>
      <link>${esc(p.url)}</link>
      <guid isPermaLink="true">${esc(p.url)}</guid>
      <pubDate>${rfc822(p.date)}</pubDate>
      <description>${esc(p.description)}</description>
    </item>`).join('\n')}
  </channel>
</rss>
`;
const jsonFeed = {
  version: 'https://jsonfeed.org/version/1.1',
  title: SITE.title,
  home_page_url: blogUrl,
  feed_url: blogUrl + 'feed.json',
  description: SITE.description,
  language: 'en-US',
  authors: [{ name: SITE.author, url: SITE.url }],
  items: posts.map((p) => ({ id: p.url, url: p.url, title: p.title, summary: p.description, date_published: p.date.length === 10 ? p.date + 'T12:00:00Z' : p.date, date_modified: p.updated.length === 10 ? p.updated + 'T12:00:00Z' : p.updated, authors: [{ name: SITE.author }] })),
};
fs.mkdirSync(blogDir, { recursive: true });
fs.writeFileSync(path.join(blogDir, 'feed.xml'), rss);
fs.writeFileSync(path.join(blogDir, 'feed.json'), JSON.stringify(jsonFeed, null, 2) + '\n');
console.log(`feed: ${posts.length} posts -> ${path.relative(process.cwd(), blogDir)}/feed.xml and feed.json`);
