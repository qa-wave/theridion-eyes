/** @type {import('tailwindcss').Config} */

function withOpacity(varName) {
  return `rgb(var(${varName}) / <alpha-value>)`;
}

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "neutral-925": "#161618",
        // Dynamic cobweb palette — driven by CSS variables so themes
        // can swap the entire accent spine by changing --accent-* vars.
        cobweb: {
          50:  withOpacity("--accent-50"),
          100: withOpacity("--accent-100"),
          200: withOpacity("--accent-200"),
          300: withOpacity("--accent-300"),
          400: withOpacity("--accent-400"),
          500: withOpacity("--accent-500"),
          600: withOpacity("--accent-600"),
          700: withOpacity("--accent-700"),
          800: withOpacity("--accent-800"),
          900: withOpacity("--accent-900"),
          950: withOpacity("--accent-950"),
        },
      },
      fontFamily: {
        sans: [
          '"Inter"',
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "system-ui",
          "sans-serif",
        ],
        mono: [
          '"JetBrains Mono"',
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      borderRadius: {
        'xl': '12px',
        '2xl': '16px',
        '3xl': '20px',
      },
      backdropBlur: {
        'xl': '24px',
        '2xl': '40px',
      },
      boxShadow: {
        glow: "0 0 20px -4px rgb(var(--accent-glow) / 0.25)",
        "glow-sm": "0 0 10px -2px rgb(var(--accent-glow) / 0.2)",
        "glow-emerald": "0 0 20px -4px rgb(var(--accent-glow) / 0.25)",
        "inner-glow": "inset 0 1px 0 0 rgba(255,255,255,0.03)",
      },
      backgroundImage: {
        "mesh-gradient":
          "radial-gradient(at 20% 80%, var(--mesh-a) 0%, transparent 50%), radial-gradient(at 80% 20%, var(--mesh-b) 0%, transparent 50%)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "slide-in": "slideIn 0.2s ease-out",
        "fade-in": "fadeIn 0.15s ease-out",
      },
      keyframes: {
        slideIn: {
          "0%": { opacity: "0", transform: "translateY(-4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};
