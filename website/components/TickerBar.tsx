'use client';
import { motion } from 'framer-motion';

const TICKER = [
  { sym: 'NIFTY 50', val: '24,815.20', chg: '+0.86%', up: true },
  { sym: 'SENSEX', val: '81,420.50', chg: '+0.74%', up: true },
  { sym: 'BANKNIFTY', val: '52,180.10', chg: '-0.21%', up: false },
  { sym: 'EUR/USD', val: '1.0842', chg: '+0.32%', up: true },
  { sym: 'USD/INR', val: '83.42', chg: '+0.12%', up: true },
  { sym: 'GBP/USD', val: '1.2719', chg: '-0.08%', up: false },
  { sym: 'BTC/USD', val: '67,840', chg: '+2.14%', up: true },
  { sym: 'ETH/USD', val: '3,512', chg: '+1.62%', up: true },
  { sym: 'GOLD', val: '₹74,520', chg: '+0.45%', up: true },
  { sym: 'SILVER', val: '₹88,210', chg: '-0.32%', up: false },
  { sym: 'CRUDE OIL', val: '$78.40', chg: '+1.08%', up: true },
  { sym: 'TCS', val: '₹4,182', chg: '+0.92%', up: true },
  { sym: 'RELIANCE', val: '₹2,945', chg: '+0.36%', up: true },
  { sym: 'INFY', val: '₹1,872', chg: '-0.18%', up: false },
];

export default function TickerBar() {
  // Double the array so the marquee loops smoothly
  const items = [...TICKER, ...TICKER];
  return (
    <div className="relative border-y border-white/5 bg-navy-900/40 backdrop-blur-sm py-3 overflow-hidden">
      <div className="ticker-mask">
        <motion.div className="flex gap-10 whitespace-nowrap will-change-transform"
          animate={{ x: ['0%', '-50%'] }} transition={{ duration: 60, repeat: Infinity, ease: 'linear' }}>
          {items.map((t, i) => (
            <div key={i} className="flex items-center gap-3 text-sm">
              <span className="text-white/50 font-medium tracking-wide">{t.sym}</span>
              <span className="font-semibold text-white">{t.val}</span>
              <span className={t.up ? 'text-emerald-400' : 'text-rose-400'}>{t.up ? '▲' : '▼'} {t.chg}</span>
              <span className="text-white/10">•</span>
            </div>
          ))}
        </motion.div>
      </div>
      <p className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-white/30 hidden md:block">Indicative · not live</p>
    </div>
  );
}
