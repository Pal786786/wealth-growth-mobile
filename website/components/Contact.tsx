'use client';
import { useState } from 'react';
import Reveal from './Reveal';
import { Mail, Phone, MapPin, MessageSquare, Send, CheckCircle2 } from 'lucide-react';
import { BRAND } from '@/lib/brand';

export default function Contact() {
  const [sent, setSent] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', message: '' });
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    // Frontend-only demo: log + show success. Wire to backend later.
    if (form.name && form.email && form.message) {
      setSent(true);
      setTimeout(() => { setSent(false); setForm({ name: '', email: '', message: '' }); }, 4000);
    }
  };
  return (
    <section id="contact" className="relative section-pad">
      <div className="max-w-7xl mx-auto grid lg:grid-cols-[1fr_1.2fr] gap-10">
        <Reveal>
          <div className="eyebrow mb-3">Contact & Support</div>
          <h2 className="heading-lg mb-6">Talk to a <span className="gold-text">human.</span></h2>
          <p className="text-white/70 leading-relaxed mb-8">
            From product feedback to fundraising decks—reach us anytime. Average response time: 4 hours.
          </p>
          <div className="space-y-4">
            <a href={`mailto:${BRAND.contact.email}`} className="glass p-5 flex items-center gap-4 hover:border-gold-500/30 transition">
              <div className="w-11 h-11 rounded-xl bg-gold-500/10 border border-gold-500/30 flex items-center justify-center"><Mail className="w-5 h-5 text-gold-400" /></div>
              <div><div className="text-xs text-white/50">Email</div><div className="font-semibold">{BRAND.contact.email}</div></div>
            </a>
            <a href={`tel:${BRAND.contact.phone.replace(/\s/g, '')}`} className="glass p-5 flex items-center gap-4 hover:border-gold-500/30 transition">
              <div className="w-11 h-11 rounded-xl bg-sky-500/10 border border-sky-500/30 flex items-center justify-center"><Phone className="w-5 h-5 text-sky-400" /></div>
              <div><div className="text-xs text-white/50">Phone</div><div className="font-semibold">{BRAND.contact.phone}</div></div>
            </a>
            <div className="glass p-5 flex items-center gap-4">
              <div className="w-11 h-11 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center"><MapPin className="w-5 h-5 text-emerald-400" /></div>
              <div><div className="text-xs text-white/50">Address</div><div className="font-semibold text-sm">{BRAND.contact.address}</div></div>
            </div>
          </div>
        </Reveal>

        <Reveal delay={0.15}>
          <form onSubmit={submit} className="glass p-7 md:p-9 space-y-5">
            <div className="flex items-center gap-3 pb-4 border-b border-white/5">
              <MessageSquare className="w-5 h-5 text-gold-400" />
              <h3 className="font-display text-xl font-bold">Send us a message</h3>
            </div>
            {sent ? (
              <div className="py-10 flex flex-col items-center text-center gap-3">
                <CheckCircle2 className="w-14 h-14 text-emerald-400" />
                <h4 className="text-xl font-bold">Message Received</h4>
                <p className="text-white/60">We’ll get back to you within 4 hours.</p>
              </div>
            ) : (
              <>
                <div>
                  <label className="block text-xs text-white/60 mb-2 tracking-wide">FULL NAME</label>
                  <input value={form.name} onChange={e => setForm({...form, name: e.target.value})} required
                    className="w-full bg-white/5 border border-white/10 focus:border-gold-500/40 rounded-xl px-4 py-3 outline-none transition" placeholder="Priya Mehta" />
                </div>
                <div>
                  <label className="block text-xs text-white/60 mb-2 tracking-wide">EMAIL</label>
                  <input type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} required
                    className="w-full bg-white/5 border border-white/10 focus:border-gold-500/40 rounded-xl px-4 py-3 outline-none transition" placeholder="you@email.com" />
                </div>
                <div>
                  <label className="block text-xs text-white/60 mb-2 tracking-wide">MESSAGE</label>
                  <textarea rows={5} value={form.message} onChange={e => setForm({...form, message: e.target.value})} required
                    className="w-full bg-white/5 border border-white/10 focus:border-gold-500/40 rounded-xl px-4 py-3 outline-none resize-none transition" placeholder="How can we help?" />
                </div>
                <button type="submit" className="btn-primary w-full">
                  <Send className="w-4 h-4" /> Send Message
                </button>
              </>
            )}
          </form>
        </Reveal>
      </div>
    </section>
  );
}
