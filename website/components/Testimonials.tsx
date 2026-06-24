'use client';
import Reveal from './Reveal';
import { Star, Quote } from 'lucide-react';

const TESTIMONIALS = [
  { name: 'Priya Mehta', role: 'CA, Mumbai', rating: 5,
    quote: 'The AI Advisor flagged my over-exposure to one sector — saved me from a 12% drawdown. This isn’t just an app, it’s a junior analyst in my pocket.' },
  { name: 'Arjun Kapoor', role: 'Founder, B2B SaaS', rating: 5,
    quote: 'I moved my entire ₹2Cr portfolio here. The dashboards rival what Kotak Wealth showed me—at 1/100th the cost.' },
  { name: 'Sneha R.', role: 'Doctor, Bangalore', rating: 5,
    quote: 'Booking flights and earning 5% wallet cashback that funds my SIPs? Genius. It’s travel × investing.' },
  { name: 'Vikram Singh', role: 'Trader, Delhi', rating: 5,
    quote: 'Best paper-trading sandbox I’ve used. The fills feel real. Onboarded my whole team for training.' },
  { name: 'Rohit Iyer', role: 'CTO, Logistics co.', rating: 5,
    quote: 'Bank-grade security, biometric login, and dark mode — nobody else in India does this trio this well.' },
  { name: 'Anjali Verma', role: 'Architect, Pune', rating: 5,
    quote: 'My favourite part? The honesty. They say “demo” when it’s demo. Trust earned.' },
];

export default function Testimonials() {
  return (
    <section id="testimonials" className="relative section-pad">
      <div className="max-w-7xl mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <div className="eyebrow justify-center mb-3">Testimonials</div>
            <h2 className="heading-lg">Loved by <span className="gold-text">India’s sharpest</span> investors.</h2>
          </div>
        </Reveal>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {TESTIMONIALS.map((t, i) => (
            <Reveal key={t.name} delay={i * 0.05}>
              <div className="glass p-6 h-full flex flex-col">
                <Quote className="w-7 h-7 text-gold-500/40 mb-3" />
                <p className="text-white/80 leading-relaxed flex-1">“{t.quote}”</p>
                <div className="mt-5 pt-5 border-t border-white/5 flex items-center gap-3">
                  <div className="w-11 h-11 rounded-full bg-gradient-to-br from-sky-500 to-navy-700 flex items-center justify-center text-sm font-bold">
                    {t.name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                  </div>
                  <div className="flex-1">
                    <div className="font-semibold text-sm">{t.name}</div>
                    <div className="text-xs text-white/50">{t.role}</div>
                  </div>
                  <div className="flex gap-0.5">
                    {Array.from({ length: t.rating }).map((_, j) => (
                      <Star key={j} className="w-3.5 h-3.5 fill-gold-400 text-gold-400" />
                    ))}
                  </div>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
