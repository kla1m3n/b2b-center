import { Alert, Anchor, Badge, Group, Stack, Table, Text } from "@mantine/core";
import { confidencePct } from "../confidence";
import type { Alternative, ClassificationResult } from "../types";
import { JustificationBlock } from "./JustificationBlock";
import { REGIME_COLORS, RegimeBadge } from "./RegimeBadge";

/** Пункт ПП альтернативного кода: первый (главный по режиму) — ссылкой на текст пункта, остальные — числом. */
function AlternativeItems({ alt, onOpenItem }: { alt: Alternative; onOpenItem: (id: number) => void }) {
  const top = alt.npa_matches[0];
  if (!top) return <Text size="sm" c="dimmed">не входит в прил. 1–3</Text>;
  const label = `Прил. ${top.appendix}, п. ${top.item_no}`;
  return (
    <>
      {top.item_id !== null ? (
        <Anchor component="button" type="button" size="sm" onClick={() => onOpenItem(top.item_id!)}>{label}</Anchor>
      ) : (
        <Text size="sm" span>{label}</Text>
      )}
      {alt.npa_matches.length > 1 && <Text size="xs" c="dimmed">и ещё {alt.npa_matches.length - 1}</Text>}
    </>
  );
}

export function ResultDetails({ result, onOpenItem }: { result: ClassificationResult; onOpenItem: (id: number) => void }) {
  const otherRegime = result.alternatives.some((a) => a.regime_differs);
  return (
    <Stack gap="sm" p="sm">
      {result.recommendation && (
        <Alert variant="light" py="xs" title="Что делать" data-testid="recommendation"
          color={result.needs_review ? "orange" : REGIME_COLORS[result.verdict]}>
          {result.recommendation}
        </Alert>
      )}

      {result.explanation && <Text size="sm">{result.explanation}</Text>}

      <div>
        <Text size="sm" fw={600} mb={4}>Пункты ПП № 1875</Text>
        {result.npa_matches.length === 0 ? (
          <Text size="sm" c="dimmed">
            Код не входит в приложения 1–3 — запретов и ограничений нет, действует преимущество для российских товаров на общих основаниях.{" "}
            {result.npa_source_url && (
              <Anchor href={result.npa_source_url} target="_blank" rel="noreferrer" size="sm">Текст постановления</Anchor>
            )}
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
          <Text size="sm" fw={600}>Другие возможные коды ОКПД2 и их режим</Text>
          <Text size="xs" c={otherRegime ? "orange.8" : "dimmed"} mb={4}>
            {otherRegime
              ? "Внимание: при другом коде режим будет другим — убедитесь, что выбранный код точнее описывает товар."
              : "При любом из этих кодов режим тот же, что у выбранного."}
          </Text>
          <Table.ScrollContainer minWidth={560}>
            <Table verticalSpacing={6} withTableBorder data-testid="alternatives">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Код ОКПД2</Table.Th>
                  <Table.Th>Режим</Table.Th>
                  <Table.Th style={{ whiteSpace: "nowrap" }}>Пункт ПП</Table.Th>
                  <Table.Th>Уверенность</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {result.alternatives.map((a) => (
                  <Table.Tr key={a.code}>
                    <Table.Td>
                      <Text size="sm" ff="monospace">{a.code}</Text>
                      <Text size="xs" c="dimmed">{a.title}</Text>
                    </Table.Td>
                    <Table.Td>
                      <RegimeBadge regime={a.verdict} size="sm" />
                      {a.regime_differs && (
                        <Badge size="xs" variant="light" color="orange" mt={4} display="block" w="fit-content">режим другой</Badge>
                      )}
                    </Table.Td>
                    <Table.Td style={{ whiteSpace: "nowrap" }}><AlternativeItems alt={a} onOpenItem={onOpenItem} /></Table.Td>
                    <Table.Td><Text size="sm">{confidencePct(a.confidence)}%</Text></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </div>
      )}

      <JustificationBlock result={result} />
    </Stack>
  );
}
