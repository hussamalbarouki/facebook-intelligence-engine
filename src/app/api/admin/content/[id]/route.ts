import { NextRequest, NextResponse } from 'next/server';
import { addAudit, readDatabase, updateDatabase } from '@/lib/admin/storage';
import { clientIp, requireAdmin } from '@/lib/admin/security';
import { CATEGORY_PERMISSION } from '@/lib/admin/types';
import { enqueuePublication } from '@/lib/admin/publication';

async function getAuthorized(request: NextRequest, id: string) {
  const db = await readDatabase();
  const item = db.content.find((entry) => entry.id === id);
  if (!item) return { response: NextResponse.json({ error: 'المحتوى غير موجود' }, { status: 404 }) };
  const auth = await requireAdmin(request, CATEGORY_PERMISSION[item.category]);
  return auth instanceof NextResponse ? { response: auth } : { auth, item };
}

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const access = await getAuthorized(request, id);
  if ('response' in access) return access.response;
  const body = await request.json().catch(() => ({}));
  const updated = await updateDatabase((db) => {
    const item = db.content.find((entry) => entry.id === id)!;
    const wasPublished = item.status === 'published';
    if (typeof body.title === 'string' && body.title.trim()) item.title = body.title.trim().slice(0, 240);
    if (typeof body.body === 'string' && body.body.trim()) item.body = body.body.trim().slice(0, 20_000);
    if (['normal', 'important', 'urgent', 'critical'].includes(body.priority)) item.priority = body.priority;
    if (typeof body.pinned === 'boolean') item.pinned = body.pinned;
    if (item.category === 'intelligence-reports' && typeof body.confirmed === 'boolean') item.confirmed = body.confirmed;
    if (typeof body.operationType === 'string') item.operationType = body.operationType;
    if (typeof body.operationArea === 'string') item.operationArea = body.operationArea;
    if (typeof body.operationSeverity === 'string') item.operationSeverity = body.operationSeverity;
    if (body.structuredData && typeof body.structuredData === 'object') item.structuredData = body.structuredData;
    if (['draft', 'published', 'archived'].includes(body.status)) {
      if (item.category === 'intelligence-reports' && body.status === 'published' && !item.confirmed) throw new Error('CONFIRM_REQUIRED');
      item.status = body.status;
      if (body.status === 'published' && !item.publishedAt) item.publishedAt = new Date().toISOString();
    }
    item.updatedAt = new Date().toISOString();
    if (item.status === 'published' && (item.category === 'central-operations' || item.category === 'intelligence-reports')) {
      enqueuePublication(db, item, wasPublished ? 'content.updated' : 'content.published');
    }
    addAudit(db, { userId: access.auth.user.id, username: access.auth.user.username, action: 'content.updated', target: id, ip: clientIp(request) });
    return { ...item };
  }).catch((error) => error instanceof Error && error.message === 'CONFIRM_REQUIRED' ? null : Promise.reject(error));
  if (!updated) return NextResponse.json({ error: 'يجب تأكيد البلاغ المعلوماتي قبل النشر' }, { status: 400 });
  return NextResponse.json({ item: updated });
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const access = await getAuthorized(request, id);
  if ('response' in access) return access.response;
  await updateDatabase((db) => {
    db.content = db.content.filter((entry) => entry.id !== id);
    addAudit(db, { userId: access.auth.user.id, username: access.auth.user.username, action: 'content.deleted', target: id, ip: clientIp(request) });
  });
  return NextResponse.json({ ok: true });
}
