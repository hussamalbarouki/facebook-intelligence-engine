type InlineButton = { text: string; callback_data: string };

function botUrl(method: string): string {
  return `https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}/${method}`;
}

async function callTelegram(method: string, payload: Record<string, unknown>): Promise<void> {
  if (!process.env.TELEGRAM_BOT_TOKEN) throw new Error('Telegram bot is not configured');
  const response = await fetch(botUrl(method), {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload), signal: AbortSignal.timeout(10_000), cache: 'no-store',
  });
  if (!response.ok) throw new Error(`Telegram API failed (${response.status})`);
}

export async function sendTelegramMessage(chatId: string, text: string, keyboard?: InlineButton[][]): Promise<void> {
  await callTelegram('sendMessage', {
    chat_id: chatId, text, parse_mode: 'HTML',
    ...(keyboard ? { reply_markup: { inline_keyboard: keyboard } } : {}),
  });
}

export async function answerTelegramCallback(callbackQueryId: string, text?: string): Promise<void> {
  await callTelegram('answerCallbackQuery', { callback_query_id: callbackQueryId, ...(text ? { text } : {}) });
}

export function buttonsForChoices(step: number, choices: string[]): InlineButton[][] {
  const buttons = choices.map((choice, index) => ({ text: choice, callback_data: `op:${step}:${index}` }));
  const rows: InlineButton[][] = [];
  for (let index = 0; index < buttons.length; index += 2) rows.push(buttons.slice(index, index + 2));
  return rows;
}
