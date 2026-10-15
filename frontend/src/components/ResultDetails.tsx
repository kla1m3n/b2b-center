import { Anchor, Badge, Group, List, Stack, Text } from "@mantine/core";
import type { ClassificationResult } from "../types";
import { RegimeBadge } from "./RegimeBadge";

export function ResultDetails({ result, onOpenItem }: { result: ClassificationResult; onOpenItem: (id: number) => void }) {
  return (
    <Stack gap="sm" p="sm">
      {result.explanation && <Text size="sm">{result.explanation}</Text>}

      <div>
        <Text size="sm" fw={600} mb={4}>Пункты ПП № 1875</Text>
        {result.npa_matches.length === 0 ? (
          <Text size="sm" c="dimmed">
            Код не входит в приложения 1–3 — запретов и ограничений нет, действует преимущество для российских товаров на общих основаниях.
          </Text>
        ) : (
          <Stack gap={6}>
            {result.npa_matches.map((m) => (
              <Group key={`${m.appendix}-${m.item_no}`} gap="xs" wrap="nowrap" align="flex-start">
                <RegimeBadge regime={m.regime} size="sm" />
                <div>
                  {m.item_id !== null ? (
                    <Anchor component="button" type="button" size="sm" onClick={() => onOpenItem(m.item_id!)}>
                      Прил. {m.appendix}, п. {m.item_no}
                    </Anchor>
                  ) : (
                    <Text size="sm" span>Прил. {m.appendix}, п. {m.item_no}</Text>
                  )}
                  <Text size="sm" span> — {m.title}</Text>
                  <Group gap={6} mt={2}>
                    <Text size="xs" c="dimmed">по коду {m.matched_code}</Text>
                    {m.quota !== null && <Badge size="xs" variant="light">мин. доля {m.quota}%</Badge>}
                    {m.has_conditions && (
                      <Badge size="xs" variant="light" color="orange">есть доп. условия — проверьте текст пункта</Badge>
                    )}
                  </Group>
                  {m.note && <Text size="xs" c="dimmed">{m.note}</Text>}
                </div>
              </Group>
            ))}
          </Stack>
        )}
      </div>

      {result.alternatives.length > 0 && (
        <div>
          <Text size="sm" fw={600} mb={4}>Другие возможные коды ОКПД2</Text>
          <List size="sm" spacing={2}>
            {result.alternatives.map((a) => (
              <List.Item key={a.code}>
                {a.code} — {a.title} <Text span c="dimmed">({Math.round(a.confidence * 100)}%)</Text>
              </List.Item>
            ))}
          </List>
        </div>
      )}
    </Stack>
  );
}
