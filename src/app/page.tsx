'use client';

import dynamic from 'next/dynamic';
import Image from 'next/image';
import ThreatClock from '@/components/panels/ThreatClock';
import NewsFeed from '@/components/panels/NewsFeed';
import ConflictFeed from '@/components/panels/ConflictFeed';
import TelegramPanel from '@/components/panels/TelegramPanel';
import FlightsPanel from '@/components/panels/FlightsPanel';
import StrikesPanel from '@/components/panels/StrikesPanel';
import AlertsPanel from '@/components/panels/AlertsPanel';
import SatellitePanel from '@/components/panels/SatellitePanel';
import NavalPanel from '@/components/panels/NavalPanel';
import RegionalAlertsPanel from '@/components/panels/RegionalAlertsPanel';
import ManagedContentPanel from '@/components/panels/ManagedContentPanel';
import ConflictToggle from '@/components/ConflictToggle';
import ThemeSwitcher from '@/components/ThemeSwitcher';
import { useConflict } from '@/lib/conflicts/context';
import { useState, useEffect } from 'react';

const ConflictMap = dynamic(() => import('@/components/map/ConflictMap'), {
  ssr: false,
  loading: () => <div className="panel h-full loading-shimmer" />,
});

export default function Dashboard() {
  const { key: conflictKey } = useConflict();
  const [uptime, setUptime] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => {
      setUptime(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const formatUptime = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Top bar */}
      <header className="border-b border-(--border-color) bg-(--bg-secondary) shrink-0">
        <div className="flex items-center justify-between px-4 py-1.5">
          <div className="flex items-center gap-3 shrink-0">
            <Image
              src="/eagle-eye-logo.png"
              alt="شعار منظومة عين النسر"
              width={52}
              height={52}
              priority
              className="brand-logo h-11 w-11 object-contain"
            />
            <div dir="rtl" className="text-right leading-tight">
              <h1 className="brand-name text-[13px] font-bold whitespace-nowrap">
                شعبة المعلومات - عين النسر
              </h1>
              <p className="brand-subtitle mt-1 text-[8px] whitespace-nowrap">
                مركز الرصد والتحليل المعلوماتي // منظومة عين النسر
              </p>
            </div>
          </div>
          <div dir="rtl" className="hidden items-center gap-5 text-[9px] text-(--text-secondary) xl:flex">
            <span className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-(--green) animate-pulse" />
              مركز العمليات متصل
            </span>
            <span className="h-4 w-px bg-(--border-color)" />
            <span>قنوات الرصد والمعلومات</span>
            <span className="h-4 w-px bg-(--border-color)" />
            <span className="text-(--accent)">وضع المتابعة المباشرة</span>
          </div>
          <div className="flex items-center gap-4 text-[9px] text-(--text-secondary)">
            <ConflictToggle />
            <ThemeSwitcher />
            <span>زمن الجلسة {formatUptime(uptime)}</span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-(--green) animate-pulse" />
              مباشر
            </span>
          </div>
        </div>
        <div className="border-t border-(--border-color)">
          <ThreatClock />
        </div>
      </header>

      {/* Main grid - 3 rows */}
      <main className="flex-1 grid grid-cols-12 gap-1 p-1 overflow-hidden"
        style={{ gridTemplateRows: '2fr 1.5fr 1.5fr' }}
      >
        {/* === ROW 1: Live intelligence feeds and map === */}
        <div className="col-span-3 min-h-0">
          <NewsFeed />
        </div>
        <div className="col-span-4 min-h-0">
          <ConflictMap key={conflictKey} className="h-full" />
        </div>
        <div className="col-span-2 min-h-0">
          <AlertsPanel />
        </div>
        <div className="col-span-3 min-h-0 flex flex-col gap-1">
          <div className="flex-1 min-h-0">
            <TelegramPanel />
          </div>
        </div>

        {/* === ROW 2: Local news, operations, conflicts and flights === */}
        <div className="col-span-3 min-h-0">
          <ManagedContentPanel category="local-news" title="أخبار محلية" />
        </div>
        <div className="col-span-3 min-h-0">
          <StrikesPanel />
        </div>
        <div className="col-span-2 min-h-0">
          <ManagedContentPanel category="central-operations" title="بلاغات العمليات المركزية" />
        </div>
        <div className="col-span-2 min-h-0">
          <ConflictFeed />
        </div>
        <div className="col-span-2 min-h-0">
          <FlightsPanel />
        </div>

        {/* === ROW 3: Regional, naval, information, Facebook and satellite === */}
        <div className="col-span-3 min-h-0">
          <RegionalAlertsPanel />
        </div>
        <div className="col-span-3 min-h-0">
          <NavalPanel />
        </div>
        <div className="col-span-2 min-h-0">
          <ManagedContentPanel category="intelligence-reports" title="بلاغات معلوماتية" />
        </div>
        <div className="col-span-2 min-h-0">
          <ManagedContentPanel category="facebook-news" title="أخبار فيسبوك" />
        </div>
        <div className="col-span-2 min-h-0">
          <SatellitePanel />
        </div>
      </main>

      {/* Bottom status bar */}
      <footer
        dir="rtl"
        className="border-t border-(--border-color) bg-(--bg-secondary) px-4 py-1.5 flex items-center justify-between text-[9px] text-(--text-secondary) shrink-0"
      >
        <span className="text-(--accent)">منظومة عين النسر // شعبة المعلومات</span>
        <div className="flex items-center gap-4">
          <span>مركز الرصد والتحليل المعلوماتي</span>
          <span>جميع الحقوق محفوظة © {new Date().getFullYear()}</span>
        </div>
      </footer>
    </div>
  );
}
