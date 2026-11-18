import { randomUUID } from 'node:crypto';
import type { ContentSource, ManagedContent } from './types';
import { cleanText } from './content';

const ACTOR_ID = 'socialscrapers~facebook-profile-posts-scraper';

interface FacebookRow {
  text?: string | null;
  createdAt?: string | null;
  url?: string | null;
  postId?: string | number | null;
  authorName?: string | null;
  authorUrl?: string | null;
  inputUrl?: string | null;
  linkTitle?: string | null;
  reactionsCount?: number | null;
  commentsCount?: number | null;
  sharesCount?: number | null;
  sharedPost?: { text?: string | null } | null;
  media?: Array<{ alt?: string | null }> | null;
}

export function apifyConfigured(): boolean {
  return Boolean(process.env.APIFY_API_TOKEN);
}

function normalizeFacebookUrl(raw: string): string {
  try {
    const url = new URL(raw);
    return `${url.hostname.replace(/^(www\.|m\.)/, '')}${url.pathname.replace(/\/$/, '').toLowerCase()}`;
  } catch { return raw.toLowerCase().replace(/\/$/, ''); }
}

function sourceForRow(row: FacebookRow, sources: ContentSource[]): ContentSource | undefined {
  const candidates = [row.inputUrl, row.authorUrl, row.url].filter((value): value is string => Boolean(value)).map(normalizeFacebookUrl);
  return sources.find((source) => {
    const normalized = normalizeFacebookUrl(source.url);
    return candidates.some((candidate) => candidate === normalized || candidate.startsWith(`${normalized}/`));
  });
}

export async function fetchFacebookPosts(sources: ContentSource[], createdBy: string): Promise<Map<string, ManagedContent[]>> {
  const output = new Map(sources.map((source) => [source.id, [] as ManagedContent[]]));
  if (!sources.length) return output;
  const token = process.env.APIFY_API_TOKEN;
  if (!token) throw new Error('مفتاح Apify غير مضبوط');
  const maxPosts = Math.min(3, Math.max(2, ...sources.map((source) => source.maxItems || 3)));
  const latestSync = sources.map((source) => source.lastSyncedAt).filter((value): value is string => Boolean(value)).sort()[0];
  const onlyPostsNewerThan = latestSync || '7 days';
  const endpoint = `https://api.apify.com/v2/acts/${ACTOR_ID}/run-sync-get-dataset-items?token=${encodeURIComponent(token)}&timeout=180`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 190_000);
  try {
    const response = await fetch(endpoint, {
      method: 'POST', signal: controller.signal, cache: 'no-store',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        startUrls: sources.map((source) => source.url),
        maxPostsPerProfile: maxPosts,
        onlyPostsNewerThan,
        includeComments: false,
      }),
    });
    if (!response.ok) throw new Error(`فشل Apify (${response.status})`);
    const rows = await response.json() as FacebookRow[];
    for (const row of rows) {
      const source = sourceForRow(row, sources);
      if (!source) continue;
      const body = cleanText(row.text || row.sharedPost?.text || row.media?.map((item) => item.alt).filter(Boolean).join(' ') || '', 20_000);
      if (!body) continue;
      const title = cleanText(row.linkTitle || `${row.authorName || source.name}: ${body.slice(0, 110)}`, 240);
      const now = new Date().toISOString();
      output.get(source.id)!.push({
        id: randomUUID(), category: 'facebook-news', title, body,
        status: source.autoPublish ? 'published' : 'draft', priority: 'normal', pinned: false, confirmed: false,
        sourceType: 'facebook', sourceName: row.authorName || source.name,
        sourceUrl: cleanText(row.url || source.url, 1000),
        externalId: String(row.postId || row.url || `${source.id}-${row.createdAt || body.slice(0, 80)}`),
        structuredData: {
          التفاعلات: String(row.reactionsCount || 0),
          التعليقات: String(row.commentsCount || 0),
          المشاركات: String(row.sharesCount || 0),
        },
        createdBy, createdAt: row.createdAt || now, updatedAt: now,
        publishedAt: source.autoPublish ? (row.createdAt || now) : undefined,
      });
    }
    return output;
  } finally {
    clearTimeout(timeout);
  }
}
