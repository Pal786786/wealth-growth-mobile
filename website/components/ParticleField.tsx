'use client';
import { useEffect, useRef } from 'react';

/**
 * Lightweight canvas particle network. ~60 nodes, links if within distance.
 * Pauses on tab hidden + respects prefers-reduced-motion.
 */
export default function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    const reduce = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) return;

    let w = (c.width = c.offsetWidth);
    let h = (c.height = c.offsetHeight);
    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    c.width = w * DPR; c.height = h * DPR;
    ctx.scale(DPR, DPR);

    const N = Math.min(60, Math.floor((w * h) / 25000));
    const dots = Array.from({ length: N }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.25,
      vy: (Math.random() - 0.5) * 0.25,
      r: Math.random() * 1.6 + 0.4,
    }));

    let raf = 0;
    const tick = () => {
      ctx.clearRect(0, 0, w, h);
      for (let i = 0; i < dots.length; i++) {
        const d = dots[i];
        d.x += d.vx; d.y += d.vy;
        if (d.x < 0 || d.x > w) d.vx *= -1;
        if (d.y < 0 || d.y > h) d.vy *= -1;
        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(56,189,248,0.6)';
        ctx.fill();
        for (let j = i + 1; j < dots.length; j++) {
          const e = dots[j];
          const dx = d.x - e.x, dy = d.y - e.y;
          const dist = Math.hypot(dx, dy);
          if (dist < 140) {
            ctx.beginPath();
            ctx.strokeStyle = `rgba(56,189,248,${0.18 * (1 - dist / 140)})`;
            ctx.lineWidth = 0.7;
            ctx.moveTo(d.x, d.y); ctx.lineTo(e.x, e.y);
            ctx.stroke();
          }
        }
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    const onResize = () => {
      w = c.offsetWidth; h = c.offsetHeight;
      c.width = w * DPR; c.height = h * DPR;
      ctx.scale(DPR, DPR);
    };
    window.addEventListener('resize', onResize);
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', onResize); };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none opacity-70" aria-hidden />;
}
