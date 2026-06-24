'use client';
import Reveal from './Reveal';
import { Smartphone, QrCode, CheckCircle2 } from 'lucide-react';
import { BRAND } from '@/lib/brand';

const PERKS = [
  'Biometric login & PIN',
  'Real-time portfolio tracking',
  'Push alerts for big moves',
  'Offline mode for SIPs',
  'Dark mode by default',
];

export default function AppDownload() {
  return (
    <section id="download" className="relative section-pad">
      <div className="max-w-7xl mx-auto">
        <div className="glass-gold p-8 md:p-12 lg:p-16 relative overflow-hidden">
          <div className="absolute -top-32 -right-32 w-96 h-96 bg-gold-500/20 rounded-full blur-3xl" />
          <div className="absolute -bottom-32 -left-32 w-96 h-96 bg-sky-500/20 rounded-full blur-3xl" />

          <div className="relative grid lg:grid-cols-2 gap-12 items-center">
            <Reveal>
              <div className="eyebrow mb-3">Mobile App</div>
              <h2 className="heading-lg mb-6">Your wealth, <span className="gold-text">in your pocket.</span></h2>
              <p className="text-white/70 leading-relaxed mb-8">
                Native iOS & Android apps. Bank-grade security. Designed by ex-Apple & ex-Razorpay designers. The fastest fintech experience in India.
              </p>
              <ul className="grid sm:grid-cols-2 gap-2 mb-8">
                {PERKS.map(p => (
                  <li key={p} className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-gold-400 shrink-0" /> {p}
                  </li>
                ))}
              </ul>
              <div className="flex flex-wrap gap-4">
                <a href={BRAND.liveLinks.apkDownload} target="_blank" rel="noreferrer" className="btn-primary">
                  <Smartphone className="w-5 h-5" /> Download Android APK
                </a>
                <button disabled className="btn-ghost opacity-50 cursor-not-allowed" aria-disabled>
                  iOS · Coming Soon
                </button>
              </div>
            </Reveal>

            <Reveal delay={0.15}>
              <div className="relative flex justify-center">
                <img src={BRAND.images.mobile} alt="My Funding Bank App" className="w-80 max-w-full rounded-3xl border border-white/15 shadow-2xl" />
                <div className="absolute -right-4 top-12 glass p-4 w-40">
                  <div className="flex items-center gap-2 mb-2">
                    <QrCode className="w-4 h-4 text-gold-400" />
                    <span className="text-xs font-semibold">Scan to Install</span>
                  </div>
                  <div className="aspect-square bg-white rounded-lg p-2 flex items-center justify-center">
                    <svg viewBox="0 0 100 100" className="w-full h-full">
                      {Array.from({ length: 81 }).map((_, i) => (
                        <rect key={i} x={(i % 9) * 11 + 1} y={Math.floor(i / 9) * 11 + 1} width="9" height="9"
                          fill={Math.random() > 0.5 ? '#0A1428' : '#fff'} />
                      ))}
                      <rect x="1" y="1" width="29" height="29" fill="#0A1428" />
                      <rect x="7" y="7" width="17" height="17" fill="#fff" />
                      <rect x="11" y="11" width="9" height="9" fill="#0A1428" />
                    </svg>
                  </div>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}
