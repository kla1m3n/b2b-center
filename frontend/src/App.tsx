import { Alert, Badge, Box, Container, Group, Tabs, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { getHealth, USE_MOCKS } from "./api";
import { CheckPage } from "./pages/CheckPage";
import { NpaPage } from "./pages/NpaPage";
import type { HealthOut } from "./types";

function useHealth() {
  const [health, setHealth] = useState<HealthOut | null>(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const h = await getHealth();
        if (stop) return;
        setHealth(h);
        setOffline(false);
        if (h.status !== "ok") timer = setTimeout(poll, 3000); // модели прогреваются — ждём
      } catch {
        if (stop) return;
        setOffline(true);
        timer = setTimeout(poll, 5000);
      }
    };
    poll();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, []);
  return { health, offline };
}

function Logo() {
  return (
    <Group gap={12} wrap="nowrap">
      <div className="logo-mark" aria-hidden>
        {Array.from({ length: 16 }, (_, i) => <span key={i} />)}
      </div>
      <div className="logo-text">
        ПП № 1875<br />Классификатор
      </div>
    </Group>
  );
}

export function App() {
  const { health, offline } = useHealth();
  const [tab, setTab] = useState<string | null>("check");

  return (
    <Tabs value={tab} onChange={setTab} className="nav-tabs">
      <Box className="topbar">
        <Container size="lg" py={10}>
          <Group justify="space-between" wrap="nowrap" gap="xs">
            <Text size="xs" c="dimmed" truncate>
              Проверка товаров на национальный режим в закупках по 44-ФЗ и 223-ФЗ
            </Text>
            <Group gap="xs" wrap="nowrap">
              {health?.npa_version && (
                <Text size="xs" c="dimmed" visibleFrom="md" truncate maw={360}>
                  База: <Text span inherit c="eis.6">{health.npa_version}</Text>
                </Text>
              )}
              {USE_MOCKS && (
                <Badge color="grape" variant="light" radius="xs" style={{ flexShrink: 0, overflow: "visible" }}>демо</Badge>
              )}
            </Group>
          </Group>
        </Container>
      </Box>

      <Box className="header">
        <Container size="lg" py={22}>
          <Logo />
        </Container>
      </Box>

      <Box className="nav">
        <Container size="lg">
          <Tabs.List>
            <Tabs.Tab value="check">Проверка товаров</Tabs.Tab>
            <Tabs.Tab value="npa">База НПА</Tabs.Tab>
          </Tabs.List>
        </Container>
      </Box>

      <Box className="page-content">
        <Container size="lg" py={36}>
          {offline && (
            <Alert color="red" mb="md" title="Сервер недоступен">Проверьте подключение — повторяем попытку автоматически.</Alert>
          )}
          {health?.status === "starting" && (
            <Alert color="eis" mb="md" title="Система запускается">Загружаются модели, обычно это занимает около минуты.</Alert>
          )}
          <Tabs.Panel value="check"><CheckPage /></Tabs.Panel>
          <Tabs.Panel value="npa"><NpaPage uploadProtected={health?.npa_upload_protected ?? false} /></Tabs.Panel>
        </Container>
      </Box>
    </Tabs>
  );
}
