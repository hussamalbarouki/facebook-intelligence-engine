import { NextRequest, NextResponse } from 'next/server';
import { addAudit, updateDatabase } from '@/lib/admin/storage';
import { requireAdmin, verifyPassword, verifyTotp } from '@/lib/admin/security';

export async function POST(request: NextRequest) {
  const auth = await requireAdmin(request);
  if (auth instanceof NextResponse) return auth;
  const body = await request.json().catch(() => ({}));
  if (!(await verifyPassword(body.password || '', auth.user.passwordSalt, auth.user.passwordHash)) || !auth.user.totpSecret || !verifyTotp(auth.user.totpSecret, body.code || '')) {
    return NextResponse.json({ error: 'بيانات التحقق غير صحيحة' }, { status: 400 });
  }
  await updateDatabase((db) => { const user = db.users.find((item) => item.id === auth.user.id)!; user.totpEnabled = false; user.totpSecret = undefined; user.pendingTotpSecret = undefined; addAudit(db, { userId: user.id, username: user.username, action: 'security.totp_disabled' }); });
  return NextResponse.json({ ok: true });
}
