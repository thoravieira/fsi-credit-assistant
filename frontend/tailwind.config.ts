import type { Config } from 'tailwindcss';

export default {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Navy — used inside the customer iPhone mockup only (its own dark shell).
        ink: '#001E2B',
        evergreen: '#023430',
        forest: '#00684A',
        spring: '#00ED64',
        // Modernist system: flat ink-on-paper outside the phone.
        paper: '#f3f2f2',
        surface: '#eae9e9',
        charcoal: '#201e1d',
      },
      fontFamily: {
        sans: ['Archivo', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '0px',
      },
    },
  },
  plugins: [],
} satisfies Config;
