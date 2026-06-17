export function Logo({ size = 40 }: { size?: number }) {
  return (
    <div
      className="rounded-xl bg-gradient-to-br from-brand-navy via-slate-800 to-brand-secondary flex items-center justify-center shadow-glow"
      style={{ width: size, height: size }}
    >
      <svg width={size * 0.7} height={size * 0.7} viewBox="0 0 120 120" fill="none">
        <defs>
          <linearGradient id="bbody" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#7DD3FC" />
            <stop offset="100%" stopColor="#0EA5E9" />
          </linearGradient>
          <linearGradient id="bgold" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#FCD34D" />
            <stop offset="100%" stopColor="#F59E0B" />
          </linearGradient>
        </defs>
        <path d="M22 38 C 14 28, 18 16, 30 14 C 38 14, 44 22, 46 32 C 38 30, 28 32, 22 38 Z" fill="#fff" stroke="#0F172A" strokeWidth="1.4" />
        <path d="M98 38 C 106 28, 102 16, 90 14 C 82 14, 76 22, 74 32 C 82 30, 92 32, 98 38 Z" fill="#fff" stroke="#0F172A" strokeWidth="1.4" />
        <circle cx="22" cy="36" r="3" fill="url(#bgold)" />
        <circle cx="98" cy="36" r="3" fill="url(#bgold)" />
        <path d="M32 40 C 36 32, 44 26, 54 26 L 66 26 C 76 26, 84 32, 88 40 L 92 56 C 92 64, 88 70, 82 74 L 78 84 C 76 90, 70 94, 60 94 C 50 94, 44 90, 42 84 L 38 74 C 32 70, 28 64, 28 56 Z" fill="url(#bbody)" stroke="#0F172A" strokeWidth="1.8" />
        <circle cx="46" cy="56" r="2.6" fill="#0F172A" />
        <circle cx="74" cy="56" r="2.6" fill="#0F172A" />
        <path d="M48 76 C 48 70, 72 70, 72 76 L 70 84 C 70 88, 64 90, 60 90 C 56 90, 50 88, 50 84 Z" fill="#0F172A" />
        <circle cx="60" cy="83" r="2.8" fill="none" stroke="#FCD34D" strokeWidth="1.4" />
        <polyline points="24,108 36,100 46,104 56,92 66,96 78,82 92,86" stroke="#10B981" strokeWidth="3.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M92 86 L 104 76 L 102 92 Z" fill="url(#bgold)" />
      </svg>
    </div>
  );
}
