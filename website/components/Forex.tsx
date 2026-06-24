'use client';
import Reveal from './Reveal';
import { useEffect, useRef } from 'react';
import { CandlestickChart, Zap, Globe, Wallet } from 'lucide-react';

const FEATURES = [
  { icon: Zap, title: 'Sub-second execution', desc: 'Co-located servers in NY4 & LD4 data centers.' },
  { icon: Globe, title: '60+ currency pairs', desc: 'Majors, minors, exotics. Commodities & indices.' },
  { icon: Wallet, title: '₹10L paper trading', desc: 'Practice with realistic price feeds, zero risk.' },
  { icon: CandlestickChart, title: 'TradingView charts', desc: 'Pro indicators, 100+ studies, save layouts.' },
];

export default function Forex() {
  const widgetRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!widgetRef.current) return;
    // Avoid double-loading on hot reload
    if (widgetRef.current.dataset.loaded === '1') return;
    const s = document.createElement('script');
    s.src = 'https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js';
    s.async = true;
    s.innerHTML = JSON.stringify({
      symbol: 'FX:EURUSD',
      width: '100%',
      height: 340,
      locale: 'en',
      dateRange: '12M',
      colorTheme: 'dark',
      isTransparent: true,
      autosize: false,
      largeChartUrl: '',
    });
    widgetRef.current.appendChild(s);
    widgetRef.current.dataset.loaded = '1';
  }, []);

  return (
    <section id="forex" className="relative section-pad bg-gradient-to-b from-transparent via-navy-900/30 to-transparent">
      <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-12 items-center">
        <Reveal>
          <div className="eyebrow mb-3">Forex Trading · Demo Mode</div>
          <h2 className="heading-lg mb-6">Trade the world’s <span className="gold-text">most liquid markets</span> — risk-free.</h2>
          <p className="text-white/70 leading-relaxed mb-8">
            Master forex with our paper-trading sandbox: ₹10 lakh virtual capital, realistic order matching, pro charts and zero real risk. Graduate to live trading when you’re ready.
          </p>
          <div className="grid sm:grid-cols-2 gap-4 mb-8">
            {FEATURES.map(f => (
              <div key={f.title} className="glass p-4">
                <f.icon className="w-5 h-5 text-sky-400 mb-2" />
                <div className="font-semibold text-sm mb-1">{f.title}</div>
                <div className="text-xs text-white/60">{f.desc}</div>
              </div>
            ))}
          </div>
          <a href="#download" className="btn-ghost">Try Demo Trading</a>
        </Reveal>

        <Reveal delay={0.15}>
          <div className="glass p-4 md:p-6">
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="text-xs text-gold-400 font-semibold tracking-wider">LIVE · EUR/USD</div>
                <div className="text-xs text-white/40 mt-0.5">Powered by TradingView</div>
              </div>
              <span className="px-2 py-1 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">DEMO ONLY</span>
            </div>
            <div ref={widgetRef} className="tradingview-widget-container rounded-xl overflow-hidden" />
          </div>
        </Reveal>
      </div>
    </section>
  );
}
