'use client';
import { motion } from 'framer-motion';

/**
 * “Investment Bull” brand mark — abstract bull head built from geometric primitives.
 * Animates on hover & in entrance. Pure SVG so it scales to any size and prints crisp.
 */
export default function AnimatedBull({ size = 160, glow = true }: { size?: number; glow?: boolean }) {
  return (
    <motion.svg
      width={size}
      height={size}
      viewBox="0 0 200 200"
      xmlns="http://www.w3.org/2000/svg"
      initial={{ opacity: 0, scale: 0.6, rotate: -8 }}
      animate={{ opacity: 1, scale: 1, rotate: 0 }}
      transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ rotate: 4, scale: 1.05 }}
      style={glow ? { filter: 'drop-shadow(0 0 24px rgba(212,175,55,0.5))' } : {}}
    >
      <defs>
        <linearGradient id="goldGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#F8DE8A" />
          <stop offset="50%" stopColor="#D4AF37" />
          <stop offset="100%" stopColor="#8E700F" />
        </linearGradient>
        <linearGradient id="skyGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#38BDF8" />
          <stop offset="100%" stopColor="#0284C7" />
        </linearGradient>
        <radialGradient id="eyeGrad">
          <stop offset="0%" stopColor="#38BDF8" />
          <stop offset="100%" stopColor="#0A1428" />
        </radialGradient>
      </defs>

      {/* Outer ring */}
      <motion.circle cx="100" cy="100" r="92" fill="none" stroke="url(#goldGrad)" strokeWidth="2" strokeDasharray="4 6"
        animate={{ rotate: 360 }} transition={{ duration: 60, repeat: Infinity, ease: 'linear' }}
        style={{ originX: '100px', originY: '100px' }} />

      {/* Bull horns */}
      <path d="M55,72 Q35,55 38,30 Q55,45 75,68 Z" fill="url(#goldGrad)" />
      <path d="M145,72 Q165,55 162,30 Q145,45 125,68 Z" fill="url(#goldGrad)" />

      {/* Head */}
      <path d="M60,80 Q60,140 100,160 Q140,140 140,80 Q140,60 100,55 Q60,60 60,80 Z"
        fill="url(#skyGrad)" stroke="url(#goldGrad)" strokeWidth="2" />

      {/* Snout */}
      <ellipse cx="100" cy="140" rx="22" ry="16" fill="#0A1428" stroke="url(#goldGrad)" strokeWidth="1.5" />
      <circle cx="92" cy="138" r="2" fill="#D4AF37" />
      <circle cx="108" cy="138" r="2" fill="#D4AF37" />

      {/* Eyes */}
      <motion.circle cx="82" cy="100" r="6" fill="url(#eyeGrad)"
        animate={{ scale: [1, 1.15, 1] }} transition={{ duration: 3, repeat: Infinity }} />
      <motion.circle cx="118" cy="100" r="6" fill="url(#eyeGrad)"
        animate={{ scale: [1, 1.15, 1] }} transition={{ duration: 3, repeat: Infinity, delay: 0.3 }} />

      {/* Nose ring */}
      <circle cx="100" cy="148" r="4" fill="none" stroke="url(#goldGrad)" strokeWidth="1.5" />

      {/* Up-arrow chart line on forehead (bull market) */}
      <motion.polyline points="75,95 90,82 100,88 115,72" fill="none" stroke="#F8DE8A" strokeWidth="2.5"
        strokeLinecap="round" strokeLinejoin="round"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.2, delay: 0.4 }} />
      <motion.polygon points="112,68 118,70 116,76" fill="#F8DE8A"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.4 }} />
    </motion.svg>
  );
}
