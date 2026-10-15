import { createTheme, type CSSVariablesResolver, type MantineColorsTuple } from "@mantine/core";

// Визуальный стиль — по мотивам zakupki.gov.ru (ЕИС): тендерные специалисты работают там каждый день.
// Цвета взяты из CSS ЕИС: синий #0065dd, текст #334059, фон страницы #eff0f2, рамки #e4e7f2.
export const EIS = {
  blue: "#0065dd",
  blueDark: "#014da8",
  text: "#334059",
  textSecondary: "#6f7c98",
  textMuted: "#909ebb",
  pageBg: "#eff0f2",
  border: "#e4e7f2",
} as const;

// Оттенок 6 (основной у Mantine) = синий ЕИС
const eisBlue: MantineColorsTuple = [
  "#e7f0fc", "#cfe1fa", "#a0c3f4", "#6ea4ee", "#418ae8",
  "#1a76e2", "#0065dd", "#0058c4", "#014da8", "#003d86",
];

export const theme = createTheme({
  primaryColor: "eis",
  colors: { eis: eisBlue },
  fontFamily: "Roboto, -apple-system, 'Segoe UI', Arial, sans-serif",
  headings: { fontFamily: "Roboto, -apple-system, 'Segoe UI', Arial, sans-serif", fontWeight: "500" },
  defaultRadius: 4,
  radius: { xs: "2px", sm: "3px", md: "4px", lg: "5px", xl: "8px" },
  components: {
    Paper: { defaultProps: { radius: "xs", shadow: "none" } },
    Button: { defaultProps: { radius: "sm" } },
  },
});

export const cssResolver: CSSVariablesResolver = () => ({
  variables: {},
  light: {
    "--mantine-color-text": EIS.text,
    "--mantine-color-dimmed": EIS.textSecondary,
    "--mantine-color-default-border": EIS.border,
    "--mantine-color-anchor": EIS.blue,
  },
  dark: {},
});
