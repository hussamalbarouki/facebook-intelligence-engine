import {
  createHmac,
  randomBytes,
  randomUUID,
  scrypt as scryptCallback,
  timingSafeEqual,
} from 'node:crypto';
import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';
import { addAudit, readDatabase, updateDatabase } from './storage';
import type { AdminUser, Permission } from './types';

function scrypt(password: string, salt: Buffer): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    scryptCallback(password, salt, 64, {
      N: 16384,
      r: 8,
      p: 1,
      maxmem: 64 * 1024 * 1024,
    }, (error, key) => error ? reject(error) : resolve(key));
  });
}
export const SESSION_COOKIE = 'eagle_eye_session';
const SESSION_SECONDS = 8 * 60 * 60;

interface SessionPayload {
  userId: string;
  roleId: string;
  csrf: string;
  exp: number;
}

export async function hashPassword(password: string): Promise<{ salt: string; hash: string }> {
  const salt = randomBytes(16).toString('hex');
  const key = await scrypt(password, Buffer.from(salt, 'hex'));
  return { salt, hash: key.toString('hex') };
}

export async function verifyPassword(password: string, salt: string, expected: string): Promise<boolean> {
  const key = await scrypt(password, Buffer.from(salt, 'hex'));
  const target = Buffer.from(expected, 'hex');
  return key.length === target.length && timingSafeEqual(key, target);
}

function sign(value: string, secret: string): string {
  return createHmac('sha256', secret).update(value).digest('base64url');
}

export async function createSession(user: AdminUser): Promise<{ token: string; csrf: string }> {
  const db = await readDatabase();
  const payload: SessionPayload = {
    userId: user.id,
    roleId: user.roleId,
    csrf: randomBytes(24).toString('base64url'),
    exp: Math.floor(Date.now() / 1000) + SESSION_SECONDS,
  };
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url');
  return { token: `${body}.${sign(body, db.security.sessionSecret)}`, csrf: payload.csrf };
}

export async function readSession(request: NextRequest): Promise<SessionPayload | null> {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  const [body, signature] = token.split('.');
  if (!body || !signature) return null;
  const db = await readDatabase();
  const expected = sign(body, db.security.sessionSecret);
  const left = Buffer.from(signature);
  const right = Buffer.from(expected);
  if (left.length !== right.length || !timingSafeEqual(left, right)) return null;
  try {
    const payload = JSON.parse(Buffer.from(body, 'base64url').toString('utf8')) as SessionPayload;
    if (payload.exp < Math.floor(Date.now() / 1000)) return null;
    return payload;
  } catch {
    return null;
  }
}

export async function requireAdmin(
  request: NextRequest,
  permission?: Permission,
): Promise<{ user: AdminUser; permissions: Permission[]; csrf: string } | NextResponse> {
  const session = await readSession(request);
  if (!session) return NextResponse.json({ error: 'غير مصرح' }, { status: 401 });
  const db = await readDatabase();
  const user = db.users.find((item) => item.id === session.userId && item.active);
  const role = db.roles.find((item) => item.id === user?.roleId);
  if (!user || !role) return NextResponse.json({ error: 'الحساب غير متاح' }, { status: 401 });
  if (permission && !role.permissions.includes(permission)) {
    return NextResponse.json({ error: 'لا تملك الصلاحية المطلوبة' }, { status: 403 });
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method)) {
    const csrf = request.headers.get('x-csrf-token');
    if (!csrf || csrf !== session.csrf) {
      return NextResponse.json({ error: 'رمز الحماية غير صالح' }, { status: 403 });
    }
  }
  return { user, permissions: role.permissions, csrf: session.csrf };
}

export function setSessionCookie(response: NextResponse, token: string): void {
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict',
    path: '/',
    maxAge: SESSION_SECONDS,
  });
}

export function clearSessionCookie(response: NextResponse): void {
  response.cookies.set(SESSION_COOKIE, '', {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'strict',
    path: '/',
    maxAge: 0,
  });
}

const BASE32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

export function generateTotpSecret(): string {
  const bytes = randomBytes(20);
  let bits = '';
  for (const byte of bytes) bits += byte.toString(2).padStart(8, '0');
  let result = '';
  for (let i = 0; i < bits.length; i += 5) {
    result += BASE32[Number.parseInt(bits.slice(i, i + 5).padEnd(5, '0'), 2)];
  }
  return result;
}

function decodeBase32(value: string): Buffer {
  let bits = '';
  for (const char of value.replace(/=+$/g, '').toUpperCase()) {
    const index = BASE32.indexOf(char);
    if (index >= 0) bits += index.toString(2).padStart(5, '0');
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(Number.parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

function totpAt(secret: string, counter: number): string {
  const message = Buffer.alloc(8);
  message.writeBigUInt64BE(BigInt(counter));
  const digest = createHmac('sha1', decodeBase32(secret)).update(message).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const value = (digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return value.toString().padStart(6, '0');
}

export function verifyTotp(secret: string, code: string): boolean {
  if (!/^\d{6}$/.test(code)) return false;
  const counter = Math.floor(Date.now() / 30_000);
  return [-1, 0, 1].some((offset) => totpAt(secret, counter + offset) === code);
}

export function clientIp(request: NextRequest): string {
  return request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || 'unknown';
}

export async function recordSecurityEvent(
  request: NextRequest,
  action: string,
  user?: AdminUser,
  detail?: string,
): Promise<void> {
  await updateDatabase((db) => {
    addAudit(db, {
      userId: user?.id,
      username: user?.username,
      action,
      detail,
      ip: clientIp(request),
    });
  });
}

export function newId(): string {
  return randomUUID();
}

