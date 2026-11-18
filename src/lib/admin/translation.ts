import { createHash, randomUUID } from 'node:crypto';
import type { TranslationCacheEntry } from './types';

const DEFAULT_ENDPOINT = 'https://api.cognitive.microsofttranslator.com';

export function translationConfigured(): boolean {
  return Boolean(process.env.AZURE_TRANSLATOR_KEY);
}

export function textHash(text: string): string {
  return createHash('sha256').update(text.normalize('NFKC').trim()).digest('hex');
}

export function isArabicText(text: string): boolean {
  const letters = text.match(/[\p{L}]/gu) || [];
  if (!letters.length) return true;
  // Persian and Urdu share the Arabic Unicode script. Their distinctive letters
  // must still go through language detection instead of being mistaken for Arabic.
  if (/[پچژگکھیےٹڈڑں]/u.test(text)) return false;
  const arabic = text.match(/[\p{Script=Arabic}]/gu) || [];
  return arabic.length / letters.length >= 0.55;
}

function translatorUrl(): string {
  const base = (process.env.AZURE_TRANSLATOR_ENDPOINT || DEFAULT_ENDPOINT).replace(/\/$/, '');
  const path = base.endsWith('/translate') ? base : `${base}/translate`;
  return `${path}?api-version=3.0&to=ar`;
}

export async function translateToArabic(
  texts: string[],
  cache: TranslationCacheEntry[],
): Promise<{ values: Map<string, string>; additions: TranslationCacheEntry[]; billedCharacters: number }> {
  const values = new Map<string, string>();
  const additions: TranslationCacheEntry[] = [];
  const cached = new Map(cache.map((entry) => [entry.hash, entry]));
  const missing = new Map<string, string>();

  for (const raw of texts) {
    const text = raw.trim();
    if (!text || isArabicText(text)) { values.set(raw, raw); continue; }
    const hash = textHash(text);
    const hit = cached.get(hash);
    if (hit) values.set(raw, hit.translatedText);
    else missing.set(hash, text);
  }

  if (!missing.size) return { values, additions, billedCharacters: 0 };
  const key = process.env.AZURE_TRANSLATOR_KEY;
  if (!key) throw new Error('مفتاح Microsoft Translator غير مضبوط');
  const entries = [...missing.entries()].slice(0, 100);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20_000);
  try {
    const headers: Record<string, string> = {
      'content-type': 'application/json',
      'Ocp-Apim-Subscription-Key': key,
      'X-ClientTraceId': randomUUID(),
    };
    if (process.env.AZURE_TRANSLATOR_REGION) headers['Ocp-Apim-Subscription-Region'] = process.env.AZURE_TRANSLATOR_REGION;
    const response = await fetch(translatorUrl(), {
      method: 'POST', signal: controller.signal, headers,
      body: JSON.stringify(entries.map(([, text]) => ({ Text: text }))),
      cache: 'no-store',
    });
    if (!response.ok) throw new Error(`فشل Microsoft Translator (${response.status})`);
    const result = await response.json() as Array<{ detectedLanguage?: { language?: string }; translations?: Array<{ text?: string }> }>;
    entries.forEach(([hash, original], index) => {
      const translatedText = result[index]?.translations?.[0]?.text?.trim() || original;
      values.set(original, translatedText);
      additions.push({
        hash, translatedText,
        sourceLanguage: result[index]?.detectedLanguage?.language,
        characterCount: original.length,
        createdAt: new Date().toISOString(),
      });
    });
    return { values, additions, billedCharacters: entries.reduce((sum, [, text]) => sum + text.length, 0) };
  } finally {
    clearTimeout(timeout);
  }
}
