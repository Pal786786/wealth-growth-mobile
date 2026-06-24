'use client';
import Reveal from './Reveal';
import { motion } from 'framer-motion';
import { Bot, Brain, Lightbulb, Target } from 'lucide-react';

const CAPS = [
  { icon: Brain, title: 'Portfolio Analysis', desc: 'Risk-adjusted returns, concentration warnings, sector tilt.' },
  { icon: Target, title: 'Goal Planning', desc: 'House, child education, retirement — modeled in seconds.' },
  { icon: Lightbulb, title: 'Smart Suggestions', desc: 'Tax-loss harvesting, rebalance signals, opportunity alerts.' },
  { icon: Bot, title: 'Conversational', desc: '“How much for 2 Cr in 15 years?” — answered, instantly.' },
];

export default function AIAdvisor() {
  return (
    <section id="ai" className="relative section-pad">
      <div className="absolute inset-0 bg-gradient-to-b from-sky-500/5 via-transparent to-transparent pointer-events-none" />
      <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-12 items-center">
        <Reveal>
          <div className="eyebrow mb-3">AI Financial Advisor</div>
          <h2 className="heading-lg mb-6">Your personal CFO, <span className="gold-text">always on.</span></h2>
          <p className="text-white/70 leading-relaxed mb-8">
            Powered by GPT-5.2 + proprietary risk models, our AI advisor analyses your portfolio 24/7, flags risks, plans goals, and suggests next-best actions in plain English—free for every user.
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            {CAPS.map(c => (
              <div key={c.title} className="glass p-4">
                <c.icon className="w-5 h-5 text-sky-400 mb-2" />
                <div className="font-semibold mb-1">{c.title}</div>
                <div className="text-xs text-white/60">{c.desc}</div>
              </div>
            ))}
          </div>
        </Reveal>

        <Reveal delay={0.15}>
          <motion.div initial={{ rotate: -2 }} animate={{ rotate: [-2, 2, -2] }} transition={{ duration: 8, repeat: Infinity }}
            className="glass p-6 max-w-md mx-auto relative">
            <div className="flex items-center gap-3 pb-4 border-b border-white/10">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-sky-500 to-sky-700 flex items-center justify-center shadow-glow-sky">
                <Bot className="w-5 h-5 text-white" />
              </div>
              <div>
                <div className="font-bold">MFB Advisor AI</div>
                <div className="text-xs text-emerald-400 flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Online · GPT-5.2</div>
              </div>
            </div>
            <div className="space-y-3 pt-4 text-sm">
              <div className="flex justify-end">
                <div className="bg-sky-500/15 border border-sky-400/30 rounded-2xl rounded-tr-sm px-4 py-2 max-w-[80%]">How much SIP for ₹1 Cr in 15 years?</div>
              </div>
              <div className="flex justify-start">
                <div className="bg-white/5 border border-white/10 rounded-2xl rounded-tl-sm px-4 py-3 max-w-[85%]">
                  <p className="mb-2">At <span className="text-gold-400 font-semibold">12% CAGR</span>, you’ll need <span className="text-gold-400 font-semibold">₹20,000/month</span> SIP for 15 years.</p>
                  <p className="text-xs text-white/60">Suggested allocation: 60% equity MFs, 25% gold, 15% debt. Want me to build a goal plan?</p>
                </div>
              </div>
              <div className="flex justify-end">
                <div className="bg-sky-500/15 border border-sky-400/30 rounded-2xl rounded-tr-sm px-4 py-2 max-w-[80%]">Yes, please.</div>
              </div>
              <div className="flex items-center gap-2 pt-2">
                <span className="w-2 h-2 bg-sky-400 rounded-full animate-pulse" />
                <span className="w-2 h-2 bg-sky-400 rounded-full animate-pulse" style={{ animationDelay: '0.2s' }} />
                <span className="w-2 h-2 bg-sky-400 rounded-full animate-pulse" style={{ animationDelay: '0.4s' }} />
                <span className="text-xs text-white/40 ml-1">Building your plan…</span>
              </div>
            </div>
          </motion.div>
        </Reveal>
      </div>
    </section>
  );
}
