'use client';
import Reveal from './Reveal';
import { Shield, Lock, Eye, FileCheck2, KeyRound, ServerCog } from 'lucide-react';

const PILLARS = [
  { icon: Lock, title: 'AES-256 Encryption', desc: 'At-rest and in-transit. TLS 1.3 everywhere.' },
  { icon: KeyRound, title: 'Multi-Factor Auth', desc: 'OTP · Biometric · Hardware-key support.' },
  { icon: ServerCog, title: 'SOC 2 Type II', desc: 'Annual audit. Independent attestation.' },
  { icon: Eye, title: 'Zero-Knowledge Logs', desc: 'PII never logged. Anonymized analytics only.' },
  { icon: FileCheck2, title: 'RBI · SEBI Compliant', desc: 'Full KYC/AML. Regular regulatory filings.' },
  { icon: Shield, title: '24x7 Fraud Engine', desc: 'ML-based anomaly detection on every transaction.' },
];

export default function Security() {
  return (
    <section id="security" className="relative section-pad bg-gradient-to-b from-transparent via-navy-900/40 to-transparent">
      <div className="max-w-7xl mx-auto">
        <Reveal>
          <div className="text-center mb-14">
            <div className="eyebrow justify-center mb-3">Security & Compliance</div>
            <h2 className="heading-lg max-w-3xl mx-auto">Built like a <span className="gold-text">private bank.</span></h2>
            <p className="text-white/60 mt-4 max-w-2xl mx-auto">Every ₹1 you trust us with is protected by the same security stack used by Tier-1 global banks. We obsess over compliance so you don’t have to.</p>
          </div>
        </Reveal>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {PILLARS.map((p, i) => (
            <Reveal key={p.title} delay={i * 0.05}>
              <div className="glass p-6 h-full hover:border-gold-500/30 transition">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-sky-500/20 to-sky-500/5 border border-sky-500/30 flex items-center justify-center mb-4">
                  <p.icon className="w-6 h-6 text-sky-400" />
                </div>
                <h3 className="font-display text-lg font-bold mb-2">{p.title}</h3>
                <p className="text-white/60 text-sm">{p.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.1}>
          <div className="mt-14 flex flex-wrap items-center justify-center gap-6 md:gap-10 opacity-80">
            {['ISO 27001', 'PCI-DSS', 'SOC 2 Type II', 'GDPR Ready', 'RBI', 'SEBI'].map(b => (
              <div key={b} className="text-xs font-semibold tracking-widest text-white/40 border border-white/10 rounded-md px-3 py-1.5">{b}</div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}
