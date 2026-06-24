'use client';
import Reveal from './Reveal';
import { Plane, Train, Bus, Hotel } from 'lucide-react';
import { BRAND } from '@/lib/brand';

const MODES = [
  { icon: Plane, label: 'Flights', tag: 'Domestic & International' },
  { icon: Train, label: 'Trains', tag: 'Tatkal · Premium Tatkal' },
  { icon: Bus, label: 'Buses', tag: '50,000+ routes' },
  { icon: Hotel, label: 'Hotels', tag: '5-star luxury · budget' },
];

export default function Travel() {
  return (
    <section id="travel" className="relative section-pad">
      <div className="max-w-7xl mx-auto grid lg:grid-cols-[1fr_1.1fr] gap-12 items-center">
        <Reveal>
          <div className="relative">
            <div className="absolute -inset-2 rounded-3xl bg-gradient-to-br from-gold-500/15 to-sky-500/10 blur-2xl" />
            <img src={BRAND.images.travel} alt="Luxury travel" className="relative rounded-3xl border border-white/10 w-full object-cover h-[500px]" />
            <div className="absolute top-6 left-6 glass p-3 px-4">
              <div className="text-[10px] text-gold-400 tracking-widest font-semibold">BLR → DXB</div>
              <div className="text-lg font-bold">₹42,500 <span className="text-emerald-400 text-xs ml-1">5% cashback</span></div>
            </div>
          </div>
        </Reveal>
        <Reveal delay={0.15}>
          <div className="eyebrow mb-3">Travel Booking</div>
          <h2 className="heading-lg mb-6">Book it. <span className="gold-text">Earn it.</span> Travel like it.</h2>
          <p className="text-white/70 leading-relaxed mb-8">
            Flights, trains, hotels and buses—all in one place, all rewarded. Every booking earns wallet cashback + reward points redeemable for upgrades, lounge access and free travel.
          </p>
          <div className="grid grid-cols-2 gap-4 mb-8">
            {MODES.map(m => (
              <div key={m.label} className="glass p-4 flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gold-500/10 border border-gold-500/20 flex items-center justify-center">
                  <m.icon className="w-5 h-5 text-gold-400" />
                </div>
                <div>
                  <div className="font-semibold">{m.label}</div>
                  <div className="text-xs text-white/50">{m.tag}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="glass-gold p-5 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold mb-1">Premium Cashback</div>
              <div className="text-xs text-white/60">Up to 5% wallet credit on every booking</div>
            </div>
            <div className="text-2xl font-display gold-text font-bold">5%</div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
