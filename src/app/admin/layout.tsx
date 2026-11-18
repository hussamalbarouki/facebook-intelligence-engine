import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'لوحة القيادة | شعبة المعلومات - عين النسر',
  robots: { index: false, follow: false },
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return children;
}
