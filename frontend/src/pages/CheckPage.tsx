import { Alert, Button, FileButton, Group, Paper, Progress, Stack, Text, Textarea, Title } from "@mantine/core";
import { useRef, useState } from "react";
import { classify, classifyBatch, classifyFile, getJob, jobExportUrl } from "../api";
import { ResultsTable } from "../components/ResultsTable";
import { downloadCsv } from "../exportCsv";
import type { ClassificationResult } from "../types";

const LIMIT = 100;
const EXAMPLES = ["Ноутбук Lenovo IdeaPad 15", "Бумага офисная А4", "Щебень гранитный", "Хлеб пшеничный (батон)", "Лифт пассажирский"];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function CheckPage() {
  const [text, setText] = useState("");
  const [results, setResults] = useState<ClassificationResult[] | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const runId = useRef(0);

  const names = text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);

  async function waitJob(id: string, run: number) {
    setJobId(id);
    for (;;) {
      const job = await getJob(id);
      if (run !== runId.current) return; // пользователь запустил новую проверку
      setProgress({ done: job.done, total: job.total });
      if (job.status === "done") {
        setResults(job.results ?? []);
        return;
      }
      if (job.status === "failed") throw new Error("Не удалось обработать список. Попробуйте ещё раз.");
      await sleep(1000);
    }
  }

  async function run(action: (run: number) => Promise<void>) {
    const run = ++runId.current;
    setBusy(true);
    setError(null);
    setResults(null);
    setProgress(null);
    setJobId(null);
    try {
      await action(run);
    } catch (e) {
      if (run === runId.current) setError((e as Error).message);
    } finally {
      if (run === runId.current) setBusy(false);
    }
  }

  const onCheck = () =>
    run(async (r) => {
      if (names.length === 1) {
        const res = await classify(names[0]);
        if (r === runId.current) setResults([res]);
      } else {
        const { job_id } = await classifyBatch(names);
        await waitJob(job_id, r);
      }
    });

  const onFile = (file: File | null) => {
    if (!file) return;
    run(async (r) => {
      const { job_id } = await classifyFile(file);
      await waitJob(job_id, r);
    });
  };

  const exportUrl = jobId ? jobExportUrl(jobId) : null;
  const tooMany = names.length > LIMIT;
  const reviewCount = results?.filter((r) => r.needs_review).length ?? 0;

  return (
    <Stack gap="lg">
      <div>
        <Title order={2}>Проверка товаров по ПП № 1875</Title>
        <Text c="dimmed" mt={4}>
          Введите наименования товаров — каждое с новой строки (до {LIMIT}) — или загрузите таблицу Excel/CSV.
          Система подберёт код ОКПД2 и покажет, действует ли запрет, ограничение или преимущество.
        </Text>
      </div>

      <Paper p="lg">
        <Stack gap="sm">
          <Textarea
            label="Наименования товаров"
            placeholder={"Ноутбук Lenovo IdeaPad 15\nБумага офисная А4\nСтул офисный"}
            autosize
            minRows={5}
            maxRows={14}
            value={text}
            onChange={(e) => setText(e.currentTarget.value)}
            error={tooMany ? `Не более ${LIMIT} товаров за один раз (сейчас ${names.length})` : undefined}
          />
          <Group gap={6}>
            <Text size="xs" c="dimmed">Примеры:</Text>
            {EXAMPLES.map((ex) => (
              <Button key={ex} size="compact-xs" variant="light" onClick={() => setText((t) => (t.trim() ? `${t.trimEnd()}\n${ex}` : ex))}>
                {ex}
              </Button>
            ))}
          </Group>
          <Group justify="space-between">
            <Group>
              <Button size="md" onClick={onCheck} loading={busy} disabled={names.length === 0 || tooMany}>
                Проверить{names.length > 1 ? ` (${names.length})` : ""}
              </Button>
              <FileButton onChange={onFile} accept=".xlsx,.csv,.txt">
                {(props) => <Button {...props} size="md" variant="default" disabled={busy}>Загрузить Excel/CSV</Button>}
              </FileButton>
            </Group>
            {text && <Button variant="subtle" color="gray" onClick={() => setText("")}>Очистить</Button>}
          </Group>
        </Stack>
      </Paper>

      {progress && progress.done < progress.total && (
        <div>
          <Text size="sm" mb={4}>Обработано {progress.done} из {progress.total}</Text>
          <Progress value={(progress.done / progress.total) * 100} animated />
        </div>
      )}

      {error && <Alert color="red" title="Ошибка">{error}</Alert>}

      {results && (
        <Paper p="lg">
          <Group justify="space-between" mb="sm">
            <Text fw={600}>
              Результаты: {results.length}
              {reviewCount > 0 && <Text span c="orange" fw={500}> · требуют проверки: {reviewCount}</Text>}
            </Text>
            {exportUrl ? (
              <Button component="a" href={exportUrl} variant="light">Скачать Excel</Button>
            ) : (
              <Button variant="light" onClick={() => downloadCsv(results)}>Скачать таблицу (CSV)</Button>
            )}
          </Group>
          <ResultsTable results={results} />
        </Paper>
      )}
    </Stack>
  );
}
