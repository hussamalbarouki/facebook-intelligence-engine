import { DOMParser } from '@xmldom/xmldom';
import { randomUUID } from 'node:crypto';
import { lookup } from 'node:dns/promises';
import { isIP } from 'node:net';
import type { ContentSource, ManagedContent } from './types';

export function cleanText(value: unknown, max = 10_000): string {
  if (typeof value !== 'string') return '';
  return value.replace(/\0/g, '').trim().slice(0, max);
}

function privateAddress(address: string): boolean {
  const normalized = address.toLowerCase();
  if (normalized === '::1' || normalized.startsWith('fe80:') || normalized.startsWith('fc') || normalized.startsWith('fd')) return true;
  if (!isIP(normalized)) return true;
  if (normalized.includes(':')) return false;
  const [a, b] = normalized.split('.').map(Number);
  return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || a >= 224;
}

export async function validateSourceUrl(type: ContentSource['type'], raw: string): Promise<URL> {
  const url = new URL(raw);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('الرابط غير مسموح');
  if (type === 'telegram' && !['t.me', 'telegram.me', 'www.t.me', 'www.telegram.me'].includes(url.hostname.toLowerCase())) throw new Error('يجب استخدام رابط قناة Telegram عامة');
  if (type === 'facebook' && !['facebook.com', 'www.facebook.com', 'm.facebook.com', 'fb.me', 'www.fb.me'].includes(url.hostname.toLowerCase())) throw new Error('يجب استخدام رابط صفحة Facebook عامة');
  const addresses = await lookup(url.hostname, { all: true, verbatim: true });
  if (!addresses.length || addresses.some(({ address }) => privateAddress(address))) throw new Error('عناوين الشبكة الداخلية غير مسموحة');
  return url;
}

async function safeFetch(source: ContentSource, signal: AbortSignal): Promise<Response> {
  let url = await validateSourceUrl(source.type, source.url);
  for (let redirects = 0; redirects < 4; redirects += 1) {
    const response = await fetch(url, { signal, cache: 'no-store', redirect: 'manual', headers: { 'User-Agent': 'EagleEye-Information/1.0', Accept: 'application/rss+xml, application/xml, text/html;q=0.9, */*;q=0.5' } });
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const location = response.headers.get('location');
      if (!location) throw new Error('تحويل المصدر غير صالح');
      url = await validateSourceUrl(source.type, new URL(location, url).toString());
      continue;
    }
    const declared = Number(response.headers.get('content-length') || 0);
    if (declared > 2_000_000) throw new Error('حجم المصدر يتجاوز الحد المسموح');
    return response;
  }
  throw new Error('عدد تحويلات المصدر كبير');
}

function stripHtml(value: string): string {
  return value
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, ' ')
    .trim();
}

function importedPost(
  source: ContentSource,
  title: string,
  body: string,
  link: string,
  externalId: string,
  createdBy: string,
): ManagedContent {
  const now = new Date().toISOString();
  return {
    id: randomUUID(),
    category: 'local-news',
    title: cleanText(title, 250) || cleanText(body, 120),
    body: cleanText(body),
    status: source.autoPublish ? 'published' : 'draft',
    priority: 'normal',
    pinned: false,
    confirmed: false,
    sourceType: source.type,
    sourceName: source.name,
    sourceUrl: cleanText(link, 1000),
    externalId,
    createdBy,
    createdAt: now,
    updatedAt: now,
    publishedAt: source.autoPublish ? now : undefined,
  };
}

export async function fetchSource(source: ContentSource, createdBy: string): Promise<ManagedContent[]> {
  if (source.type === 'facebook') throw new Error('مصادر Facebook تتم مزامنتها عبر Apify');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  try {
    const response = await safeFetch(source, controller.signal);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength > 2_000_000) throw new Error('حجم المصدر يتجاوز الحد المسموح');
    const text = new TextDecoder().decode(buffer);

    if (source.type === 'rss') {
      const document = new DOMParser().parseFromString(text, 'text/xml');
      const nodes = Array.from(document.getElementsByTagName('item')).slice(0, source.maxItems);
      return nodes.map((node, index) => {
        const get = (name: string) => node.getElementsByTagName(name)[0]?.textContent?.trim() || '';
        const link = get('link');
        return importedPost(
          source,
          stripHtml(get('title')),
          stripHtml(get('description') || get('content:encoded')),
          link,
          get('guid') || link || `${source.id}-${index}`,
          createdBy,
        );
      });
    }

    const messages = [...text.matchAll(/<div class="tgme_widget_message_text[^>]*>([\s\S]*?)<\/div>/gi)].slice(0, source.maxItems);
    return messages.map((match, index) => {
      const body = stripHtml(match[1]);
      const idMatch = match.input.slice(Math.max(0, (match.index || 0) - 1000), match.index).match(/data-post="([^"]+)"/);
      const postId = idMatch?.[1] || `${source.id}-${index}-${body.slice(0, 30)}`;
      const link = postId.includes('/') ? `https://t.me/${postId}` : source.url;
      return importedPost(source, body.slice(0, 120), body, link, postId, createdBy);
    });
  } finally {
    clearTimeout(timeout);
  }
}

