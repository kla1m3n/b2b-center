import { ActionIcon, Anchor, Group, Paper, Stack, Text } from "@mantine/core";
import type { HistoryEntry } from "../history";
import { countResults } from "../resultFilters";

const fmt = (iso: string) => new Date(iso).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });

function summary(e: HistoryEntry): string {
  const c = countResults(e.results);
  const parts = [
    c.ban && `запрет ${c.ban}`,
    c.restriction && `огранич. ${c.restriction}`,
    c.advantage && `преим. ${c.advantage}`,
    c.none && `не подпадает ${c.none}`,
    c.review && `⚠ ${c.review}`,
  ].filter(Boolean);
  return parts.join(" · ");
}

export function HistoryList({ entries, onOpen, onRemove, onClear }: {
  entries: HistoryEntry[];
  onOpen: (e: HistoryEntry) => void;
  onRemove: (id: string) => void;
  onClear: () => void;
}) {
  if (entries.length === 0) return null;
  return (
    <Paper p="lg">
      <Group justify="space-between" mb="xs">
        <Text className="caps-label" c="dimmed">Последние проверки</Text>
        <Anchor component="button" type="button" size="sm" c="dimmed" onClick={onClear}>Очистить историю</Anchor>
      </Group>
      <Stack gap={6}>
        {entries.map((e) => (
          <Group key={e.id} justify="space-between" wrap="nowrap" gap="xs">
            <div style={{ minWidth: 0 }}>
              <Anchor component="button" type="button" size="sm" onClick={() => onOpen(e)} style={{ textAlign: "left" }}>
                {fmt(e.at)} — {e.source}
              </Anchor>
              <Text size="xs" c="dimmed" truncate>{summary(e)}</Text>
            </div>
            <ActionIcon variant="subtle" color="gray" aria-label="Удалить из истории" onClick={() => onRemove(e.id)}>×</ActionIcon>
          </Group>
        ))}
      </Stack>
      <Text size="xs" c="dimmed" mt="xs">Хранится только в этом браузере.</Text>
    </Paper>
  );
}
