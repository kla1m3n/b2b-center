import { Button, Group, Text } from "@mantine/core";
import { useClipboard } from "@mantine/hooks";
import { useState } from "react";
import { REPORTS_AVAILABLE, downloadJustification } from "../api";
import { saveText } from "../download";
import type { ClassificationResult } from "../types";

/** Готовое обоснование для закупочной документации или служебной записки: текст можно скопировать
 *  или скачать (.txt — сразу из браузера, Word — формирует backend). */
export function JustificationBlock({ result }: { result: ClassificationResult }) {
  const clipboard = useClipboard({ timeout: 2000 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!result.justification) return null;

  const onWord = async () => {
    setBusy(true);
    setError(null);
    try {
      await downloadJustification(result.input);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <Group justify="space-between" mb={6} gap="xs">
        <Text size="sm" fw={600}>Обоснование для документации</Text>
        <Group gap={6} className="no-print">
          <Button size="compact-sm" variant="light" onClick={() => clipboard.copy(result.justification)}>
            {clipboard.copied ? "Скопировано ✓" : "Скопировать текст"}
          </Button>
          <Button size="compact-sm" variant="default" onClick={() => saveText(result.justification, "pp1875-obosnovanie.txt")}>
            Скачать .txt
          </Button>
          {REPORTS_AVAILABLE && (
            <Button size="compact-sm" variant="default" loading={busy} onClick={onWord}>Скачать Word</Button>
          )}
        </Group>
      </Group>
      <pre className="justification" data-testid="justification">{result.justification}</pre>
      {error && <Text size="xs" c="red" mt={4}>{error}</Text>}
    </div>
  );
}
