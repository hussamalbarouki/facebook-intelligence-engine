import { NextRequest, NextResponse } from 'next/server';
import QRCode from 'qrcode';
import { updateDatabase } from '@/lib/admin/storage';
import { generateTotpSecret, requireAdmin } from '@/lib/admin/security';

export async function POST(request: NextRequest) {
  const auth = await requireAdmin(request);
  if (auth instanceof NextResponse) return auth;
  const secret = generateTotpSecret();
  await updateDatabase((db) => {
    const user = db.users.find((item) => item.id === auth.user.id)!;
    user.pendingTotpSecret = secret;
    user.updatedAt = new Date().toISOString();
  });
  const label = encodeURIComponent(`عين النسر:${auth.user.username}`);
  const issuer = encodeURIComponent('منظومة عين النسر');
  const uri = `otpauth://totp/${label}?secret=${secret}&issuer=${issuer}&algorithm=SHA1&digits=6&period=30`;
  const qr = await QRCode.toDataURL(uri, { width: 260, margin: 1, errorCorrectionLevel: 'M' });
  return NextResponse.json({ secret, uri, qr });
}

