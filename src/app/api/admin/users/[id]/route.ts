import { NextRequest, NextResponse } from 'next/server';
import { addAudit, readDatabase, updateDatabase } from '@/lib/admin/storage';
import { hashPassword, requireAdmin } from '@/lib/admin/security';

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const auth = await requireAdmin(request, 'users.manage');
  if (auth instanceof NextResponse) return auth;
  const { id } = await params;
  const body = await request.json().catch(() => ({}));
  const db = await readDatabase();
  if (body.roleId && !db.roles.some((role) => role.id === body.roleId)) return NextResponse.json({ error: 'الدور غير صالح' }, { status: 400 });
  const password = typeof body.password === 'string' && body.password.length >= 12 ? await hashPassword(body.password) : null;
  const result = await updateDatabase((current) => {
    const user = current.users.find((item) => item.id === id);
    if (!user) return 'missing';
    if (body.active === false && user.roleId === 'super-admin' && current.users.filter((item) => item.active && item.roleId === 'super-admin').length === 1) return 'last-admin';
    if (typeof body.displayName === 'string' && body.displayName.trim()) user.displayName = body.displayName.trim().slice(0, 120);
    if (typeof body.roleId === 'string') user.roleId = body.roleId;
    if (typeof body.active === 'boolean') user.active = body.active;
    if (password) { user.passwordSalt = password.salt; user.passwordHash = password.hash; user.mustChangePassword = true; user.failedAttempts = 0; user.lockedUntil = undefined; }
    if (body.resetTotp === true) { user.totpEnabled = false; user.totpSecret = undefined; user.pendingTotpSecret = undefined; }
    user.updatedAt = new Date().toISOString();
    addAudit(current, { userId: auth.user.id, username: auth.user.username, action: 'user.updated', target: id });
    return 'ok';
  });
  if (result === 'missing') return NextResponse.json({ error: 'المستخدم غير موجود' }, { status: 404 });
  if (result === 'last-admin') return NextResponse.json({ error: 'لا يمكن تعطيل آخر مدير للنظام' }, { status: 400 });
  return NextResponse.json({ ok: true });
}
