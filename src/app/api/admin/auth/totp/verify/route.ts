import { NextRequest, NextResponse } from 'next/server';
import { addAudit, updateDatabase } from '@/lib/admin/storage';
import { requireAdmin, verifyTotp } from '@/lib/admin/security';

export async function POST(request: NextRequest) {
  const auth = await requireAdmin(request);
  if (auth instanceof NextResponse) return auth;
  const body = await request.json().catch(() => ({}));
  const code = typeof body.code === 'string' ? body.code : '';
  const success = await updateDatabase((db) => {
    const user = db.users.find((item) => item.id === auth.user.id)!;
    if (!user.pendingTotpSecret || !verifyTotp(user.pendingTotpSecret, code)) return false;
    user.totpSecret = user.pendingTotpSecret;
    user.pendingTotpSecret = undefined;
    user.totpEnabled = true;
    user.updatedAt = new Date().toISOString();
    addAudit(db, { userId: user.id, username: user.username, action: 'security.totp_enabled' });
    return true;
  });
  return success ? NextResponse.json({ ok: true }) : NextResponse.json({ error: 'الرمز غير صحيح' }, { status: 400 });
}

