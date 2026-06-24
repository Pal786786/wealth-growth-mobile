'use client';
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import Reveal from './Reveal';

const FAQS = [
  { q: 'Is My Funding Bank safe? Are my investments protected?',
    a: 'Yes. We are ISO 27001 certified, PCI-DSS Level 1 compliant, and operate under RBI/SEBI guidelines. Customer funds are held in escrow with partner banks. We use AES-256 encryption, biometric auth, and 24x7 fraud monitoring. Your investments in stocks/MFs are held directly in your demat account, not in our books.' },
  { q: 'What does it cost to use My Funding Bank?',
    a: 'Account opening is free. Equity delivery is zero brokerage. Mutual funds are direct (zero commission). Forex paper trading is free with ₹10L virtual capital. We earn a small spread on FX live trades and partnership fees on travel bookings—never hidden charges.' },
  { q: 'Is forex trading live or demo?',
    a: 'Phase 1 (current) is 100% demo / paper trading with realistic simulated price feeds. We are intentionally cautious about live forex while we secure necessary licences. Live FX trading will roll out in Phase 2 to verified KYC users only.' },
  { q: 'How does the AI Financial Advisor work?',
    a: 'It uses GPT-5.2 and our proprietary risk models to analyse your portfolio, goals and risk tolerance. It can answer plain-English questions like “How much SIP for ₹1Cr in 15 years?”, flag concentration risks, suggest tax-loss harvesting, and generate goal-based plans. It is advisory only—the buy/sell decision is always yours.' },
  { q: 'Can I withdraw my money anytime?',
    a: 'Yes. Wallet withdrawals to your linked bank account are instant via IMPS/UPI (24x7). Mutual fund redemptions follow scheme T+1/T+3 norms. Equity sale proceeds settle T+1 as per SEBI rules.' },
  { q: 'Which devices are supported?',
    a: 'Native Android app (live). iOS native app (coming soon). Web portal at app.myfundingbank.com works on any modern browser including iPad Safari and desktop Chrome/Firefox/Edge.' },
  { q: 'How do I get support?',
    a: 'In-app chat (24x7 AI + human escalation), email support@myfundingbank.com (response <4 hrs), phone +91 80 1234 5678 (Mon–Sat 9am–9pm IST). HNIs get a dedicated relationship manager.' },
  { q: 'Will my data be sold or shared?',
    a: 'Never. We do not sell, rent or share personal data with third parties for marketing. We comply with India’s DPDP Act 2023 and global GDPR principles. You can export or delete your data anytime from Settings → Privacy.' },
];

export default function FAQ() {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <section id="faq" className="relative section-pad">
      <div className="max-w-4xl mx-auto">
        <Reveal>
          <div className="text-center mb-12">
            <div className="eyebrow justify-center mb-3">FAQ</div>
            <h2 className="heading-lg">Questions? <span className="gold-text">We have answers.</span></h2>
          </div>
        </Reveal>
        <div className="space-y-3">
          {FAQS.map((f, i) => (
            <Reveal key={i} delay={i * 0.04}>
              <div className={`glass overflow-hidden transition-all ${open === i ? 'border-gold-500/30' : ''}`}>
                <button onClick={() => setOpen(open === i ? null : i)}
                  className="w-full px-6 py-5 flex items-center justify-between gap-4 text-left">
                  <span className="font-semibold text-base md:text-lg">{f.q}</span>
                  <motion.span animate={{ rotate: open === i ? 180 : 0 }} className="shrink-0 text-gold-400">
                    <ChevronDown className="w-5 h-5" />
                  </motion.span>
                </button>
                <AnimatePresence initial={false}>
                  {open === i && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.3 }}>
                      <p className="px-6 pb-5 text-white/70 leading-relaxed">{f.a}</p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
