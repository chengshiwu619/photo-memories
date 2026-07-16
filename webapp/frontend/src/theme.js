import { alpha, createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#d7ff64", contrastText: "#11150b" },
    secondary: { main: "#f0b7ff" },
    background: { default: "#0a0c0b", paper: "#121513" },
    text: { primary: "#f3f5ef", secondary: "#9ca49c" },
    divider: "rgba(255,255,255,.09)",
  },
  typography: {
    fontFamily: '"Segoe UI Variable", "Microsoft YaHei UI", system-ui, sans-serif',
    h1: { fontSize: "clamp(2.3rem, 5vw, 5.4rem)", lineHeight: 0.98, fontWeight: 660, letterSpacing: "-.055em" },
    h2: { fontSize: "clamp(1.65rem, 3vw, 2.9rem)", lineHeight: 1.05, fontWeight: 650, letterSpacing: "-.04em" },
    h3: { fontSize: "1.3rem", fontWeight: 650, letterSpacing: "-.025em" },
    button: { textTransform: "none", fontWeight: 650, letterSpacing: "-.01em" },
  },
  shape: { borderRadius: 16 },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { minHeight: 42, borderRadius: 999, paddingInline: 18 } },
    },
    MuiIconButton: {
      styleOverrides: { root: { border: "1px solid rgba(255,255,255,.1)" } },
    },
    MuiChip: {
      styleOverrides: { root: { borderRadius: 999, background: alpha("#ffffff", 0.055) } },
    },
    MuiPaper: {
      styleOverrides: { root: { backgroundImage: "none" } },
    },
    MuiTooltip: {
      styleOverrides: { tooltip: { fontSize: 12, borderRadius: 8 } },
    },
  },
});
