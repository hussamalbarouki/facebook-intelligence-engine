import { NextRequest, NextResponse } from 'next/server';
import { addAudit, readDatabase, updateDatabase } from '@/lib/admin/storage';
import { clientIp, newId, requireAdmin } from '@/lib/admin/security';
import type { ContentSource } from '@/lib/admin/types';
import { validateSourceUrl } from '@/lib/admin/content';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const auth = await requireAdmin(request, 'sources.manage');
  if (auth instanceof NextResponse) return auth;
  return NextResponse.json({ sources: (await readDatabase()).sources });
}

export async function POST(request: NextRequest) {
  const auth = await requireAdmin(request, 'sources.manage');
  if (auth instanceof NextResponse) return auth;
  const body = await request.json().catch(() => ({}));
  const type = body.type === 'facebook' ? 'facebook' : body.type === 'telegram' ? 'telegram' : body.type === 'rss' ? 'rss' : null;
  const name = typeof body.name === 'string' ? body.name.trim().slice(0, 120) : '';
  const url = typeof body.url === 'string' ? body.url.trim().slice(0, 1000) : '';
  if (!type || !name) return NextResponse.json({ error: 'الاسم والنوع مطلوبان' }, { status: 400 });
  try { await validateSourceUrl(type, url); } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : 'الرابط غير صالح' }, { status: 400 }); }
  const now = new Date().toISOString();
  const requestedMax = Number(body.maxItems);
  const maxItems = type === 'facebook' ? Math.min(3, Math.max(2, requestedMax || 3)) : Math.min(30, Math.max(1, requestedMax || (type === 'telegram' ? 5 : 8)));
  const source: ContentSource = {
    id: newId(), name, type, url, enabled: body.enabled !== false,
    autoPublish: body.autoPublish === true, autoTranslate: body.autoTranslate === true,
    maxItems, createdAt: now, updatedAt: now,
  };
  await updateDatabase((db) => {
    db.sources.push(source);
    addAudit(db, { userId: auth.user.id, username: auth.user.username, action: 'source.created', target: source.id, detail: type, ip: clientIp(request) });
  });
  return NextResponse.json({ source }, { status: 201 });
}
