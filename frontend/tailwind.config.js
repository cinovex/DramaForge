/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#0B0B0D",
          900: "#141416",
          850: "#17171B",
          800: "#1C1C20",
          700: "#232329",
          600: "#2C2C33",
          500: "#3A3A42",
          400: "#55555F",
        },
        violetdim: "#2A2436",
      },
      fontFamily: {
        sans: [
          "Inter",
          "PingFang SC",
          "Microsoft YaHei",
          "system-ui",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
