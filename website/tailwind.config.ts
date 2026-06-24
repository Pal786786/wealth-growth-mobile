import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Brand
        navy: { 50:'#E8EEF7', 100:'#C5D0E5', 400:'#3F5680', 500:'#1F3461', 600:'#152547', 700:'#0F1B36', 800:'#0A1428', 900:'#070E1C', 950:'#040813' },
        sky: { 400:'#38BDF8', 500:'#0EA5E9', 600:'#0284C7' },
        gold: { 100:'#FCEFC7', 200:'#F8DE8A', 300:'#F0CC5C', 400:'#E8C547', 500:'#D4AF37', 600:'#B8941F', 700:'#8E700F' },
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
        display: ['var(--font-playfair)', 'serif'],
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
        'gold-shine': 'linear-gradient(120deg, #D4AF37 0%, #F8DE8A 25%, #D4AF37 50%, #B8941F 75%, #D4AF37 100%)',
        'hero-glow': 'radial-gradient(ellipse 80% 50% at 50% -20%, rgba(56,189,248,0.25), transparent 70%)',
      },
      animation: {
        'fade-up': 'fadeUp 0.8s ease-out forwards',
        'float': 'float 6s ease-in-out infinite',
        'shimmer': 'shimmer 3s linear infinite',
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'ticker': 'ticker 40s linear infinite',
      },
      keyframes: {
        fadeUp: { '0%': { opacity: '0', transform: 'translateY(20px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        float: { '0%, 100%': { transform: 'translateY(0px)' }, '50%': { transform: 'translateY(-12px)' } },
        shimmer: { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
        ticker: { '0%': { transform: 'translateX(0)' }, '100%': { transform: 'translateX(-50%)' } },
      },
      boxShadow: {
        'glow-sky': '0 0 40px rgba(56,189,248,0.35)',
        'glow-gold': '0 0 40px rgba(212,175,55,0.45)',
        'glass': '0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.08)',
      },
    },
  },
  plugins: [],
};

export default config;
