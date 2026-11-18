import { randomUUID } from 'node:crypto';
import type { AdminDatabase, ManagedContent, OperationOptions, PublicationEvent } from './types';

export function formatDamascusDate(value = new Date()): string {
  return new Intl.DateTimeFormat('ar-SY', {
    timeZone: 'Asia/Damascus', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(value);
}

export function formatOperationBody(
  options: OperationOptions,
  values: Record<string, string>,
  createdAt = new Date(),
): string {
  const lines = [options.title, `الوقت والتاريخ: ${formatDamascusDate(createdAt)}`];
  for (const field of options.fields) {
    const value = values[field.id]?.trim();
    if (value) lines.push(`${field.label}: ${value}`);
  }
  if (options.footer.trim()) lines.push('', options.footer.trim());
  return lines.join('\n');
}

export function enqueuePublication(
  db: AdminDatabase,
  item: ManagedContent,
  type: PublicationEvent['type'],
): void {
  if (item.status !== 'published' || !['central-operations', 'intelligence-reports'].includes(item.category)) return;
  const publishedAt = item.publishedAt || new Date().toISOString();
  db.publicationEvents.push({
    id: randomUUID(), type, contentId: item.id,
    category: item.category as PublicationEvent['category'],
    occurredAt: new Date().toISOString(),
    payload: {
      version: 1, title: item.title, body: item.body, priority: item.priority,
      publishedAt, structuredData: item.structuredData,
    },
    // Connectors append their own delivery record. Keeping the canonical event
    // channel-neutral makes Telegram, WhatsApp and webhooks interchangeable later.
    deliveries: [],
  });
  db.publicationEvents = db.publicationEvents.slice(-5_000);
}
