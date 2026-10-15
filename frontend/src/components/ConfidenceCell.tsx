import { Group, Progress, Text, Tooltip } from "@mantine/core";

export function confidenceColor(c: number): string {
  if (c >= 0.8) return "teal";
  if (c >= 0.6) return "yellow";
  return "red";
}

export function ConfidenceCell({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <Tooltip label="Насколько система уверена, что код ОКПД2 выбран верно" withArrow>
      <Group gap={6} wrap="nowrap" w={110}>
        <Progress value={pct} color={confidenceColor(value)} size="sm" w={56} aria-hidden />
        <Text size="sm" fw={500}>{pct}%</Text>
      </Group>
    </Tooltip>
  );
}
