import { NextRequest, NextResponse } from 'next/server';
import { addAudit, readDatabase, updateDatabase } from '@/lib/admin/storage';
import { requireAdmin } from '@/lib/admin/security';
import { apifyConfigured } from '@/lib/admin/facebook';
import { translationConfigured } from '@/lib/admin/translation';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const auth = await requireAdmin(request, 'content.read');
  if (auth instanceof NextResponse) return auth;
  const db = await readDatabase();
  return NextResponse.json({
    operationOptions: db.operationOptions,
    telegramOperators: db.telegramOperators,
    publicationPipeline: {
      events: db.publicationEvents.length,
      pendingDeliveries: db.publicationEvents.flatMap((event) => event.deliveries).filter((delivery) => delivery.status === 'pending').length,
    },
    roles: db.roles.map(({ id, name, permissions }) => ({ id, name, permissions })),
    integrations: {
      apify: apifyConfigured(),
      microsoftTranslator: translationConfigured(),
      translatedCharacters: db.translationCache.reduce((sum, entry) => sum + entry.characterCount, 0),
      cachedTranslations: db.translationCache.length,
      automaticSync: 'كل ساعة',
      telegramBot: Boolean(process.env.TELEGRAM_BOT_TOKEN && process.env.TELEGRAM_WEBHOOK_SECRET),
    },
  });
}

export async function PATCH(request: NextRequest) {
  const auth = await requireAdmin(request, 'operations.configure');
  if (auth instanceof NextResponse) return auth;
  const body = await request.json().catch(() => ({}));
  const cleanList = (value: unknown) => Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string').map((item) => item.trim().slice(0, 100)).filter(Boolean).slice(0, 100) : null;
  const cleanFields = (value: unknown) => Array.isArray(value) ? value.slice(0, 30).map((field, index) => {
    const raw = field && typeof field === 'object' ? field as Record<string, unknown> : {};
    const label = typeof raw.label === 'string' ? raw.label.trim().slice(0, 100) : '';
    const choices = cleanList(raw.choices)?.slice(0, 30) || [];
    const suppliedId = typeof raw.id === 'string' ? raw.id.replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 40) : '';
    return { id: suppliedId || `field-${index + 1}`, label, choices, required: raw.required !== false };
  }).filter((field) => field.label && field.choices.length) : null;
  const cleanOperators = (value: unknown) => Array.isArray(value) ? value.slice(0, 100).map((entry) => {
    const raw = entry && typeof entry === 'object' ? entry as Record<string, unknown> : {};
    const userId = typeof raw.userId === 'string' ? raw.userId.trim() : '';
    const name = typeof raw.name === 'string' ? raw.name.trim().slice(0, 100) : '';
    const permissions = Array.isArray(raw.permissions) ? raw.permissions.filter((item): item is 'central-operations' | 'intelligence-reports' => item === 'central-operations' || item === 'intelligence-reports') : [];
    return { userId, name, permissions: [...new Set(permissions)] };
  }).filter((entry) => /^\d{3,20}$/.test(entry.userId) && entry.permissions.length) : null;
  await updateDatabase((db) => {
    db.operationOptions.types = cleanList(body.types) || db.operationOptions.types;
    db.operationOptions.areas = cleanList(body.areas) || db.operationOptions.areas;
    db.operationOptions.severities = cleanList(body.severities) || db.operationOptions.severities;
    if (typeof body.operationTitle === 'string' && body.operationTitle.trim()) db.operationOptions.title = body.operationTitle.trim().slice(0, 160);
    if (typeof body.operationFooter === 'string') db.operationOptions.footer = body.operationFooter.trim().slice(0, 1000);
    const fields = cleanFields(body.operationFields);
    if (fields?.length) db.operationOptions.fields = fields;
    const operators = cleanOperators(body.telegramOperators);
    if (operators) db.telegramOperators = operators;
    addAudit(db, { userId: auth.user.id, username: auth.user.username, action: 'operations.options_updated' });
  });
  return NextResponse.json({ ok: true });
}
