/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        track: {
          darkest: '#070b14',
          card: '#0d1527',
          panel: '#111c34',
          border: '#1f2d4d',
          accent: '#06b6d4',
          accentBlue: '#3b82f6',
        }
      }
    },
  },
  plugins: [],
}
