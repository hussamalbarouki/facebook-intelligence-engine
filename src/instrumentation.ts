export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    const { startSourceScheduler } = await import('./lib/admin/scheduler');
    startSourceScheduler();
  }
}
