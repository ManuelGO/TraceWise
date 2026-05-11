/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{html,ts}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#1976d2',
        secondary: '#ff4081',
        success: '#4caf50',
        warning: '#ff9800',
        error: '#f44336',
      },
    },
  },
  plugins: [],
  darkMode: 'class',
}
