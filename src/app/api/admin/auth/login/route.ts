import { NextRequest, NextResponse } from 'next/server';
import { addAudit, updateDatabase } from '@/lib/admin/storage';
import {
  clientIp,
  createSession,
  setSessionCookie,
  verifyPassword,
  verifyTotp,
} from '@/lib/admin/security';

export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const username = typeof body.username === 'string' ? body.username.trim() : '';
  const password = typeof body.password === 'string' ? body.password : '';
  const totp = typeof body.totp === 'string' ? body.totp.trim() : '';
  const ip = clientIp(request);

  if (!username || !password) return NextResponse.json({ error: 'أدخل اسم المستخدم وكلمة السر' }, { status: 400 });

  const result = await updateDatabase(async (db) => {
    const user = db.users.find((item) => item.username.toLowerCase() === username.toLowerCase());
    if (!user || !user.active) {
      addAudit(db, { action: 'auth.login_failed', detail: `username=${username}`, ip });
      return { ok: false as const, status: 401, error: 'بيانات الدخول غير صحيحة' };
    }
    if (user.lockedUntil && new Date(user.lockedUntil).getTime() > Date.now()) {
      addAudit(db, { userId: user.id, username: user.username, action: 'auth.locked_attempt', ip });
      return { ok: false as const, status: 429, error: 'الحساب مقفل مؤقتاً. حاول لاحقاً' };
    }
    const validPassword = await verifyPassword(password, user.passwordSalt, user.passwordHash);
    const validTotp = !user.totpEnabled || (!!user.totpSecret && verifyTotp(user.totpSecret, totp));
    if (!validPassword || !validTotp) {
      user.failedAttempts += 1;
      if (user.failedAttempts >= 5) {
        user.lockedUntil = new Date(Date.now() + 15 * 60_000).toISOString();
        user.failedAttempts = 0;
      }
      addAudit(db, {
        userId: user.id,
        username: user.username,
        action: 'auth.login_failed',
        detail: user.totpEnabled && !totp ? 'totp_required' : undefined,
        ip,
      });
      return {
        ok: false as const,
        status: 401,
        error: user.totpEnabled && !totp ? 'أدخل رمز المصادقة' : 'بيانات الدخول غير صحيحة',
        totpRequired: user.totpEnabled,
      };
    }
    user.failedAttempts = 0;
    user.lockedUntil = undefined;
    user.lastLoginAt = new Date().toISOString();
    user.updatedAt = user.lastLoginAt;
    addAudit(db, { userId: user.id, username: user.username, action: 'auth.login', ip });
    return { ok: true as const, user: { ...user } };
  });

  if (!result.ok) return NextResponse.json(result, { status: result.status });
  const session = await createSession(result.user);
  const response = NextResponse.json({
    ok: true,
    mustChangePassword: result.user.mustChangePassword,
    totpEnabled: result.user.totpEnabled,
  });
  setSessionCookie(response, session.token);
  return response;
}

