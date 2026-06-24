'use client';
import { Linkedin, Twitter, Instagram, Youtube, Mail } from 'lucide-react';
import { BRAND } from '@/lib/brand';

export default function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="relative pt-20 pb-10 border-t border-white/5 bg-navy-950/60 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-6 md:px-10 lg:px-16">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-10 mb-12">
          {/* Brand */}
          <div className="col-span-2">
            <div className="flex items-center gap-2 mb-4">
              <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-gold-300 to-gold-700 flex items-center justify-center">
                <svg viewBox="0 0 24 24" className="w-5 h-5 text-navy-900"><path fill="currentColor" d="M3 18l6-6 4 4 8-8v4h2V4h-8v2h4l-6 6-4-4-8 8z"/></svg>
              </div>
              <span className="font-display font-bold text-lg">My Funding <span className="gold-text">Bank</span></span>
            </div>
            <p className="text-white/60 text-sm leading-relaxed mb-5 max-w-sm">
              India’s premium fintech super-app. Wealth, forex, travel and AI advisory—one elegant platform.
            </p>
            <div className="flex gap-3">
              {[
                { Icon: Twitter, href: BRAND.social.twitter, label: 'Twitter' },
                { Icon: Linkedin, href: BRAND.social.linkedin, label: 'LinkedIn' },
                { Icon: Instagram, href: BRAND.social.instagram, label: 'Instagram' },
                { Icon: Youtube, href: BRAND.social.youtube, label: 'YouTube' },
                { Icon: Mail, href: `mailto:${BRAND.contact.email}`, label: 'Email' },
              ].map(s => (
                <a key={s.label} href={s.href} aria-label={s.label} target="_blank" rel="noreferrer"
                  className="w-9 h-9 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center hover:border-gold-500/40 hover:bg-gold-500/10 transition">
                  <s.Icon className="w-4 h-4 text-white/70" />
                </a>
              ))}
            </div>
          </div>

          {/* Columns */}
          <FCol title="Product" items={[
            { label: 'Invest', href: '#invest' },
            { label: 'Forex (Demo)', href: '#forex' },
            { label: 'Travel', href: '#travel' },
            { label: 'AI Advisor', href: '#ai' },
            { label: 'Calculator', href: '#calculator' },
          ]} />
          <FCol title="Company" items={[
            { label: 'About', href: '#about' },
            { label: 'Vision & Mission', href: '#vision' },
            { label: 'Security', href: '#security' },
            { label: 'Contact', href: '#contact' },
            { label: 'Careers', href: '#contact' },
          ]} />
          <FCol title="Legal" items={[
            { label: 'Privacy Policy', href: '/privacy/' },
            { label: 'Terms & Conditions', href: '/terms/' },
            { label: 'Risk Disclosure', href: '/terms/#risk' },
            { label: 'Grievance Redressal', href: '/terms/#grievance' },
          ]} />
        </div>

        <div className="pt-8 border-t border-white/5 flex flex-col md:flex-row gap-4 items-center justify-between text-xs text-white/40">
          <div>
            © {year} My Funding Bank Private Limited. All rights reserved.
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-2 items-center">
            <span>CIN: U65999MH2024PTC012345</span>
            <span>•</span>
            <span>GSTIN: 27AAACM0000A1Z5</span>
            <span>•</span>
            <span>SEBI Reg: INZ0000123456 (planned)</span>
          </div>
        </div>
        <p className="text-[10px] text-white/30 mt-6 text-center max-w-4xl mx-auto leading-relaxed">
          Disclaimer: Investments in securities are subject to market risks. Read all scheme-related documents carefully before investing. Forex products on this platform are currently offered in <strong className="text-gold-500/70">demo / paper-trading mode only</strong>. Past performance is not indicative of future returns. Figures and testimonials on this page are illustrative.
        </p>
      </div>
    </footer>
  );
}

function FCol({ title, items }: { title: string; items: { label: string; href: string }[] }) {
  return (
    <div>
      <h4 className="font-display font-bold mb-4 text-gold-400">{title}</h4>
      <ul className="space-y-2">
        {items.map(it => (
          <li key={it.label}>
            <a href={it.href} className="text-sm text-white/60 hover:text-white transition">{it.label}</a>
          </li>
        ))}
      </ul>
    </div>
  );
}
