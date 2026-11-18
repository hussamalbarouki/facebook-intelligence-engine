import { NextRequest, NextResponse } from 'next/server';
import { readDatabase } from '@/lib/admin/storage';
import { requireAdmin } from '@/lib/admin/security';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const auth = await requireAdmin(request, 'audit.read');
  if (auth instanceof NextResponse) return auth;
  const db = await readDatabase();
  return NextResponse.json({ entries: db.audit.slice(-500).reverse() });
}
