import { NextRequest, NextResponse } from 'next/server';
import { addAudit, readDatabase, updateDatabase } from '@/lib/admin/storage';
import { hashPassword, newId, requireAdmin } from '@/lib/admin/security';

export const dynamic = 'force-dynamic';
const publicUser = (user: Awaited<ReturnType<typeof readDatabase>>['users'][number]) => ({ id: user.id, username: user.username, displayName: user.displayName, roleId: user.roleId, active: user.active, mustChangePassword: user.mustChangePassword, totpEnabled: user.totpEnabled, lastLoginAt: user.lastLoginAt, createdAt: user.createdAt });

export async function GET(request: NextRequest) {
  const auth = await requireAdmin(request, 'users.manage');
  if (auth instanceof NextResponse) return auth;
  return NextResponse.json({ users: (await readDatabase()).users.map(publicUser) });
}

export async function POST(request: NextRequest) {
  const auth = await requireAdmin(request, 'users.manage');
  if (auth instanceof NextResponse) return auth;
  const body = await request.json().catch(() => ({}));
  const username = typeof body.username === 'string' ? body.username.trim().slice(0, 80) : '';
  const displayName = typeof body.displayName === 'string' ? body.displayName.trim().slice(0, 120) : '';
  const password = typeof body.password === 'string' ? body.password : '';
  const strong = password.length >= 12 && /[A-Z]/.test(password) && /[a-z]/.test(password) && /\d/.test(password) && /[^A-Za-z0-9]/.test(password);
  if (!/^[A-Za-z0-9._-]{3,80}$/.test(username) || !strong) return NextResponse.json({ error: 'اسم المستخدم غير صالح أو كلمة السر لا تحقق شروط الأمان' }, { status: 400 });
  const db = await readDatabase();
  if (!db.roles.some((role) => role.id === body.roleId)) return NextResponse.json({ error: 'الدور غير صالح' }, { status: 400 });
  if (db.users.some((user) => user.username.toLowerCase() === username.toLowerCase())) return NextResponse.json({ error: 'اسم المستخدم مستخدم' }, { status: 409 });
  const credentials = await hashPassword(password);
  const now = new Date().toISOString();
  const user = { id: newId(), username, displayName: displayName || username, passwordSalt: credentials.salt, passwordHash: credentials.hash, roleId: body.roleId, active: true, mustChangePassword: true, totpEnabled: false, failedAttempts: 0, createdAt: now, updatedAt: now };
  await updateDatabase((current) => { current.users.push(user); addAudit(current, { userId: auth.user.id, username: auth.user.username, action: 'user.created', target: user.id, detail: user.roleId }); });
  return NextResponse.json({ user: publicUser(user) }, { status: 201 });
}
