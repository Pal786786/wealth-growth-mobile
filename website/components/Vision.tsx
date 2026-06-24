'use client';
import Reveal from './Reveal';
import { Compass, Flag } from 'lucide-react';

export default function Vision() {
  return (
    <section id="vision" className="relative section-pad">
      <div className="max-w-7xl mx-auto grid md:grid-cols-2 gap-6">
        <Reveal>
          <div className="glass p-8 md:p-10 h-full relative overflow-hidden">
            <div className="absolute -top-12 -right-12 w-64 h-64 bg-sky-500/10 blur-3xl rounded-full" />
            <Compass className="w-10 h-10 text-sky-400 mb-5" />
            <div className="eyebrow mb-2">Our Vision</div>
            <h3 className="font-display text-2xl md:text-3xl font-bold mb-4">Democratising premium finance for <span className="gold-text">a billion Indians.</span></h3>
            <p className="text-white/70 leading-relaxed">
              We believe wealth-building shouldn’t be reserved for the elite. Our vision is to put the same tools used by family offices and HNIs into every Indian’s pocket—elegantly, transparently, and at near-zero cost.
            </p>
          </div>
        </Reveal>
        <Reveal delay={0.1}>
          <div className="glass-gold p-8 md:p-10 h-full relative overflow-hidden">
            <div className="absolute -bottom-12 -left-12 w-64 h-64 bg-gold-500/10 blur-3xl rounded-full" />
            <Flag className="w-10 h-10 text-gold-400 mb-5" />
            <div className="eyebrow mb-2">Our Mission</div>
            <h3 className="font-display text-2xl md:text-3xl font-bold mb-4">Build the <span className="gold-text">most-loved</span> fintech experience in Asia.</h3>
            <p className="text-white/70 leading-relaxed">
              Obsess over craft. Move at startup speed with the discipline of a bank. Ship products that customers recommend without being asked. Be the reason a 22-year-old starts their first SIP—and the reason a 52-year-old finally feels in control of their wealth.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
