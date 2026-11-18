import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isArabicText, textHash, translateToArabic } from '../src/lib/admin/translation.ts';

test('Arabic text bypasses Microsoft Translator entirely', async () => {
  assert.equal(isArabicText('خبر عاجل من دمشق'), true);
  const result = await translateToArabic(['خبر عاجل من دمشق'], []);
  assert.equal(result.values.get('خبر عاجل من دمشق'), 'خبر عاجل من دمشق');
  assert.equal(result.billedCharacters, 0);
  assert.equal(result.additions.length, 0);
});

test('Persian and Urdu script is not mistaken for Arabic', () => {
  assert.equal(isArabicText('گزارش جدید درباره تهران'), false);
  assert.equal(isArabicText('یہ ایک نئی خبر ہے'), false);
});

test('a cached foreign translation uses zero new characters', async () => {
  const original = 'Breaking news from Damascus';
  const result = await translateToArabic([original], [{
    hash: textHash(original),
    sourceLanguage: 'en',
    translatedText: 'خبر عاجل من دمشق',
    characterCount: original.length,
    createdAt: new Date().toISOString(),
  }]);
  assert.equal(result.values.get(original), 'خبر عاجل من دمشق');
  assert.equal(result.billedCharacters, 0);
  assert.equal(result.additions.length, 0);
});
