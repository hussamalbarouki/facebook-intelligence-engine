import { NextRequest, NextResponse } from 'next/server';
import { clearSessionCookie, requireAdmin } from '@/lib/admin/security';

export async function POST(request: NextRequest) {
  const auth = await requireAdmin(request);
  if (auth instanceof NextResponse) return auth;
  const response = NextResponse.json({ ok: true });
  clearSessionCookie(response);
  return response;
}

