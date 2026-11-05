import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

import { colors, fontSize, fonts, radius, shadows, spacing, zIndex } from "./src/design/tokens";

const zIndexScale = Object.fromEntries(Object.entries(zIndex).map(([k, v]) => [k, String(v)]));
const fontSizeScale = Object.fromEntries(
  Object.entries(fontSize).map(([k, [size, lineHeight]]) => [k, [size, { lineHeight }]]),
) as Record<string, [string, { lineHeight: string }]>;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: [...fonts.sans], mono: [...fonts.mono] },
      fontSize: fontSizeScale,
      colors: {
        neutral: colors.neutral,
        accent: { ...colors.accent, DEFAULT: colors.accent[600], foreground: colors.white },
        teal: colors.teal,
        status: {
          grey: colors.status.grey,
          blue: colors.status.blue,
          amber: colors.status.amber,
          green: colors.status.green,
          red: colors.status.red,
        },
        border: colors.neutral[200],
        input: colors.neutral[300],
        ring: colors.accent[600],
        background: colors.white,
        foreground: colors.neutral[900],
        primary: { DEFAULT: colors.accent[600], foreground: colors.white },
        secondary: { DEFAULT: colors.neutral[50], foreground: colors.neutral[800] },
        destructive: { DEFAULT: "#D92D20", foreground: colors.white },
        muted: { DEFAULT: colors.neutral[100], foreground: colors.neutral[600] },
        card: { DEFAULT: colors.white, foreground: colors.neutral[900] },
        popover: { DEFAULT: colors.white, foreground: colors.neutral[900] },
        sidebar: colors.neutral[50],
      },
      borderRadius: { sm: radius.sm, md: radius.md, lg: radius.lg },
      boxShadow: { xs: shadows.xs, sm: shadows.sm, md: shadows.md, focus: shadows.focus },
      spacing: { sidebar: spacing.sidebar, "sidebar-collapsed": spacing.sidebarCollapsed, topbar: spacing.topbar, row: spacing.tableRow },
      zIndex: zIndexScale,
      keyframes: {
        shimmer: { "0%": { backgroundPosition: "-400px 0" }, "100%": { backgroundPosition: "400px 0" } },
      },
      animation: { shimmer: "shimmer 1.4s ease-in-out infinite" },
    },
  },
  plugins: [animate],
} satisfies Config;
