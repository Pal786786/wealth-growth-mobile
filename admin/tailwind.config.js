/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "#38BDF8",
          secondary: "#0EA5E9",
          navy: "#0F172A",
          accent: "#7DD3FC",
        },
      },
      fontFamily: {
        sans: ['"Inter"', '"SF Pro Display"', "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 8px 32px rgba(56,189,248,0.18)",
      },
    },
  },
  plugins: [],
};
