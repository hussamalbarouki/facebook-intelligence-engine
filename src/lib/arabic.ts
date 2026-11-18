const LABELS: Record<string, string> = {
  STRIKE: 'ضربة', DEFENSE: 'دفاع', MILITARY: 'عسكري', DIPLOMATIC: 'دبلوماسي', NUCLEAR: 'نووي', REPORT: 'تقرير',
  MISSILE: 'صاروخ', INTERCEPTION: 'اعتراض', DRONE: 'مسيّرة', AIRSTRIKE: 'غارة جوية', ROCKET: 'قذيفة صاروخية',
  CLEAR: 'آمن', MONITORING: 'مراقبة', MONITOR: 'مراقبة', ALERT: 'تنبيه', CRITICAL: 'حرج',
  low: 'منخفض', medium: 'متوسط', high: 'مرتفع', critical: 'حرج', extreme: 'شديد',
  Active: 'نشطة', Deployed: 'منتشرة', Transit: 'في العبور', Port: 'في الميناء',
  'Aircraft Carrier': 'حاملة طائرات', Destroyer: 'مدمرة', Cruiser: 'طراد', Frigate: 'فرقاطة', Corvette: 'كورفيت', Submarine: 'غواصة',
  'Guided Missile Submarine': 'غواصة صواريخ موجهة', 'Amphibious Assault Ship': 'سفينة إنزال هجومية', 'Forward Base Ship': 'سفينة قاعدة أمامية', 'Fast Attack Craft': 'زورق هجوم سريع',
  'ISR Drone (UAV)': 'مسيّرة استطلاع', 'High-Alt ISR/Drone': 'استطلاع عالي الارتفاع', 'Fast Mover': 'طائرة سريعة', 'SIGINT/ELINT': 'استخبارات إلكترونية',
  AWACS: 'إنذار مبكر', JSTARS: 'مراقبة جوية أرضية', 'Maritime Patrol': 'دورية بحرية', ISR: 'استطلاع', Bomber: 'قاذفة', Fighter: 'مقاتلة',
  'Transport (C-17/C-5)': 'نقل عسكري', 'Aerial Tanker (KC-135/KC-46)': 'ناقلة وقود جوية', 'Navy P-8/MPA': 'دورية بحرية', 'Special Operations': 'عمليات خاصة',
  'CSAR/Rescue': 'بحث وإنقاذ', 'VIP/Government': 'حكومية', 'RAF Transport': 'نقل جوي', 'Medical Evacuation': 'إخلاء طبي', 'Tactical Transport': 'نقل تكتيكي', 'Rotary/Low-Level': 'مروحية/ارتفاع منخفض', Military: 'عسكرية',
  Iran: 'إيران', Israel: 'إسرائيل', Iraq: 'العراق', Syria: 'سوريا', Lebanon: 'لبنان', Jordan: 'الأردن', Egypt: 'مصر', Turkey: 'تركيا', Yemen: 'اليمن',
  Russia: 'روسيا', Ukraine: 'أوكرانيا', Belarus: 'بيلاروسيا', Poland: 'بولندا', Germany: 'ألمانيا',
  Tehran: 'طهران', Isfahan: 'أصفهان', Shiraz: 'شيراز', Tabriz: 'تبريز', 'Bandar Abbas': 'بندر عباس',
  'Tel Aviv': 'تل أبيب', Jerusalem: 'القدس', Haifa: 'حيفا', Baghdad: 'بغداد', Damascus: 'دمشق', Beirut: 'بيروت',
  Riyadh: 'الرياض', Dubai: 'دبي', Doha: 'الدوحة', Manama: 'المنامة', 'Kuwait City': 'مدينة الكويت', Amman: 'عمّان', Cairo: 'القاهرة', Ankara: 'أنقرة',
  "Sana'a": 'صنعاء', Aden: 'عدن', Muscat: 'مسقط', Dimona: 'ديمونا', Kyiv: 'كييف', Moscow: 'موسكو', Warsaw: 'وارسو', Berlin: 'برلين',
  'Pikud HaOref': 'قيادة الجبهة الداخلية', 'Ukraine Air Raid Alerts': 'تنبيهات الغارات الجوية الأوكرانية',
  'Persian Gulf': 'الخليج العربي', 'Red Sea': 'البحر الأحمر', Mediterranean: 'البحر المتوسط', 'Black Sea': 'البحر الأسود', Baltic: 'بحر البلطيق',
};

export function arabicLabel(value: string): string {
  return LABELS[value] || value;
}
