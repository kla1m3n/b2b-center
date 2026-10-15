import "@mantine/core/styles.css";
import "./app.css";
import { MantineProvider } from "@mantine/core";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { cssResolver, theme } from "./theme";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* Как и ЕИС — только светлая тема */}
    <MantineProvider theme={theme} cssVariablesResolver={cssResolver} forceColorScheme="light">
      <App />
    </MantineProvider>
  </StrictMode>,
);
