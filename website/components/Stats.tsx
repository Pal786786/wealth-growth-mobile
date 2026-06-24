'use client';
import { motion, useInView } from 'framer-motion';
import { useRef, useEffect, useState } from 'react';

function Counter({ to, suffix = '', prefix = '', decimals = 0 }: { to: number; suffix?: string; prefix?: string; decimals?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!inView) return;
    let start = 0; const dur = 1600; const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      setVal(start + (to - start) * eased);
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [inView, to]);
  return <span ref={ref}>{prefix}{decimals ? val.toFixed(decimals) : Math.floor(val).toLocaleString('en-IN')}{suffix}</span>;
}

const ITEMS = [
  { label: 'Assets Under Management', value: 500, suffix: ' Cr+', prefix: '₹' },
  { label: 'Active Investors', value: 50_000, suffix: '+' },
  { label: 'Daily Forex Volume', value: 12.4, suffix: 'M+', prefix: '$', decimals: 1 },
  { label: 'Uptime SLA', value: 99.98, suffix: '%', decimals: 2 },
];

export default function Stats() {
  return (
    <section className="relative section-pad">
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
          {ITEMS.map((it, i) => (
            <motion.div key={it.label} initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.6 }} className="glass p-6 md:p-8 text-center">
              <div className="text-3xl md:text-4xl font-display font-bold gold-text mb-2">
                <Counter to={it.value} suffix={it.suffix} prefix={it.prefix} decimals={it.decimals} />
              </div>
              <div className="text-xs md:text-sm text-white/60 tracking-wide">{it.label}</div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
