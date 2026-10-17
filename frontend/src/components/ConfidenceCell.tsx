import { Group, Progress, Text, Tooltip } from "@mantine/core";
import { confidencePct } from "../confidence";

export function confidenceColor(c: number): string {
  if (c >= 0.8) return "teal";
  if (c >= 0.6) return "yellow";
  return "red";
}

export function ConfidenceCell({ value }: { value: number }) {
  const pct = confidencePct(value);
  return (
    <Tooltip label="Насколько система уверена в вердикте по ПП № 1875 (ниже 80% — «Проверьте вручную»)" withArrow>
      <Group gap={6} wrap="nowrap" w={110}>
        <Progress value={pct} color={confidenceColor(value)} size="sm" w={56} aria-hidden />
        <Text size="sm" fw={500}>{pct}%</Text>
      </Group>
    </Tooltip>
  );
}
