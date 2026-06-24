'use client';
import Reveal from './Reveal';
import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Calculator as Calc, Sparkles } from 'lucide-react';
import { BRAND } from '@/lib/brand';

function fmt(n: number) { return '₹' + Math.round(n).toLocaleString('en-IN'); }

export default function Calculator() {
  const [monthly, setMonthly] = useState(10000);
  const [years, setYears] = useState(15);
  const [rate, setRate] = useState(12);

  const result = useMemo(() => {
    const r = rate / 100 / 12;
    const n = years * 12;
    const fv = monthly * ((Math.pow(1 + r, n) - 1) / r) * (1 + r);
    const invested = monthly * n;
    return { fv, invested, gain: fv - invested };
  }, [monthly, years, rate]);

  return (
    <section id="calculator" className="relative section-pad">
      <div className="max-w-7xl mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <div className="eyebrow justify-center mb-3"><Calc className="w-3.5 h-3.5" /> Investment Calculator</div>
            <h2 className="heading-lg">See your <span className="gold-text">future wealth</span> in seconds.</h2>
          </div>
        </Reveal>

        <div className="grid lg:grid-cols-[1fr_1.1fr] gap-8">
          <Reveal>
            <div className="glass p-7">
              <div className="space-y-7">
                {[
                  { label: 'Monthly SIP', val: monthly, set: setMonthly, min: 500, max: 200000, step: 500, fmt: (v: number) => fmt(v) },
                  { label: 'Duration (years)', val: years, set: setYears, min: 1, max: 40, step: 1, fmt: (v: number) => `${v} yrs` },
                  { label: 'Expected Return', val: rate, set: setRate, min: 4, max: 20, step: 0.5, fmt: (v: number) => `${v}% p.a.` },
                ].map(f => (
                  <div key={f.label}>
                    <div className="flex justify-between mb-3">
                      <span className="text-sm text-white/70">{f.label}</span>
                      <span className="text-base font-semibold gold-text">{f.fmt(f.val)}</span>
                    </div>
                    <input type="range" min={f.min} max={f.max} step={f.step} value={f.val}
                      onChange={e => f.set(Number(e.target.value))}
                      className="w-full accent-gold-500" />
                  </div>
                ))}
              </div>
            </div>
          </Reveal>

          <Reveal delay={0.15}>
            <motion.div className="glass-gold p-8 h-full flex flex-col justify-between">
              <div>
                <div className="text-xs tracking-widest text-gold-400 font-semibold mb-2">PROJECTED VALUE AFTER {years} YEARS</div>
                <motion.div key={result.fv} initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                  className="text-5xl md:text-6xl font-display font-bold gold-text mb-6">
                  {fmt(result.fv)}
                </motion.div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-white/5 rounded-xl p-4 border border-white/10">
                    <div className="text-xs text-white/50 mb-1">Total Invested</div>
                    <div className="text-xl font-bold text-white">{fmt(result.invested)}</div>
                  </div>
                  <div className="bg-emerald-500/10 rounded-xl p-4 border border-emerald-500/30">
                    <div className="text-xs text-emerald-300/80 mb-1">Wealth Gained</div>
                    <div className="text-xl font-bold text-emerald-400">{fmt(result.gain)}</div>
                  </div>
                </div>
              </div>
              <a href={BRAND.liveLinks.appPortal} target="_blank" rel="noreferrer" className="btn-primary mt-7 w-full">
                <Sparkles className="w-4 h-4" /> Save Plan & Start Investing
              </a>
            </motion.div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
