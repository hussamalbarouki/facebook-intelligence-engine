import { NextRequest, NextResponse } from 'next/server';
import { addAudit, updateDatabase } from '@/lib/admin/storage';
import { hashPassword, requireAdmin, verifyPassword, verifyTotp } from '@/lib/admin/security';

export async function POST(request: NextRequest) {
  const auth = await requireAdmin(request);
  if (auth instanceof NextResponse) return auth;
  const body = await request.json().catch(() => ({}));
  const currentPassword = typeof body.currentPassword === 'string' ? body.currentPassword : '';
  const newPassword = typeof body.newPassword === 'string' ? body.newPassword : '';
  const totp = typeof body.totp === 'string' ? body.totp : '';
  if (newPassword.length < 12 || !/[A-Z]/.test(newPassword) || !/[a-z]/.test(newPassword) || !/\d/.test(newPassword) || !/[^A-Za-z0-9]/.test(newPassword)) {
    return NextResponse.json({ error: 'كلمة السر يجب أن تكون 12 محرفاً وتضم حرفاً كبيراً وصغيراً ورقماً ورمزاً' }, { status: 400 });
  }
  if (!(await verifyPassword(currentPassword, auth.user.passwordSalt, auth.user.passwordHash))) {
    return NextResponse.json({ error: 'كلمة السر الحالية غير صحيحة' }, { status: 400 });
  }
  if (auth.user.totpEnabled && (!auth.user.totpSecret || !verifyTotp(auth.user.totpSecret, totp))) {
    return NextResponse.json({ error: 'رمز المصادقة غير صحيح' }, { status: 400 });
  }
  const password = await hashPassword(newPassword);
  await updateDatabase((db) => {
    const user = db.users.find((item) => item.id === auth.user.id)!;
    user.passwordSalt = password.salt;
    user.passwordHash = password.hash;
    user.mustChangePassword = false;
    user.updatedAt = new Date().toISOString();
    addAudit(db, { userId: user.id, username: user.username, action: 'security.password_changed' });
  });
  return NextResponse.json({ ok: true });
}

