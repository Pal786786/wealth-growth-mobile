'use client';
import Reveal from './Reveal';
import { Award, Building2, Globe2, ShieldCheck } from 'lucide-react';

const HIGHLIGHTS = [
  { icon: Building2, label: 'RBI-aligned' },
  { icon: ShieldCheck, label: 'SEBI Compliant' },
  { icon: Award, label: 'ISO 27001 Certified' },
  { icon: Globe2, label: 'Global Reach' },
];

export default function About() {
  return (
    <section id="about" className="relative section-pad">
      <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-12 items-center">
        <Reveal>
          <div className="eyebrow mb-4">About My Funding Bank</div>
          <h2 className="heading-lg mb-6">A new <span className="gold-text">standard</span> for premium fintech in India.</h2>
          <p className="text-white/70 text-lg leading-relaxed mb-6">
            My Funding Bank is a next-generation financial super-app engineered for India’s emerging affluent class. We unify wealth management, forex trading, travel concierge and AI-driven advisory into one elegant experience—trusted by tens of thousands of investors.
          </p>
          <p className="text-white/60 leading-relaxed mb-8">
            Built by veterans from JP Morgan, Razorpay and Groww, we obsess over three things: regulatory rigor, design craft, and outcomes that compound. Whether you’re investing your first ₹1,000 SIP or rebalancing a 10-crore portfolio, the platform adapts to you.
          </p>
          <div className="grid grid-cols-2 gap-3">
            {HIGHLIGHTS.map(h => (
              <div key={h.label} className="glass flex items-center gap-3 px-4 py-3">
                <h.icon className="w-5 h-5 text-gold-400" />
                <span className="text-sm font-medium">{h.label}</span>
              </div>
            ))}
          </div>
        </Reveal>

        <Reveal delay={0.15}>
          <div className="relative">
            <div className="absolute -inset-2 rounded-3xl bg-gradient-to-br from-sky-500/10 to-gold-500/10 blur-2xl" />
            <img src="https://images.pexels.com/photos/8159115/pexels-photo-8159115.jpeg" alt="Global finance network" className="relative rounded-3xl border border-white/10 shadow-2xl w-full object-cover h-[520px]" />
            <div className="absolute bottom-6 left-6 right-6 glass p-5">
              <div className="text-xs text-gold-400 font-semibold tracking-wider mb-1">FOUNDED</div>
              <div className="text-2xl font-display font-bold">2024 • Mumbai, India</div>
              <div className="text-sm text-white/60 mt-2">Backed by leading fintech investors. Operating across IN · SG · AE.</div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
