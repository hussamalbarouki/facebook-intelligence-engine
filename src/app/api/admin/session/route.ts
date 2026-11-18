import { NextRequest, NextResponse } from 'next/server';
import { readDatabase } from '@/lib/admin/storage';
import { requireAdmin } from '@/lib/admin/security';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const auth = await requireAdmin(request);
  if (auth instanceof NextResponse) return auth;
  const db = await readDatabase();
  const role = db.roles.find((item) => item.id === auth.user.roleId);
  return NextResponse.json({
    user: {
      id: auth.user.id,
      username: auth.user.username,
      displayName: auth.user.displayName,
      roleId: auth.user.roleId,
      roleName: role?.name,
      mustChangePassword: auth.user.mustChangePassword,
      totpEnabled: auth.user.totpEnabled,
    },
    permissions: auth.permissions,
    csrf: auth.csrf,
  });
}

