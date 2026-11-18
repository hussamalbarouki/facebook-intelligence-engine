import { timingSafeEqual } from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';
import { addAudit, readDatabase, updateDatabase } from '@/lib/admin/storage';
import { enqueuePublication, formatOperationBody } from '@/lib/admin/publication';
import { answerTelegramCallback, buttonsForChoices, sendTelegramMessage } from '@/lib/admin/telegram-bot';
import { newId } from '@/lib/admin/security';
import type { ManagedContent, TelegramFlowPermission } from '@/lib/admin/types';
import { esc } from '@/lib/escapeHtml';

export const dynamic = 'force-dynamic';

type TelegramUpdate = {
  update_id?: number;
  message?: { text?: string; chat?: { id?: number; type?: string }; from?: { id?: number; first_name?: string; username?: string } };
  callback_query?: { id?: string; data?: string; from?: { id?: number; first_name?: string; username?: string }; message?: { chat?: { id?: number; type?: string } } };
};

function validSecret(request: NextRequest): boolean {
  const expected = process.env.TELEGRAM_WEBHOOK_SECRET || '';
  const actual = request.headers.get('x-telegram-bot-api-secret-token') || '';
  if (!expected || expected.length !== actual.length) return false;
  return timingSafeEqual(Buffer.from(expected), Buffer.from(actual));
}

function displayName(update: TelegramUpdate): string {
  const from = update.message?.from || update.callback_query?.from;
  return from?.username ? `@${from.username}` : from?.first_name || 'مناوب Telegram';
}

async function showMenu(chatId: string, permissions: TelegramFlowPermission[]) {
  const keyboard = [];
  if (permissions.includes('central-operations')) keyboard.push([{ text: 'بلاغ العمليات المركزية', callback_data: 'flow:ops' }]);
  if (permissions.includes('intelligence-reports')) keyboard.push([{ text: 'بلاغ معلوماتي', callback_data: 'flow:intel' }]);
  await sendTelegramMessage(chatId, 'اختر نوع البلاغ المطلوب:', keyboard);
}

