import { test } from 'node:test';
import assert from 'node:assert/strict';
import { enqueuePublication, formatOperationBody } from '../src/lib/admin/publication.ts';

const options = {
  title: 'بلاغ العمليات المركزية', footer: 'شعبة المعلومات',
  fields: [
    { id: 'side', label: 'الجهة', choices: ['الغرب', 'الشرق'], required: true },
    { id: 'state', label: 'الحالة', choices: ['طبيعي', 'طارئ'], required: true },
  ], types: [], areas: [], severities: [], customFields: [],
};

test('central report formatter preserves configured titles, choices and footer', () => {
  const body = formatOperationBody(options, { side: 'الغرب', state: 'طارئ' }, new Date('2026-11-18T12:00:00Z'));
  assert.match(body, /^بلاغ العمليات المركزية/);
  assert.match(body, /الجهة: الغرب/);
  assert.match(body, /الحالة: طارئ/);
  assert.match(body, /شعبة المعلومات$/);
});

test('publishing creates a channel-neutral versioned outbox event', () => {
  const db = { publicationEvents: [] };
  enqueuePublication(db, {
    id: 'report-1', category: 'central-operations', title: 'بلاغ', body: 'النص',
    status: 'published', priority: 'urgent', pinned: false, confirmed: true,
    sourceType: 'manual', createdBy: 'user-1', createdAt: '2026-11-18T12:00:00Z',
    updatedAt: '2026-11-18T12:00:00Z', publishedAt: '2026-11-18T12:00:00Z',
  }, 'content.published');
  assert.equal(db.publicationEvents.length, 1);
  assert.equal(db.publicationEvents[0].payload.version, 1);
  assert.equal(db.publicationEvents[0].deliveries.length, 0);
  assert.equal(db.publicationEvents[0].category, 'central-operations');
});
