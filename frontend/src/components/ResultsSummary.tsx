import { Badge, Group, UnstyledButton } from "@mantine/core";
import { countResults, type ResultFilter } from "../resultFilters";
import type { ClassificationResult } from "../types";
import { REGIME_COLORS } from "./RegimeBadge";

const ITEMS: { filter: ResultFilter; label: string; color: string }[] = [
  { filter: "all", label: "Все", color: "eis" },
  { filter: "ban", label: "Запрет", color: REGIME_COLORS.ban },
  { filter: "restriction", label: "Ограничение", color: REGIME_COLORS.restriction },
  { filter: "advantage", label: "Преимущество", color: REGIME_COLORS.advantage },
  { filter: "none", label: "Не подпадает", color: REGIME_COLORS.none },
  { filter: "review", label: "⚠ Проверить вручную", color: "orange" },
  { filter: "error", label: "Ошибки", color: "gray" },
];

/** Сводка по пакету и фильтр: клик по счётчику оставляет в таблице только эти строки. */
export function ResultsSummary({ results, value, onChange }: {
  results: ClassificationResult[];
  value: ResultFilter;
  onChange: (f: ResultFilter) => void;
}) {
  const counts = countResults(results);
  return (
    <Group gap={6} role="group" aria-label="Фильтр результатов">
      {ITEMS.filter((it) => it.filter === "all" || counts[it.filter] > 0).map((it) => {
        const active = value === it.filter;
        return (
          <UnstyledButton key={it.filter} onClick={() => onChange(active && it.filter !== "all" ? "all" : it.filter)}
            aria-pressed={active}>
            <Badge size="lg" radius="xs" color={it.color} variant={active ? "filled" : "light"} autoContrast
              style={{ cursor: "pointer", textTransform: "none", fontWeight: 500 }}>
              {it.label}: {counts[it.filter]}
            </Badge>
          </UnstyledButton>
        );
      })}
    </Group>
  );
}
