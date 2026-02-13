import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: "#0A0A0B", card: "#141416", hover: "#1C1C1F" },
        border: { DEFAULT: "#27272A", light: "#3F3F46" },
        accent: { DEFAULT: "#10B981", hover: "#059669" },
        warning: "#F59E0B",
        danger: "#EF4444",
        text: { DEFAULT: "#FAFAFA", muted: "#A1A1AA", dim: "#71717A" },
      },
      fontFamily: {
        mono: ["var(--font-jetbrains-mono)", "monospace"],
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "zoom-in": {
          from: { opacity: "0", transform: "scale(0.98)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        "fade-in": "fade-in 180ms ease-out",
        "zoom-in": "zoom-in 180ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
