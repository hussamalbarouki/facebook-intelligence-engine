import { NextRequest, NextResponse } from 'next/server';
import { addAudit, readDatabase, updateDatabase } from '@/lib/admin/storage';
import { enqueuePublication, formatOperationBody } from '@/lib/admin/publication';
import { clientIp, newId, requireAdmin } from '@/lib/admin/security';
import type { ContentPriority, ManagedContent } from '@/lib/admin/types';

export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  const auth = await requireAdmin(request, 'content.operations.manage');
  if (auth instanceof NextResponse) return auth;
  const body = await request.json().catch(() => ({}));
  const db = await readDatabase();
  const rawValues = body.values && typeof body.values === 'object' ? body.values as Record<string, unknown> : {};
  const values: Record<string, string> = {};
  for (const field of db.operationOptions.fields) {
    const value = typeof rawValues[field.id] === 'string' ? String(rawValues[field.id]).trim() : '';
    if (field.required && !value) return NextResponse.json({ error: `اختر ${field.label}` }, { status: 400 });
    if (value && !field.choices.includes(value)) return NextResponse.json({ error: `خيار غير صالح في ${field.label}` }, { status: 400 });
    if (value) values[field.id] = value;
  }
  const now = new Date();
  const status = body.status === 'draft' ? 'draft' : 'published';
  const priorities: ContentPriority[] = ['normal', 'important', 'urgent', 'critical'];
  const priority: ContentPriority = priorities.includes(body.priority) ? body.priority : 'normal';
  const item: ManagedContent = {
    id: newId(), category: 'central-operations', title: db.operationOptions.title,
    body: formatOperationBody(db.operationOptions, values, now), status, priority,
    pinned: body.pinned === true, confirmed: true, sourceType: 'manual',
    sourceName: 'لوحة العمليات المركزية',
    operationType: values.type, operationArea: values.area, operationSeverity: values.severity,
    structuredData: values, createdBy: auth.user.id, createdAt: now.toISOString(), updatedAt: now.toISOString(),
    publishedAt: status === 'published' ? now.toISOString() : undefined,
  };
  await updateDatabase((current) => {
    current.content.push(item);
    if (status === 'published') enqueuePublication(current, item, 'content.published');
    addAudit(current, { userId: auth.user.id, username: auth.user.username, action: 'operations.report_created', target: item.id, detail: status, ip: clientIp(request) });
  });
  return NextResponse.json({ item }, { status: 201 });
}
