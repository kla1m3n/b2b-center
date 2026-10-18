import { Anchor, Badge, Box, Group, Stack, Text, UnstyledButton } from "@mantine/core";
import type { ClassificationResult } from "../types";
import { ConfidenceCell } from "./ConfidenceCell";
import { NotInAppendices } from "./NotInAppendices";
import { REGIME_COLORS, RegimeBadge } from "./RegimeBadge";
import { ResultDetails } from "./ResultDetails";

interface Props {
  results: ClassificationResult[];
  expanded: Set<number>;
  onToggle: (i: number) => void;
  onOpenItem: (id: number) => void;
}

/** Результаты на телефоне: карточки как записи реестра в ЕИС — режим сверху, затем товар, код и пункт ПП. */
export function ResultCards({ results, expanded, onToggle, onOpenItem }: Props) {
  return (
    <Stack gap="sm">
      {results.map((r, i) => {
        const top = r.npa_matches[0];
        const isOpen = expanded.has(i);
        const stripe = r.error ? "var(--mantine-color-red-6)" : `var(--mantine-color-${REGIME_COLORS[r.verdict]}-6)`;
        return (
          <Box key={i} className="result-card" style={{ borderLeftColor: stripe }} data-testid="result-card">
            {r.error ? (
              <>
                <Text fw={500}>{r.input}</Text>
                <Text size="sm" c="red" mt={4}>{r.error}</Text>
              </>
            ) : (
              <>
                <Group justify="space-between" wrap="nowrap" gap="xs">
                  <RegimeBadge regime={r.verdict} size="sm" />
                  <ConfidenceCell value={r.confidence} />
                </Group>

                <Text fw={500} mt={8} lh={1.35}>{r.input}</Text>
                {r.needs_review && (
                  <Badge color="orange" variant="light" size="sm" mt={6}>⚠ Проверьте вручную</Badge>
                )}

                <div className="result-card__field">
                  <Text className="caps-label" c="dimmed">Код ОКПД2</Text>
                  <Text size="sm"><Text span ff="monospace">{r.okpd2?.code}</Text> — {r.okpd2?.title}</Text>
                </div>

                <div className="result-card__field">
                  <Text className="caps-label" c="dimmed">Пункт ПП № 1875</Text>
                  {top ? (
                    <Text size="sm">
                      {top.item_id !== null ? (
                        <Anchor component="button" type="button" size="sm" onClick={() => onOpenItem(top.item_id!)}>
                          Прил. {top.appendix}, п. {top.item_no}
                        </Anchor>
                      ) : (
                        <>Прил. {top.appendix}, п. {top.item_no}</>
                      )}
                      {r.npa_matches.length > 1 && <Text span c="dimmed"> и ещё {r.npa_matches.length - 1}</Text>}
                    </Text>
                  ) : (
                    <NotInAppendices url={r.npa_source_url} />
                  )}
                </div>

                <UnstyledButton className="result-card__toggle" onClick={() => onToggle(i)} aria-expanded={isOpen}>
                  {isOpen ? "Скрыть подробности ▴" : "Подробнее ▾"}
                </UnstyledButton>
                {isOpen && (
                  <Box mx={-12}>
                    <ResultDetails result={r} onOpenItem={onOpenItem} />
                  </Box>
                )}
              </>
            )}
          </Box>
        );
      })}
    </Stack>
  );
}