export async function POST(request: NextRequest) {
  if (!process.env.TELEGRAM_BOT_TOKEN || !validSecret(request)) return NextResponse.json({ error: 'غير مصرح' }, { status: 401 });
  const update = await request.json().catch(() => ({})) as TelegramUpdate;
  const updateId = update.update_id;
  if (typeof updateId !== 'number') return NextResponse.json({ ok: true });

  const claimed = await updateDatabase((db) => {
    if (db.processedTelegramUpdates.includes(updateId)) return false;
    db.processedTelegramUpdates.push(updateId);
    db.processedTelegramUpdates = db.processedTelegramUpdates.slice(-2_000);
    return true;
  });
  if (!claimed) return NextResponse.json({ ok: true, duplicate: true });

  const fromId = update.message?.from?.id ?? update.callback_query?.from?.id;
  const chat = update.message?.chat ?? update.callback_query?.message?.chat;
  if (!fromId || !chat?.id || chat.type !== 'private') return NextResponse.json({ ok: true });
  const userId = String(fromId);
  const chatId = String(chat.id);
  const snapshot = await readDatabase();
  const operator = snapshot.telegramOperators.find((entry) => entry.userId === userId);
  if (!operator) {
    await sendTelegramMessage(chatId, `هذا الحساب غير مخوّل. معرّفك: <code>${userId}</code>`);
    return NextResponse.json({ ok: true });
  }

  const text = update.message?.text?.trim();
  if (text === '/start' || text === '/menu') {
    await updateDatabase((db) => { db.telegramConversations = db.telegramConversations.filter((entry) => entry.userId !== userId); });
    await showMenu(chatId, operator.permissions);
    return NextResponse.json({ ok: true });
  }
  if (text === '/cancel') {
    await updateDatabase((db) => { db.telegramConversations = db.telegramConversations.filter((entry) => entry.userId !== userId); });
    await sendTelegramMessage(chatId, 'تم إلغاء العملية الحالية. أرسل /start للبدء مجدداً.');
    return NextResponse.json({ ok: true });
  }

  const callback = update.callback_query;
  if (callback?.id && callback.data) {
    await answerTelegramCallback(callback.id);
    if (callback.data === 'flow:ops') {
      if (!operator.permissions.includes('central-operations')) return NextResponse.json({ ok: true });
      const db = await readDatabase();
      const first = db.operationOptions.fields[0];
      if (!first) { await sendTelegramMessage(chatId, 'لا توجد حقول مهيأة للبلاغ المركزي.'); return NextResponse.json({ ok: true }); }
      await updateDatabase((current) => {
        current.telegramConversations = current.telegramConversations.filter((entry) => entry.userId !== userId);
        current.telegramConversations.push({ userId, chatId, flow: 'central-operations', step: 0, draft: {}, updatedAt: new Date().toISOString() });
      });
      await sendTelegramMessage(chatId, `<b>${esc(first.label)}</b>`, buttonsForChoices(0, first.choices));
      return NextResponse.json({ ok: true });
    }
    if (callback.data === 'flow:intel') {
      if (!operator.permissions.includes('intelligence-reports')) return NextResponse.json({ ok: true });
      await updateDatabase((db) => {
        db.telegramConversations = db.telegramConversations.filter((entry) => entry.userId !== userId);
        db.telegramConversations.push({ userId, chatId, flow: 'intelligence-reports', step: 0, draft: {}, updatedAt: new Date().toISOString() });
      });
      await sendTelegramMessage(chatId, 'أرسل <b>عنوان البلاغ المعلوماتي</b>.');
      return NextResponse.json({ ok: true });
    }
    if (callback.data === 'flow:cancel') {
      await updateDatabase((db) => { db.telegramConversations = db.telegramConversations.filter((entry) => entry.userId !== userId); });
      await sendTelegramMessage(chatId, 'تم إلغاء العملية. أرسل /start للبدء مجدداً.');
      return NextResponse.json({ ok: true });
    }
    if (callback.data === 'intel:publish') {
      const item = await updateDatabase((db) => {
        const conversation = db.telegramConversations.find((entry) => entry.userId === userId && entry.flow === 'intelligence-reports');
        if (!conversation?.draft.title || !conversation.draft.body || !operator.permissions.includes('intelligence-reports')) return null;
        const now = new Date().toISOString();
        const report: ManagedContent = {
          id: newId(), category: 'intelligence-reports', title: conversation.draft.title.slice(0, 240), body: conversation.draft.body.slice(0, 20_000),
          status: 'published', priority: 'normal', pinned: false, confirmed: true,
          sourceType: 'telegram', sourceName: `بوت Telegram - ${operator.name || displayName(update)}`,
          externalId: `telegram-${updateId}`, createdBy: `telegram:${userId}`, createdAt: now, updatedAt: now, publishedAt: now,
        };
        db.content.push(report); enqueuePublication(db, report, 'content.published');
        db.telegramConversations = db.telegramConversations.filter((entry) => entry.userId !== userId);
        addAudit(db, { username: operator.name || displayName(update), action: 'telegram.intelligence_published', target: report.id, detail: `telegramUserId=${userId}` });
        return report;
      });
      await sendTelegramMessage(chatId, item ? `تم نشر البلاغ المعلوماتي بنجاح:\n\n<b>${esc(item.title)}</b>\n${esc(item.body).slice(0, 3500)}` : 'تعذر النشر. ابدأ مجدداً عبر /start.');
      return NextResponse.json({ ok: true });
    }
    const match = callback.data.match(/^op:(\d+):(\d+)$/);
    if (match) {
      const step = Number(match[1]); const choiceIndex = Number(match[2]);
      const result = await updateDatabase((db) => {
        const conversation = db.telegramConversations.find((entry) => entry.userId === userId && entry.flow === 'central-operations');
        const field = db.operationOptions.fields[step];
        const choice = field?.choices[choiceIndex];
        if (!conversation || conversation.step !== step || !choice || !operator.permissions.includes('central-operations')) return { error: true as const };
        conversation.draft[field.id] = choice;
        const next = db.operationOptions.fields[step + 1];
        if (next) { conversation.step += 1; conversation.updatedAt = new Date().toISOString(); return { next }; }
        const now = new Date();
        const report: ManagedContent = {
          id: newId(), category: 'central-operations', title: db.operationOptions.title,
          body: formatOperationBody(db.operationOptions, conversation.draft, now), status: 'published', priority: 'normal', pinned: false, confirmed: true,
          sourceType: 'telegram', sourceName: `بوت Telegram - ${operator.name || displayName(update)}`,
          externalId: `telegram-${updateId}`, structuredData: { ...conversation.draft }, createdBy: `telegram:${userId}`,
          createdAt: now.toISOString(), updatedAt: now.toISOString(), publishedAt: now.toISOString(),
        };
        db.content.push(report); enqueuePublication(db, report, 'content.published');
        db.telegramConversations = db.telegramConversations.filter((entry) => entry.userId !== userId);
        addAudit(db, { username: operator.name || displayName(update), action: 'telegram.operations_published', target: report.id, detail: `telegramUserId=${userId}` });
        return { report };
      });
      if ('next' in result && result.next) await sendTelegramMessage(chatId, `<b>${esc(result.next.label)}</b>`, buttonsForChoices(step + 1, result.next.choices));
      else if ('report' in result && result.report) await sendTelegramMessage(chatId, `تم نشر البلاغ المركزي بنجاح:\n\n${esc(result.report.body).slice(0, 3500)}`);
      else await sendTelegramMessage(chatId, 'انتهت صلاحية الخطوة. أرسل /start للبدء مجدداً.');
      return NextResponse.json({ ok: true });
    }
  }

  if (text) {
    const result = await updateDatabase((db) => {
      const conversation = db.telegramConversations.find((entry) => entry.userId === userId && entry.flow === 'intelligence-reports');
      if (!conversation || !operator.permissions.includes('intelligence-reports')) return null;
      if (conversation.step === 0) {
        conversation.draft.title = text.slice(0, 240); conversation.step = 1; conversation.updatedAt = new Date().toISOString();
        return 'body';
      }
      if (conversation.step === 1) {
        conversation.draft.body = text.slice(0, 20_000); conversation.step = 2; conversation.updatedAt = new Date().toISOString();
        return 'confirm';
      }
      return null;
    });
    if (result === 'body') await sendTelegramMessage(chatId, 'أرسل الآن <b>نص الخبر كاملاً</b>.');
    else if (result === 'confirm') await sendTelegramMessage(chatId, 'راجع البلاغ ثم أكد النشر:', [[{ text: 'نشر البلاغ', callback_data: 'intel:publish' }], [{ text: 'إلغاء', callback_data: 'flow:cancel' }]]);
    else await showMenu(chatId, operator.permissions);
  }
  return NextResponse.json({ ok: true });
}
