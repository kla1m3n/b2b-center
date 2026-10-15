import { MantineProvider } from "@mantine/core";
import { render as rtlRender } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { theme } from "../theme";

function Providers({ children }: { children: ReactNode }) {
  return <MantineProvider theme={theme}>{children}</MantineProvider>;
}

// wrapper, а не обёртка вокруг ui — тогда и rerender получает MantineProvider
export function render(ui: ReactElement) {
  return rtlRender(ui, { wrapper: Providers });
}
