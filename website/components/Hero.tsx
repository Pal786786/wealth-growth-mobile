'use client';
import { motion } from 'framer-motion';
import { ArrowRight, Shield, TrendingUp, Sparkles, Smartphone } from 'lucide-react';
import AnimatedBull from './AnimatedBull';
import ParticleField from './ParticleField';
import { BRAND } from '@/lib/brand';

export default function Hero() {
  return (
    <section id="top" className="relative min-h-screen flex items-center pt-24 pb-16 overflow-hidden">
      {/* Background layers */}
      <div className="absolute inset-0 grid-bg" />
      <div className="absolute inset-0 bg-hero-glow" />
      <div className="orb w-[600px] h-[600px] -top-40 -left-40" style={{ background: 'radial-gradient(circle, rgba(56,189,248,0.4), transparent 70%)' }} />
      <div className="orb w-[500px] h-[500px] -bottom-40 -right-20" style={{ background: 'radial-gradient(circle, rgba(212,175,55,0.25), transparent 70%)' }} />
      <ParticleField />

      <div className="relative max-w-7xl mx-auto px-6 md:px-10 lg:px-16 grid lg:grid-cols-[1.1fr_1fr] gap-12 items-center">
        <div>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
            className="eyebrow mb-5">
            <Sparkles className="w-3.5 h-3.5" /> Luxury Fintech Super App · Made in India
          </motion.div>

          <motion.h1 initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.05 }}
            className="heading-xl mb-6">
            Where <span className="gold-text">Wealth</span> Meets <span className="text-sky-400">Intelligence</span>
          </motion.h1>

          <motion.p initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.15 }}
            className="text-lg md:text-xl text-white/70 max-w-xl mb-8 leading-relaxed">
            India’s premium financial super-app for the next generation of investors. Invest, trade forex, book travel, and grow your wealth—guided by AI, secured by bank-grade encryption.
          </motion.p>

          <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.25 }}
            className="flex flex-wrap gap-4 mb-10">
            <a href={BRAND.liveLinks.appPortal} target="_blank" rel="noreferrer" className="btn-primary">
              <Smartphone className="w-5 h-5" /> Open Web App <ArrowRight className="w-5 h-5" />
            </a>
            <a href="#download" className="btn-ghost">Download Android APK</a>
          </motion.div>

          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.8, delay: 0.4 }}
            className="flex flex-wrap items-center gap-x-8 gap-y-4 text-sm text-white/60">
            <div className="flex items-center gap-2"><Shield className="w-4 h-4 text-sky-400" /> ISO 27001 · PCI-DSS</div>
            <div className="flex items-center gap-2"><TrendingUp className="w-4 h-4 text-gold-400" /> ₹500 Cr+ AUM¹</div>
            <div className="flex items-center gap-2"><Sparkles className="w-4 h-4 text-sky-400" /> 50,000+ Users¹</div>
          </motion.div>
        </div>

        {/* Right: Floating preview cards + bull */}
        <div className="relative h-[480px] lg:h-[560px]">
          <div className="absolute inset-0 flex items-center justify-center">
            <AnimatedBull size={320} />
          </div>

          {/* Floating cards */}
          <motion.div animate={{ y: [0, -10, 0] }} transition={{ duration: 5, repeat: Infinity }}
            className="absolute top-6 left-0 glass p-4 w-56">
            <div className="text-xs text-gold-400 font-semibold tracking-wider mb-1">PORTFOLIO</div>
            <div className="text-2xl font-bold">₹12,84,500</div>
            <div className="text-xs text-emerald-400 mt-1">▲ +18.6% YTD</div>
          </motion.div>

          <motion.div animate={{ y: [0, 10, 0] }} transition={{ duration: 5, repeat: Infinity, delay: 1.2 }}
            className="absolute top-32 right-0 glass p-4 w-52">
            <div className="text-xs text-sky-400 font-semibold tracking-wider mb-1">EUR/USD</div>
            <div className="text-xl font-bold flex items-center gap-2">1.0842 <span className="text-emerald-400 text-sm">+0.32%</span></div>
            <svg viewBox="0 0 100 30" className="w-full mt-1 h-8">
              <polyline fill="none" stroke="#34D399" strokeWidth="2" points="0,22 12,18 24,21 36,15 48,17 60,10 72,12 84,7 100,4" />
            </svg>
          </motion.div>

          <motion.div animate={{ y: [0, -8, 0] }} transition={{ duration: 5, repeat: Infinity, delay: 0.6 }}
            className="absolute bottom-12 left-4 glass-gold p-4 w-60">
            <div className="text-xs text-gold-400 font-semibold tracking-wider mb-1">SIP CALCULATOR</div>
            <div className="text-sm text-white/80">₹10,000/mo · 15Y · 12%</div>
            <div className="text-2xl font-bold gold-text mt-1">₹50.4 L</div>
          </motion.div>

          <motion.div animate={{ y: [0, 8, 0] }} transition={{ duration: 5, repeat: Infinity, delay: 1.8 }}
            className="absolute bottom-32 right-4 glass p-4 w-48">
            <div className="text-xs text-sky-400 font-semibold tracking-wider mb-1">AI INSIGHT</div>
            <div className="text-sm text-white">Rebalance suggested: ↑ tech, ↓ commodities</div>
          </motion.div>
        </div>
      </div>

      <p className="absolute bottom-3 left-1/2 -translate-x-1/2 text-[10px] text-white/30">¹ Illustrative figures for demo purposes</p>
    </section>
  );
}
