/**
 * Tailwind build config for the four pages that use it.
 *
 * These pages used to pull https://cdn.tailwindcss.com at runtime, which
 * compiles CSS in the browser on every load. Tailwind's own docs say that
 * script is not for production, and it showed: a flash of unstyled content on
 * every visit, on the employee phones that are the slowest devices we serve,
 * and nothing at all when a corporate network blocks the CDN - which is
 * exactly the network most of our employees are on.
 *
 * The generated file is committed rather than built at deploy time, because
 * the Dockerfile copies frontend/ as-is and has no Node in it. Rebuild with
 * `npm run build:css` after changing classes on these pages; the test suite
 * fails if the committed CSS is out of date, so this cannot be forgotten
 * quietly.
 *
 * Pinned to Tailwind 3 deliberately: the CDN served 3, these pages were built
 * against 3, and 4 renames enough that it would change how they look.
 */
module.exports = {
  // Scanned as plain text, so class names assembled in JS string
  // concatenation are still found - every one of them is a complete literal.
  content: [
    'frontend/employee-dashboard.html',
    'frontend/employee-login.html',
    'frontend/meeting.html',
    'frontend/reset-password.html',
  ],
  darkMode: 'class',          // meeting.html toggles dark by class
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', 'sans-serif'] },
      colors: {
        brand: {
          50:'#eef2ff',100:'#e0e7ff',200:'#c7d2fe',300:'#a5b4fc',400:'#818cf8',
          500:'#6366f1',600:'#4f46e5',700:'#4338ca',800:'#3730a3',900:'#312e81',
        },
        dark: { 700:'#334155',800:'#1e293b',900:'#0f172a',950:'#020617' },
        // meeting.html only
        gray: { 750:'#2d3748', 850:'#1a202c', 950:'#0d1117' },
      },
    },
  },
  plugins: [],
};
