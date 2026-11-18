import { NextRequest, NextResponse } from 'next/server';
import { addAudit, readDatabase, updateDatabase } from '@/lib/admin/storage';
import { clientIp, requireAdmin } from '@/lib/admin/security';
import { validateSourceUrl } from '@/lib/admin/content';

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = await requireAdmin(request, 'sources.manage');
  if (auth instanceof NextResponse) return auth;
  const { id } = await params;
  const body = await request.json().catch(() => ({}));
  if (typeof body.url === 'string') {
    const existing = (await readDatabase()).sources.find((entry) => entry.id === id);
    if (!existing) return NextResponse.json({ error: 'المصدر غير موجود' }, { status: 404 });
    try { await validateSourceUrl(existing.type, body.url); } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : 'الرابط غير صالح' }, { status: 400 }); }
  }
  const source = await updateDatabase((db) => {
    const item = db.sources.find((entry) => entry.id === id);
    if (!item) return null;
    if (typeof body.name === 'string' && body.name.trim()) item.name = body.name.trim().slice(0, 120);
    if (typeof body.enabled === 'boolean') item.enabled = body.enabled;
    if (typeof body.autoPublish === 'boolean') item.autoPublish = body.autoPublish;
    if (typeof body.autoTranslate === 'boolean') item.autoTranslate = body.autoTranslate;
    if (Number.isFinite(Number(body.maxItems))) item.maxItems = item.type === 'facebook' ? Math.min(3, Math.max(2, Number(body.maxItems))) : Math.min(30, Math.max(1, Number(body.maxItems)));
    if (typeof body.url === 'string') item.url = body.url.slice(0, 1000);
    item.updatedAt = new Date().toISOString();
    addAudit(db, { userId: auth.user.id, username: auth.user.username, action: 'source.updated', target: id, ip: clientIp(request) });
    return item;
  });
  return source ? NextResponse.json({ source }) : NextResponse.json({ error: 'المصدر غير موجود' }, { status: 404 });
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = await requireAdmin(request, 'sources.manage');
  if (auth instanceof NextResponse) return auth;
  const { id } = await params;
  const found = await updateDatabase((db) => {
    if (!db.sources.some((entry) => entry.id === id)) return false;
    db.sources = db.sources.filter((entry) => entry.id !== id);
    addAudit(db, { userId: auth.user.id, username: auth.user.username, action: 'source.deleted', target: id, ip: clientIp(request) });
    return true;
  });
  return found ? NextResponse.json({ ok: true }) : NextResponse.json({ error: 'المصدر غير موجود' }, { status: 404 });
}
