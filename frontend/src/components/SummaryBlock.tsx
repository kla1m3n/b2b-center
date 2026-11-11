import { Alert, Box, Button, Group, Progress, Stack, Text, Tooltip } from "@mantine/core";
import type { ReactNode } from "react";
import { confidencePct } from "../confidence";
import type { ResultFilter } from "../resultFilters";
import { sharePct, summarize } from "../summary";
import type { ClassificationResult } from "../types";
import { REGIME_COLORS, RegimeBadge } from "./RegimeBadge";
import { ResultsSummary } from "./ResultsSummary";

const plural = (n: number) =>
  n % 10 === 1 && n % 100 !== 11 ? "позиция" : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? "позиции" : "позиций";

/** Блок-сводка над таблицей: доли по режимам, позиции для ручной проверки и с наименьшей уверенностью.
 *  Отвечает на вопрос специалиста «что в этом списке и на что смотреть в первую очередь». */
export function SummaryBlock({ results, filter, onFilter, actions }: {
  results: ClassificationResult[];
  filter: ResultFilter;
  onFilter: (f: ResultFilter) => void;
  actions?: ReactNode;
}) {
  const s = summarize(results);
  const toCheck = s.needs_review + s.errors;
  const reviewOnly = filter === "review";
  return (
    <Stack gap="sm" data-testid="summary-block">
      <Group justify="space-between" align="flex-start" gap="sm">
        <div>
          <Text fw={600} size="lg">Сводка по списку</Text>
          <Text size="sm" c="dimmed">{s.total} {plural(s.total)} · режим по ПП № 1875</Text>
        </div>
        {actions}
      </Group>

      <Progress.Root size={22} radius="xs" aria-label="Доли позиций по режимам">
        {s.by_regime.filter((x) => x.count > 0).map((x) => (
          <Tooltip key={x.regime} label={`${x.label}: ${x.count} (${sharePct(x.share)})`} withArrow>
            <Progress.Section value={x.share * 100} color={REGIME_COLORS[x.regime]}>
              {x.share >= 0.08 && <Progress.Label style={{ color: x.regime === "restriction" ? "#000" : undefined }}>{sharePct(x.share)}</Progress.Label>}
            </Progress.Section>
          </Tooltip>
        ))}
        {s.errors > 0 && (
          <Tooltip label={`Не распознано: ${s.errors}`} withArrow>
            <Progress.Section value={(s.errors / s.total) * 100} color="gray" />
          </Tooltip>
        )}
      </Progress.Root>

      <ResultsSummary results={results} value={filter} onChange={onFilter} />

      {toCheck > 0 ? (
        <Alert color="orange" variant="light" py="xs" title={`Требуют ручной проверки: ${toCheck} из ${s.total} (${sharePct(toCheck / s.total)})`}>
          <Group justify="space-between" gap="xs">
            <Text size="sm">
              Уверенность ниже 80%{s.errors > 0 ? " или наименование не распознано" : ""} — проверьте код ОКПД2 до включения в документацию.
            </Text>
            {s.needs_review > 0 && (
              <Button size="compact-sm" variant={reviewOnly ? "filled" : "light"} color="orange"
                onClick={() => onFilter(reviewOnly ? "all" : "review")}>
                {reviewOnly ? "Показать все" : "Показать только их"}
              </Button>
            )}
          </Group>
        </Alert>
      ) : (
        <Alert color="teal" variant="light" py="xs">Все позиции определены уверенно — ручная проверка не требуется.</Alert>
      )}

      {s.lowest_confidence.length > 0 && (
        <Box>
          <Text size="sm" fw={600} mb={4}>Наименьшая уверенность</Text>
          <Stack gap={4}>
            {s.lowest_confidence.map((x) => (
              <Group key={x.idx} gap="xs" wrap="nowrap" data-testid="lowest-item">
                <Text size="sm" c="dimmed" w={34} ta="right" style={{ flexShrink: 0 }}>№ {x.idx}</Text>
                <Text size="sm" fw={500} w={42} style={{ flexShrink: 0 }}>{confidencePct(x.confidence)}%</Text>
                <RegimeBadge regime={x.verdict} size="sm" />
                <Text size="sm" truncate title={x.input}>{x.input}</Text>
              </Group>
            ))}
          </Stack>
        </Box>
      )}
    </Stack>
  );
}
