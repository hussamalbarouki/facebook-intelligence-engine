import { NextRequest, NextResponse } from 'next/server';
import { addAudit, updateDatabase } from '@/lib/admin/storage';
import { enqueuePublication } from '@/lib/admin/publication';
import { clientIp, newId, requireAdmin } from '@/lib/admin/security';
import type { ContentPriority, ManagedContent } from '@/lib/admin/types';

export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  const auth = await requireAdmin(request, 'content.intelligence.manage');
  if (auth instanceof NextResponse) return auth;
  const body = await request.json().catch(() => ({}));
  const title = typeof body.title === 'string' ? body.title.trim().slice(0, 240) : '';
  const contentBody = typeof body.body === 'string' ? body.body.trim().slice(0, 20_000) : '';
  if (!title || !contentBody) return NextResponse.json({ error: 'العنوان ونص البلاغ مطلوبان' }, { status: 400 });
  const status = body.status === 'draft' ? 'draft' : 'published';
  if (status === 'published' && body.confirmed !== true) return NextResponse.json({ error: 'أكد صحة البلاغ قبل النشر' }, { status: 400 });
  const priorities: ContentPriority[] = ['normal', 'important', 'urgent', 'critical'];
  const priority: ContentPriority = priorities.includes(body.priority) ? body.priority : 'normal';
  const now = new Date().toISOString();
  const item: ManagedContent = {
    id: newId(), category: 'intelligence-reports', title, body: contentBody,
    status, priority, pinned: body.pinned === true, confirmed: body.confirmed === true,
    sourceType: 'manual', sourceName: 'واجهة البلاغات المعلوماتية',
    createdBy: auth.user.id, createdAt: now, updatedAt: now,
    publishedAt: status === 'published' ? now : undefined,
  };
  await updateDatabase((db) => {
    db.content.push(item);
    if (status === 'published') enqueuePublication(db, item, 'content.published');
    addAudit(db, { userId: auth.user.id, username: auth.user.username, action: 'intelligence.report_created', target: item.id, detail: status, ip: clientIp(request) });
  });
  return NextResponse.json({ item }, { status: 201 });
}
