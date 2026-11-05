/**
 * FabTrack design tokens. Single source for the Tailwind theme (tailwind.config.ts)
 * and for the few places that need raw values in TypeScript (charts, canvas).
 * Colours meet WCAG AA for text on their paired backgrounds.
 */

export const colors = {
  white: "#FFFFFF",
  neutral: {
    25: "#FCFCFD",
    50: "#F8F9FB",
    100: "#F1F3F6",
    200: "#E6E8EC",
    300: "#D0D5DD",
    400: "#98A2B3",
    500: "#667085",
    600: "#475467",
    700: "#344054",
    800: "#1D2939",
    900: "#101828",
  },
  accent: {
    50: "#EEF3FE",
    100: "#DCE6FD",
    200: "#B9CCFB",
    300: "#8AA8F6",
    400: "#5A83EE",
    500: "#3A66E5",
    600: "#1F4FD8",
    700: "#1A41B3",
    800: "#17378F",
  },
  teal: {
    50: "#E7F7F6",
    100: "#C5ECEA",
    200: "#8FD9D5",
    500: "#13B5AF",
    600: "#0E9F9A",
    700: "#0B7F7B",
    800: "#0A625F",
  },
  status: {
    grey: { fg: "#475467", bg: "#F1F3F6", border: "#D0D5DD", dot: "#98A2B3" },
    blue: { fg: "#1A41B3", bg: "#EEF3FE", border: "#B9CCFB", dot: "#1F4FD8" },
    amber: { fg: "#93370D", bg: "#FFFAEB", border: "#FEDF89", dot: "#F79009" },
    green: { fg: "#067647", bg: "#ECFDF3", border: "#ABEFC6", dot: "#17B26A" },
    red: { fg: "#B42318", bg: "#FEF3F2", border: "#FECDCA", dot: "#F04438" },
  },
} as const;

export type StatusTone = keyof typeof colors.status;

export const radius = { sm: "6px", md: "8px", lg: "12px", full: "9999px" } as const;

export const shadows = {
  xs: "0 1px 2px rgba(16,24,40,.04)",
  sm: "0 1px 2px rgba(16,24,40,.04), 0 4px 12px rgba(16,24,40,.04)",
  md: "0 2px 4px rgba(16,24,40,.05), 0 12px 24px rgba(16,24,40,.07)",
  focus: "0 0 0 3px rgba(31,79,216,.20)",
} as const;

/** [font-size, line-height] pairs. Base UI text is 14px; dense tables use 13px. */
export const fontSize = {
  "2xs": ["11px", "16px"],
  xs: ["12px", "16px"],
  sm: ["13px", "20px"],
  base: ["14px", "22px"],
  md: ["15px", "24px"],
  lg: ["18px", "28px"],
  xl: ["20px", "30px"],
  "2xl": ["24px", "32px"],
  "3xl": ["30px", "38px"],
} as const;

/** 4px base spacing (Tailwind's default scale is kept; these are named layout steps). */
export const spacing = {
  gutter: "24px",
  sidebar: "240px",
  sidebarCollapsed: "64px",
  topbar: "56px",
  tableRow: "36px",
} as const;

export const zIndex = {
  base: 0,
  sticky: 10,
  sidebar: 20,
  dropdown: 30,
  overlay: 40,
  modal: 50,
  toast: 60,
  tooltip: 70,
} as const;

export const fonts = {
  sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
  mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
} as const;
