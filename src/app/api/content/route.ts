import { NextRequest, NextResponse } from 'next/server';
import { readDatabase } from '@/lib/admin/storage';
import { CONTENT_CATEGORIES, type ContentCategory } from '@/lib/admin/types';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const category = request.nextUrl.searchParams.get('category') as ContentCategory | null;
  if (!category || !CONTENT_CATEGORIES.includes(category)) {
    return NextResponse.json({ error: 'تصنيف غير صالح' }, { status: 400 });
  }
  const db = await readDatabase();
  const items = db.content
    .filter((item) => item.category === category && item.status === 'published')
    .sort((a, b) => Number(b.pinned) - Number(a.pinned) || (b.publishedAt || '').localeCompare(a.publishedAt || ''))
    .slice(0, 100)
    .map((item) => ({
      ...item,
      createdBy: undefined,
    }));
  return NextResponse.json({ items, updatedAt: new Date().toISOString() });
}

