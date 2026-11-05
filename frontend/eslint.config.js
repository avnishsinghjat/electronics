import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage", "playwright-report", "test-results", "node_modules"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.strict],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2022, globals: { ...globals.browser, ...globals.node } },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "no-restricted-syntax": [
        "error",
        {
          selector: "Literal[value=/^https?:\\/\\/(?!localhost|127\\.0\\.0\\.1|www\\.w3\\.org\\/2000\\/svg)/]",
          message: "Offline-first: no absolute external URLs in source (CLAUDE.md rule 1).",
        },
      ],
    },
  },
  {
    // Library and wiring modules export variants/constants next to components; the rule
    // only affects dev-server hot reload, not correctness.
    files: ["src/**"],
    rules: { "react-refresh/only-export-components": "off" },
  },
  {
    // TanStack Table/Virtual return non-memoisable functions; we do not use the React Compiler.
    files: ["src/design/components/data-table/**", "src/features/boq/BoqGrid.tsx"],
    rules: { "react-hooks/incompatible-library": "off" },
  },
  {
    files: ["tests/**", "e2e/**"],
    rules: { "no-restricted-syntax": "off", "@typescript-eslint/no-non-null-assertion": "off" },
  },
  {
    // Playwright fixtures call `use()`, which is not a React hook.
    files: ["e2e/**"],
    rules: { "react-hooks/rules-of-hooks": "off" },
  },
);
