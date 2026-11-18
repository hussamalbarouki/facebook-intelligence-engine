'use client';

import Image from 'next/image';
import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';

export default function AdminLogin() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [totp, setTotp] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError('');
    const response = await fetch('/api/admin/auth/login', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ username, password, totp }) });
    const data = await response.json().catch(() => ({}));
    setLoading(false);
    if (!response.ok) return setError(data.error || 'تعذر تسجيل الدخول');
    router.replace('/admin'); router.refresh();
  }

  return <main dir="rtl" className="min-h-screen grid place-items-center bg-black p-5">
    <section className="w-full max-w-md rounded-2xl border border-amber-500/25 bg-zinc-950 p-7 shadow-2xl shadow-amber-950/30">
      <div className="mb-7 flex items-center gap-4"><Image src="/eagle-eye-logo.png" alt="عين النسر" width={76} height={76} className="h-20 w-20 object-contain"/><div><h1 className="text-xl font-bold text-amber-300">شعبة المعلومات</h1><p className="mt-1 text-xs text-zinc-400">لوحة قيادة منظومة عين النسر</p></div></div>
      <form onSubmit={submit} className="space-y-4">
        <label className="block text-sm text-zinc-300">اسم المستخدم<input autoComplete="username" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} className="mt-2 w-full rounded-lg border border-zinc-700 bg-black px-4 py-3 text-left text-white outline-none focus:border-amber-400" dir="ltr" required/></label>
        <label className="block text-sm text-zinc-300">كلمة السر<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-2 w-full rounded-lg border border-zinc-700 bg-black px-4 py-3 text-left text-white outline-none focus:border-amber-400" dir="ltr" required/></label>
        <label className="block text-sm text-zinc-300">رمز Google Authenticator <span className="text-zinc-600">(عند تفعيله)</span><input inputMode="numeric" autoComplete="one-time-code" value={totp} onChange={(e) => setTotp(e.target.value.replace(/\D/g, '').slice(0, 6))} className="mt-2 w-full rounded-lg border border-zinc-700 bg-black px-4 py-3 text-center tracking-[.5em] text-white outline-none focus:border-amber-400" dir="ltr"/></label>
        {error && <p role="alert" className="rounded-lg border border-red-900 bg-red-950/50 p-3 text-sm text-red-300">{error}</p>}
        <button disabled={loading} className="w-full rounded-lg bg-amber-400 px-4 py-3 font-bold text-black transition hover:bg-amber-300 disabled:opacity-50">{loading ? 'جارٍ التحقق...' : 'دخول آمن'}</button>
      </form>
      <p className="mt-6 text-center text-[11px] text-zinc-600">جلسة مشفرة • حماية محاولات الدخول • سجل تدقيق</p>
    </section>
  </main>;
}
