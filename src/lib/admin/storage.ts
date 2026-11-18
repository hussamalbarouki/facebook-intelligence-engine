import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { randomBytes, randomUUID } from 'node:crypto';
import path from 'node:path';
import type { AdminDatabase, AuditEntry, ContentSource } from './types';
import { PERMISSIONS } from './types';

const DATA_DIR = process.env.EAGLE_EYE_DATA_DIR || '/data';
const DATA_FILE = path.join(DATA_DIR, 'eagle-eye-admin.json');
const SEED_SALT = 'd0749795d01124dc9fb3bb20f0e569e2';
const SEED_HASH = 'b1b81fae14cea2c61f7f843418529b5a81bd38b1a2c8cba058a367dd99ba68995b625b711ea6f74c71bf8d48f320e9d1437408cf2ff381324c86e66c0e4c2e68';

let writeQueue: Promise<unknown> = Promise.resolve();
let ensurePromise: Promise<void> | null = null;

function initialDatabase(): AdminDatabase {
  const now = new Date().toISOString();
  const sources = defaultSyrianSources(now);
  return {
    version: 5,
    security: { sessionSecret: randomBytes(48).toString('base64url') },
    roles: [
      { id: 'super-admin', name: 'مدير النظام', permissions: [...PERMISSIONS], system: true },
      {
        id: 'operations',
        name: 'العمليات المركزية',
        permissions: ['content.read', 'content.operations.manage'],
        system: true,
      },
      {
        id: 'information',
        name: 'البلاغات المعلوماتية',
        permissions: ['content.read', 'content.intelligence.manage'],
        system: true,
      },
      {
        id: 'editor',
        name: 'محرر المحتوى',
        permissions: ['content.read', 'content.local.manage', 'content.facebook.manage'],
        system: true,
      },
    ],
    users: [
      {
        id: 'user-admin',
        username: 'Veto',
        displayName: 'مدير النظام',
        passwordSalt: SEED_SALT,
        passwordHash: SEED_HASH,
        roleId: 'super-admin',
        active: true,
        mustChangePassword: true,
        totpEnabled: false,
        failedAttempts: 0,
        createdAt: now,
        updatedAt: now,
      },
    ],
    content: [],
    sources,
    translationCache: [],
    operationOptions: {
      title: 'بلاغ العمليات المركزية',
      footer: 'شعبة المعلومات - منظومة عين النسر',
      fields: [
        { id: 'type', label: 'نوع البلاغ', choices: ['بلاغ أمني', 'بلاغ ميداني', 'بلاغ متابعة', 'بلاغ طارئ'], required: true },
        { id: 'area', label: 'الجهة', choices: ['المركز', 'الشمال', 'الجنوب', 'الشرق', 'الغرب'], required: true },
        { id: 'severity', label: 'درجة الخطورة', choices: ['اعتيادي', 'مهم', 'عاجل', 'حرج'], required: true },
      ],
      types: ['بلاغ أمني', 'بلاغ ميداني', 'بلاغ متابعة', 'بلاغ طارئ'],
      areas: ['المركز', 'الشمال', 'الجنوب', 'الشرق', 'الغرب'],
      severities: ['اعتيادي', 'مهم', 'عاجل', 'حرج'],
      customFields: [],
    },
    telegramOperators: [],
    telegramConversations: [],
    processedTelegramUpdates: [],
    publicationEvents: [],
    audit: [
      {
        id: randomUUID(),
        action: 'system.initialized',
        detail: 'تم إنشاء مخزن لوحة التحكم',
        createdAt: now,
      },
    ],
  };
}

function defaultSyrianSources(now: string): ContentSource[] {
  const definitions: Array<[string, ContentSource['type'], string, number]> = [
    ['وكالة سانا', 'rss', 'https://sana.sy/feed/', 8],
    ['عنب بلدي', 'rss', 'https://www.enabbaladi.net/feed/', 8],
    ['تلفزيون سوريا', 'rss', 'https://www.syria.tv/rss', 8],
    ['سناك سوري', 'rss', 'https://snacksyrian.com/feed/', 8],
    ['نورث برس العربية', 'rss', 'https://npasyria.com/feed/', 8],
    ['قناة حلب اليوم', 'rss', 'https://halabtodaytv.net/feed', 8],
    ['سوريا على طول', 'rss', 'https://syriadirect.org/ar/feed/', 8],
    ['صحيفة الوطن السورية', 'rss', 'https://alwatan.sy/feed/', 8],
    ['زمان الوصل', 'rss', 'https://www.zamanalwsl.net/rss', 8],
    ['سانا - تيليغرام', 'telegram', 'https://t.me/s/SyrianArabNewsAgency', 5],
    ['عنب بلدي - تيليغرام', 'telegram', 'https://t.me/s/EnabBaladi', 5],
    ['أثر برس - تيليغرام', 'telegram', 'https://t.me/s/athrpress', 5],
    ['حلب اليوم - تيليغرام', 'telegram', 'https://t.me/s/halabtodaytv', 5],
    ['زمان الوصل - تيليغرام', 'telegram', 'https://t.me/s/zamanalwsl', 5],
  ];
  return definitions.map(([name, type, url, maxItems]) => ({
    id: randomUUID(), name, type, url, enabled: true, autoPublish: true,
    autoTranslate: false, maxItems, createdAt: now, updatedAt: now,
  }));
}

