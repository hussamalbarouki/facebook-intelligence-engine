import { NextRequest, NextResponse } from 'next/server';
import { addAudit, readDatabase, updateDatabase } from '@/lib/admin/storage';
import { clientIp, newId, requireAdmin } from '@/lib/admin/security';
import { CATEGORY_PERMISSION, CONTENT_CATEGORIES, type ContentCategory, type ManagedContent } from '@/lib/admin/types';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const auth = await requireAdmin(request, 'content.read');
  if (auth instanceof NextResponse) return auth;
  const category = request.nextUrl.searchParams.get('category');
  const db = await readDatabase();
  const items = db.content
    .filter((item) => !category || item.category === category)
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  return NextResponse.json({ items });
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const category = body.category as ContentCategory;
  if (!CONTENT_CATEGORIES.includes(category)) return NextResponse.json({ error: 'التصنيف غير صالح' }, { status: 400 });
  if (category === 'central-operations' || category === 'intelligence-reports') {
    return NextResponse.json({ error: 'استخدم الواجهة المتخصصة لهذا النوع من البلاغات' }, { status: 400 });
  }
  const auth = await requireAdmin(request, CATEGORY_PERMISSION[category]);
  if (auth instanceof NextResponse) return auth;
  const title = typeof body.title === 'string' ? body.title.trim().slice(0, 240) : '';
  const contentBody = typeof body.body === 'string' ? body.body.trim().slice(0, 20_000) : '';
  if (!title || !contentBody) return NextResponse.json({ error: 'العنوان والنص مطلوبان' }, { status: 400 });
  const now = new Date().toISOString();
  const item: ManagedContent = {
    id: newId(), category, title, body: contentBody,
    status: ['draft', 'published', 'archived'].includes(body.status) ? body.status : 'draft',
    priority: ['normal', 'important', 'urgent', 'critical'].includes(body.priority) ? body.priority : 'normal',
    pinned: body.pinned === true,
    confirmed: false,
    sourceType: 'manual', sourceName: typeof body.sourceName === 'string' ? body.sourceName.slice(0, 120) : undefined,
    operationType: typeof body.operationType === 'string' ? body.operationType : undefined,
    operationArea: typeof body.operationArea === 'string' ? body.operationArea : undefined,
    operationSeverity: typeof body.operationSeverity === 'string' ? body.operationSeverity : undefined,
    structuredData: body.structuredData && typeof body.structuredData === 'object' ? body.structuredData : undefined,
    createdBy: auth.user.id, createdAt: now, updatedAt: now,
    publishedAt: body.status === 'published' ? now : undefined,
  };
  await updateDatabase((db) => {
    db.content.push(item);
    addAudit(db, { userId: auth.user.id, username: auth.user.username, action: 'content.created', target: item.id, detail: category, ip: clientIp(request) });
  });
  return NextResponse.json({ item }, { status: 201 });
}
