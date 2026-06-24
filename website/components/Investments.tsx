'use client';
import Reveal from './Reveal';
import { Coins, LineChart, Landmark, PiggyBank, Briefcase, Sparkles } from 'lucide-react';
import { motion } from 'framer-motion';
import { BRAND } from '@/lib/brand';

const PRODUCTS = [
  { icon: LineChart, title: 'Stocks & ETFs', desc: 'NSE & BSE direct access. Zero brokerage on delivery. Live charting.', color: 'from-sky-500/20 to-sky-500/5' },
  { icon: PiggyBank, title: 'Mutual Funds & SIPs', desc: '5,000+ direct MFs. Auto SIP. Goal-based investing.', color: 'from-emerald-500/20 to-emerald-500/5' },
  { icon: Coins, title: 'Digital Gold & Silver', desc: '24K 99.9% pure. Buy from ₹1. Instant liquidity.', color: 'from-gold-500/20 to-gold-500/5' },
  { icon: Landmark, title: 'Fixed Deposits', desc: 'Up to 9.1% p.a. Partner banks & NBFCs. Liquid FDs.', color: 'from-purple-500/20 to-purple-500/5' },
  { icon: Briefcase, title: 'Govt Securities', desc: 'RBI Retail Direct. T-Bills, SDLs, SGBs.', color: 'from-rose-500/20 to-rose-500/5' },
  { icon: Sparkles, title: 'Alternative Assets', desc: 'Curated PMS, AIF & US stocks for HNIs.', color: 'from-cyan-500/20 to-cyan-500/5' },
];

export default function Investments() {
  return (
    <section id="invest" className="relative section-pad">
      <div className="max-w-7xl mx-auto">
        <Reveal>
          <div className="text-center mb-14">
            <div className="eyebrow justify-center mb-3">Investment Platform</div>
            <h2 className="heading-lg max-w-3xl mx-auto">Every asset class. <span className="gold-text">One portfolio.</span></h2>
            <p className="text-white/60 mt-4 max-w-2xl mx-auto">From your first SIP to alternative investments, build a diversified portfolio across stocks, mutual funds, gold, FDs, government securities and more—all in one app.</p>
          </div>
        </Reveal>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {PRODUCTS.map((p, i) => (
            <motion.div key={p.title} initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
              transition={{ delay: i * 0.06, duration: 0.6 }}
              whileHover={{ y: -6 }}
              className="glass p-7 group relative overflow-hidden">
              <div className={`absolute inset-0 bg-gradient-to-br ${p.color} opacity-0 group-hover:opacity-100 transition-opacity`} />
              <div className="relative">
                <div className="w-12 h-12 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center mb-5 group-hover:border-gold-500/40 transition">
                  <p.icon className="w-6 h-6 text-gold-400" />
                </div>
                <h3 className="text-xl font-display font-bold mb-2">{p.title}</h3>
                <p className="text-white/60 text-sm leading-relaxed">{p.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>

        <Reveal delay={0.1}>
          <div className="mt-14 glass p-8 md:p-10 flex flex-col md:flex-row items-center justify-between gap-6">
            <div>
              <h3 className="text-2xl font-display font-bold mb-2">Start investing in 2 minutes</h3>
              <p className="text-white/60">Aadhaar e-KYC · Zero account opening charges · 24x7 support</p>
            </div>
            <a href={BRAND.liveLinks.appPortal} target="_blank" rel="noreferrer" className="btn-primary">Open Free Account</a>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
