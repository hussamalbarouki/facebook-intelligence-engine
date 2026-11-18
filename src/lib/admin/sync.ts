import { createHash } from 'node:crypto';
import { fetchSource } from './content';
import { fetchFacebookPosts } from './facebook';
import { addAudit, readDatabase, updateDatabase } from './storage';
import { translateToArabic } from './translation';
import type { ContentSource, ManagedContent, TranslationCacheEntry } from './types';

interface SyncContext {
  sourceId?: string;
  onlyDue?: boolean;
  userId?: string;
  username?: string;
  ip?: string;
}

export interface SourceSyncResult { id: string; imported: number; translatedCharacters?: number; error?: string }

function fingerprint(item: Pick<ManagedContent, 'title' | 'body'>): string {
  const normalized = `${item.title}\n${item.body}`.normalize('NFKC').toLowerCase().replace(/\s+/g, ' ').trim();
  return createHash('sha256').update(normalized).digest('hex');
}

function freshItems(items: ManagedContent[], current: ManagedContent[]): ManagedContent[] {
  const external = new Set(current.filter((item) => item.externalId).map((item) => `${item.sourceType}:${item.externalId}`));
  const urls = new Set(current.map((item) => item.sourceUrl).filter(Boolean));
  const fingerprints = new Set(current.map(fingerprint));
  const accepted: ManagedContent[] = [];
  for (const item of items) {
    const key = item.externalId ? `${item.sourceType}:${item.externalId}` : '';
    const hash = fingerprint(item);
    if ((key && external.has(key)) || (item.sourceUrl && urls.has(item.sourceUrl)) || fingerprints.has(hash)) continue;
    if (key) external.add(key);
    if (item.sourceUrl) urls.add(item.sourceUrl);
    fingerprints.add(hash);
    accepted.push(item);
  }
  return accepted;
}

async function prepareTranslations(items: ManagedContent[], source: ContentSource) {
  if (!source.autoTranslate || !items.length) return { items, additions: [] as TranslationCacheEntry[], billedCharacters: 0 };
  const db = await readDatabase();
  const texts = items.flatMap((item) => [item.title, item.body]);
  const translated = await translateToArabic(texts, db.translationCache);
  for (const item of items) {
    const originalTitle = item.title;
    const originalBody = item.body;
    item.title = translated.values.get(originalTitle) || originalTitle;
    item.body = translated.values.get(originalBody) || originalBody;
    if (item.title !== originalTitle || item.body !== originalBody) {
      item.structuredData = { ...(item.structuredData || {}), originalTitle, originalBody, translatedBy: 'Microsoft Translator' };
    }
  }
  return { items, additions: translated.additions, billedCharacters: translated.billedCharacters };
}

async function storeResult(source: ContentSource, candidates: ManagedContent[], context: SyncContext): Promise<SourceSyncResult> {
  const snapshot = await readDatabase();
  const unique = freshItems(candidates, snapshot.content);
  const translated = await prepareTranslations(unique, source);
  const imported = await updateDatabase((db) => {
    const finalItems = freshItems(translated.items, db.content);
    db.content.push(...finalItems);
    const knownCache = new Set(db.translationCache.map((entry) => entry.hash));
    db.translationCache.push(...translated.additions.filter((entry) => !knownCache.has(entry.hash)));
    db.translationCache = db.translationCache.slice(-10_000);
    const stored = db.sources.find((item) => item.id === source.id);
    if (stored) { stored.lastAttemptAt = new Date().toISOString(); stored.lastSyncedAt = stored.lastAttemptAt; stored.lastError = undefined; }
    addAudit(db, {
      userId: context.userId, username: context.username, action: 'source.synced', target: source.id,
      detail: `imported=${finalItems.length}; translatedCharacters=${translated.billedCharacters}`,
      ip: context.ip,
    });
    return finalItems.length;
  });
  return { id: source.id, imported, translatedCharacters: translated.billedCharacters };
}

async function recordError(source: ContentSource, error: unknown): Promise<SourceSyncResult> {
  const message = error instanceof Error ? error.message.slice(0, 300) : 'فشلت المزامنة';
  await updateDatabase((db) => {
    const stored = db.sources.find((item) => item.id === source.id);
    if (stored) { stored.lastAttemptAt = new Date().toISOString(); stored.lastError = message; }
  });
  return { id: source.id, imported: 0, error: message };
}

function isDue(source: ContentSource): boolean {
  const lastRun = source.lastAttemptAt || source.lastSyncedAt;
  if (!lastRun) return true;
  return Date.now() - new Date(lastRun).getTime() >= 60 * 60_000;
}

export async function syncSources(context: SyncContext = {}): Promise<{ imported: number; results: SourceSyncResult[] }> {
  const db = await readDatabase();
  const sources = db.sources.filter((source) => source.enabled && (!context.sourceId || source.id === context.sourceId) && (!context.onlyDue || isDue(source)));
  const regular = sources.filter((source) => source.type !== 'facebook');
  const facebook = sources.filter((source) => source.type === 'facebook');
  const results: SourceSyncResult[] = [];

  for (let index = 0; index < regular.length; index += 3) {
    const chunk = regular.slice(index, index + 3);
    results.push(...await Promise.all(chunk.map(async (source) => {
      try { return await storeResult(source, await fetchSource(source, context.userId || 'system-sync'), context); }
      catch (error) { return recordError(source, error); }
    })));
  }

  if (facebook.length) {
    try {
      const posts = await fetchFacebookPosts(facebook, context.userId || 'system-sync');
      for (const source of facebook) results.push(await storeResult(source, posts.get(source.id) || [], context));
    } catch (error) {
      for (const source of facebook) results.push(await recordError(source, error));
    }
  }
  return { imported: results.reduce((sum, item) => sum + item.imported, 0), results };
}
