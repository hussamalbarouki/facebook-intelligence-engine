import { NextRequest, NextResponse } from 'next/server';
import { syncSources } from '@/lib/admin/sync';
import { clientIp, requireAdmin } from '@/lib/admin/security';

export async function POST(request: NextRequest) {
  const auth = await requireAdmin(request, 'sources.manage');
  if (auth instanceof NextResponse) return auth;
  const body = await request.json().catch(() => ({}));
  return NextResponse.json(await syncSources({
    sourceId: typeof body.sourceId === 'string' ? body.sourceId : undefined,
    userId: auth.user.id, username: auth.user.username, ip: clientIp(request),
  }));
}
