'use client';
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Menu, X, ArrowRight } from 'lucide-react';
import { BRAND } from '@/lib/brand';

const LINKS = [
  { label: 'Invest', href: '#invest' },
  { label: 'Forex', href: '#forex' },
  { label: 'Travel', href: '#travel' },
  { label: 'AI Advisor', href: '#ai' },
  { label: 'Security', href: '#security' },
  { label: 'Contact', href: '#contact' },
];

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  return (
    <motion.nav
      initial={{ y: -32, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className={`fixed top-0 inset-x-0 z-50 transition-all ${scrolled ? 'bg-navy-900/80 backdrop-blur-xl border-b border-white/5' : 'bg-transparent'}`}
    >
      <div className="max-w-7xl mx-auto px-6 md:px-10 lg:px-16 h-16 md:h-20 flex items-center justify-between">
        <a href="#top" className="flex items-center gap-2 group">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-gold-300 to-gold-700 flex items-center justify-center shadow-glow-gold">
            <svg viewBox="0 0 24 24" className="w-5 h-5 text-navy-900"><path fill="currentColor" d="M3 18l6-6 4 4 8-8v4h2V4h-8v2h4l-6 6-4-4-8 8z"/></svg>
          </div>
          <span className="font-display font-bold text-lg tracking-tight">My Funding <span className="gold-text">Bank</span></span>
        </a>
        <div className="hidden lg:flex items-center gap-1">
          {LINKS.map(l => (
            <a key={l.href} href={l.href} className="px-4 py-2 text-sm text-white/70 hover:text-white transition-colors rounded-lg hover:bg-white/5">{l.label}</a>
          ))}
        </div>
        <div className="hidden md:flex items-center gap-3">
          <a href={BRAND.liveLinks.adminPortal} target="_blank" rel="noreferrer" className="text-sm text-white/60 hover:text-gold-400 transition-colors">Admin</a>
          <a href={BRAND.liveLinks.appPortal} target="_blank" rel="noreferrer" className="btn-primary text-sm">
            Open App <ArrowRight className="w-4 h-4" />
          </a>
        </div>
        <button className="lg:hidden text-white" onClick={() => setOpen(!open)} aria-label="Menu">{open ? <X /> : <Menu />}</button>
      </div>
      {open && (
        <div className="lg:hidden border-t border-white/5 bg-navy-900/95 backdrop-blur-xl px-6 py-4 flex flex-col gap-2">
          {LINKS.map(l => (
            <a key={l.href} href={l.href} onClick={() => setOpen(false)} className="py-2 text-white/80">{l.label}</a>
          ))}
          <a href={BRAND.liveLinks.appPortal} target="_blank" rel="noreferrer" className="btn-primary mt-2">Open App</a>
        </div>
      )}
    </motion.nav>
  );
}
