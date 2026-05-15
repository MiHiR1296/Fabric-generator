/**
 * Tailwind config — Phase 2e (Putting It Together).
 *
 * Added to support the ported yarnseamless editors which use Tailwind utility
 * classes. preflight is OFF so the existing tryon design system in
 * src/styles/index.css (2,400+ lines, navy/gold dark theme) is not disturbed.
 *
 * If a future component needs Tailwind's element resets, flip preflight: true
 * and audit the existing layout — but expect breakage in the wizard chrome.
 */
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './studio.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  /* `important: true` — makes every Tailwind utility !important, which is
   * the only reliable way to win the cascade against tryon's existing
   * `.fabric-shell input/select/textarea` rules (0,1,1) AND our own scoped
   * preflight at `.ys-step <element>` (0,1,1). With !important, Tailwind
   * utilities at (0,1,0) win the cascade regardless of specificity.
   *
   * Safety: tryon's custom design system uses class names like `.card`,
   * `.fabric-step-card`, `.button` — none of which are Tailwind utility
   * names. So Tailwind only emits utilities for the classes USED in
   * `.ys-step` editors. !important on those utilities can't accidentally
   * override tryon's design since tryon doesn't use any Tailwind-named
   * classes anywhere.
   *
   * (Originally tried `important: '.ys-step'` thinking it added the scope
   * prefix AND !important. It only adds the prefix — name is misleading.) */
  important: true,
  corePlugins: {
    // Don't reset element defaults — tryon owns those globally in index.css.
    preflight: false,
  },
  theme: {
    extend: {},
  },
  plugins: [],
};
