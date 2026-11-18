import { readDatabase, updateDatabase } from './storage';
import { translateToArabic } from './translation';
import type { TranslationCacheEntry } from './types';

// Serialize live-feed translation work inside the server process. Several dashboard
// panels refresh together, and without this queue they could translate the same new
// headline concurrently before either request has persisted it in the shared cache.
let liveTranslationQueue: Promise<unknown> = Promise.resolve();

export function isRecentLiveDate(value: string | undefined, maxAgeHours = 24): boolean {
  if (!value) return false;
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return false;
  const age = Date.now() - timestamp;
  // Permit small future offsets caused by publisher timezone/clock mistakes.
  return age >= -6 * 60 * 60_000 && age <= maxAgeHours * 60 * 60_000;
}

export async function translateLiveTextsToArabic(texts: string[]): Promise<Map<string, string>> {
  const originals = new Map(texts.map((text) => [text, text.trim()]));
  const fallback = new Map(texts.map((text) => [text, text]));

  const operation = liveTranslationQueue.then(async () => {
    const unique = [...new Set([...originals.values()].filter(Boolean))];
    if (!unique.length) return fallback;

    const snapshot = await readDatabase();
    const workingCache: TranslationCacheEntry[] = [...snapshot.translationCache];
    const additions: TranslationCacheEntry[] = [];
    const translatedValues = new Map<string, string>();

    // Microsoft accepts at most 100 text objects in one request. Chunking also
    // ensures every displayed item is translated while retaining one cache entry
    // per exact source text.
    for (let index = 0; index < unique.length; index += 100) {
      const result = await translateToArabic(unique.slice(index, index + 100), workingCache);
      result.values.forEach((value, key) => translatedValues.set(key, value));
      workingCache.push(...result.additions);
      additions.push(...result.additions);
    }

    if (additions.length) {
      await updateDatabase((db) => {
        const known = new Set(db.translationCache.map((entry) => entry.hash));
        db.translationCache.push(...additions.filter((entry) => !known.has(entry.hash)));
        db.translationCache = db.translationCache.slice(-10_000);
      });
    }

    return new Map([...originals].map(([raw, trimmed]) => [
      raw,
      translatedValues.get(trimmed) || raw,
    ]));
  });

  liveTranslationQueue = operation.catch(() => undefined);
  try {
    return await operation;
  } catch (error) {
    console.error('Live-feed Arabic translation failed:', error instanceof Error ? error.message : 'unknown error');
    return fallback;
  }
}
