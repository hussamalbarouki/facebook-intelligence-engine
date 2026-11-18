'use client';

import { useState, useEffect } from 'react';
import { useConflict } from '@/lib/conflicts/context';

export default function ThreatClock() {
  const { config } = useConflict();
  const TIME_ZONES = config.client.timeZones;
  const [time, setTime] = useState<Date | null>(null);
  const zoneNames: Record<string, string> = {
    'America/New_York': 'واشنطن', 'Europe/London': 'لندن', 'Europe/Kyiv': 'كييف',
    'Europe/Moscow': 'موسكو', 'Europe/Warsaw': 'وارسو', 'Europe/Berlin': 'برلين',
    'Asia/Tehran': 'طهران', 'Asia/Jerusalem': 'القدس', 'Asia/Baghdad': 'بغداد',
    'Asia/Damascus': 'دمشق', 'Asia/Beirut': 'بيروت', 'Asia/Riyadh': 'الرياض',
  };

  // Starts null so the server render and first client render match; the first
  // tick is deferred (not a synchronous setState in the effect body).
  useEffect(() => {
    const tick = () => setTime(new Date());
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 1000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, []);

  if (!time) {
    return (
      <div className="flex items-center gap-4 px-4 py-1.5">
        <span className="text-[9px] text-(--text-secondary)">جارٍ تهيئة التوقيت...</span>
      </div>
    );
  }

  const utc = time.toISOString().replace('T', ' ').substring(0, 19);

  return (
    <div className="flex items-center gap-4 px-4 py-1.5 overflow-x-auto">
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-[9px] text-(--text-secondary)">التوقيت العالمي</span>
        <span className="text-xs font-bold text-(--accent) glow-text font-mono">{utc}Z</span>
      </div>
      <div className="h-4 w-px bg-(--border-color)" />
      {TIME_ZONES.map((tz, i) => {
        const localTime = time.toLocaleTimeString('en-US', {
          timeZone: tz.zone,
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        });
        const hour = parseInt(localTime.split(':')[0]);
        const isNight = hour < 6 || hour >= 20;

        return (
          <div key={i} className="flex items-center gap-1.5 shrink-0">
            <span className="text-[9px] text-(--text-secondary)">{zoneNames[tz.zone] || tz.label}</span>
            <span className={`text-[11px] font-mono font-bold ${isNight ? 'text-(--text-secondary)' : 'text-(--text-primary)'}`}>
              {localTime}
            </span>
          </div>
        );
      })}
    </div>
  );
}