async function ensureDatabase(): Promise<void> {
  if (!ensurePromise) {
    ensurePromise = (async () => {
      await mkdir(DATA_DIR, { recursive: true, mode: 0o700 });
      try {
        await readFile(DATA_FILE, 'utf8');
      } catch {
        await atomicWrite(initialDatabase());
      }
    })().catch((error) => {
      ensurePromise = null;
      throw error;
    });
  }
  await ensurePromise;
}

async function atomicWrite(data: AdminDatabase): Promise<void> {
  await mkdir(DATA_DIR, { recursive: true, mode: 0o700 });
  const tmp = `${DATA_FILE}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(tmp, JSON.stringify(data, null, 2), { encoding: 'utf8', mode: 0o600 });
  await rename(tmp, DATA_FILE);
}

export async function readDatabase(): Promise<AdminDatabase> {
  await ensureDatabase();
  const db = JSON.parse(await readFile(DATA_FILE, 'utf8')) as AdminDatabase;
  let migrated = false;
  if (db.version < 3) {
    const seedAdmin = db.users.find((user) => user.id === 'user-admin' || user.username.toLowerCase() === 'veto');
    if (seedAdmin) {
      seedAdmin.username = 'Veto';
      seedAdmin.displayName = 'مدير النظام';
      seedAdmin.passwordSalt = SEED_SALT;
      seedAdmin.passwordHash = SEED_HASH;
      seedAdmin.roleId = 'super-admin';
      seedAdmin.active = true;
      seedAdmin.mustChangePassword = true;
      seedAdmin.totpEnabled = false;
      seedAdmin.totpSecret = undefined;
      seedAdmin.pendingTotpSecret = undefined;
      seedAdmin.failedAttempts = 0;
      seedAdmin.lockedUntil = undefined;
      seedAdmin.updatedAt = new Date().toISOString();
      addAudit(db, { userId: seedAdmin.id, username: seedAdmin.username, action: 'system.initial_admin_migrated' });
    }
    db.version = 3;
    migrated = true;
  }
  if (db.version < 4) {
    for (const item of db.content) {
      if ((item.category as string) === 'general') item.category = 'facebook-news';
    }
    for (const role of db.roles) {
      role.permissions = role.permissions.map((permission) => (permission as string) === 'content.general.manage' ? 'content.facebook.manage' : permission);
    }
    const existingUrls = new Set(db.sources.map((source) => source.url.replace(/\/$/, '')));
    for (const source of defaultSyrianSources(new Date().toISOString())) {
      if (!existingUrls.has(source.url.replace(/\/$/, ''))) db.sources.push(source);
    }
    for (const source of db.sources) {
      source.autoTranslate ??= false;
      source.maxItems ??= source.type === 'telegram' ? 5 : 8;
    }
    db.translationCache ??= [];
    db.version = 4;
    migrated = true;
    addAudit(db, { action: 'system.sources_and_facebook_migrated', detail: 'تم تجهيز مصادر الأخبار السورية وقسم أخبار فيسبوك' });
  }
  if (db.version < 5) {
    db.operationOptions.title ??= 'بلاغ العمليات المركزية';
    db.operationOptions.footer ??= 'شعبة المعلومات - منظومة عين النسر';
    db.operationOptions.fields ??= [
      { id: 'type', label: 'نوع البلاغ', choices: db.operationOptions.types || [], required: true },
      { id: 'area', label: 'الجهة', choices: db.operationOptions.areas || [], required: true },
      { id: 'severity', label: 'درجة الخطورة', choices: db.operationOptions.severities || [], required: true },
    ];
    db.telegramOperators ??= [];
    db.telegramConversations ??= [];
    db.processedTelegramUpdates ??= [];
    db.publicationEvents ??= [];
    db.version = 5;
    migrated = true;
    addAudit(db, { action: 'system.operational_forms_migrated', detail: 'تم فصل نماذج البلاغات وتجهيز سجل أحداث النشر' });
  }
  if (migrated) await atomicWrite(db);
  return db;
}

export async function updateDatabase<T>(mutator: (db: AdminDatabase) => T | Promise<T>): Promise<T> {
  let result!: T;
  const operation = writeQueue.then(async () => {
    const db = await readDatabase();
    result = await mutator(db);
    db.audit = db.audit.slice(-1999);
    await atomicWrite(db);
  });
  writeQueue = operation.catch(() => undefined);
  await operation;
  return result;
}

export function addAudit(
  db: AdminDatabase,
  entry: Omit<AuditEntry, 'id' | 'createdAt'>,
): void {
  db.audit.push({ id: randomUUID(), createdAt: new Date().toISOString(), ...entry });
}

