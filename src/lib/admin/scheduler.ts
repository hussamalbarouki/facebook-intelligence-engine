import { syncSources } from './sync';

let started = false;
let running = false;

async function tick(): Promise<void> {
  if (running) return;
  running = true;
  try {
    await syncSources({ onlyDue: true, username: 'المزامنة التلقائية' });
  } catch (error) {
    console.error('تعذرت المزامنة التلقائية للمصادر', error instanceof Error ? error.message : error);
  } finally {
    running = false;
  }
}

export function startSourceScheduler(): void {
  if (started || process.env.NODE_ENV !== 'production') return;
  started = true;
  const first = setTimeout(tick, 90_000);
  const interval = setInterval(tick, 5 * 60_000);
  first.unref();
  interval.unref();
}
