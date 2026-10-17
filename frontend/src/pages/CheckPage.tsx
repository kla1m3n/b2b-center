import { Alert, Anchor, Button, FileButton, Group, Paper, Progress, Stack, Text, Textarea, Title } from "@mantine/core";
import { useRef, useState, type DragEvent } from "react";
import { classify, classifyBatch, classifyFile, getJob, jobExportUrl } from "../api";
import { HistoryList } from "../components/HistoryList";
import { HowItWorks } from "../components/HowItWorks";
import { ResultsSummary } from "../components/ResultsSummary";
import { ResultsTable } from "../components/ResultsTable";
import { downloadCsv, downloadTemplate } from "../exportCsv";
import { addToHistory, clearHistory, loadHistory, removeFromHistory, type HistoryEntry } from "../history";
import { matchesFilter, type ResultFilter } from "../resultFilters";
import type { ClassificationResult } from "../types";

const LIMIT = 100;
const EXAMPLES = ["Ноутбук Lenovo IdeaPad 15", "Бумага офисная А4", "Щебень гранитный", "Хлеб пшеничный (батон)", "Лифт пассажирский"];
const FILE_TYPES = /\.(xlsx|csv|txt)$/i;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const plural = (n: number) => (n % 10 === 1 && n % 100 !== 11 ? "товар" : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? "товара" : "товаров");

export function CheckPage() {
  const [text, setText] = useState("");
  const [results, setResults] = useState<ClassificationResult[] | null>(null);
  const [filter, setFilter] = useState<ResultFilter>("all");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>(loadHistory);
  const runId = useRef(0);

  const names = text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);

  function showResults(res: ClassificationResult[], source: string) {
    setResults(res);
    setFilter("all");
    setHistory(addToHistory(source, res));
  }

  async function waitJob(id: string, run: number, source: string) {
    setJobId(id);
    for (;;) {
      const job = await getJob(id);
      if (run !== runId.current) return; // пользователь запустил новую проверку
      setProgress({ done: job.done, total: job.total });
      if (job.status === "done") {
        showResults(job.results ?? [], source);
        return;
      }
      if (job.status === "failed") throw new Error(job.error || "Не удалось обработать список. Попробуйте ещё раз.");
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
      const source = names.length === 1 ? names[0] : `${names.length} ${plural(names.length)}`;
      if (names.length === 1) {
        const res = await classify(names[0]);
        if (r === runId.current) showResults([res], source);
      } else {
        const { job_id } = await classifyBatch(names);
        await waitJob(job_id, r, source);
      }
    });

  const onFile = (file: File | null) => {
    if (!file) return;
    if (!FILE_TYPES.test(file.name)) {
      setError("Поддерживаются файлы .xlsx, .csv и .txt");
      return;
    }
    run(async (r) => {
      const { job_id } = await classifyFile(file);
      await waitJob(job_id, r, `файл «${file.name}»`);
    });
  };

  // Перетаскивание файла на форму. dragleave приходит и при переходе между вложенными элементами —
  // поэтому проверяем, что курсор действительно ушёл за пределы формы.
  const dragProps = {
    onDragOver: (e: DragEvent) => {
      if (busy || !e.dataTransfer.types.includes("Files")) return;
      e.preventDefault();
      setDragging(true);
    },
    onDragLeave: (e: DragEvent) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
    },
    onDrop: (e: DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (!busy) onFile(e.dataTransfer.files[0] ?? null);
    },
  };

  const openHistory = (e: HistoryEntry) => {
    runId.current++; // отменяем ожидание текущей задачи, если оно идёт
    setBusy(false);
    setError(null);
    setProgress(null);
    setJobId(null); // у сохранённых результатов нет задачи на backend → выгрузка в CSV
    setResults(e.results);
    setFilter("all");
  };

  const exportUrl = jobId ? jobExportUrl(jobId) : null;
  const tooMany = names.length > LIMIT;
  const shown = results?.filter((r) => matchesFilter(r, filter)) ?? [];

  return (
    <Stack gap="lg">
      <div>
        <Title order={2}>Проверка товаров по ПП № 1875</Title>
        <Text c="dimmed" mt={4}>
          Введите наименования товаров — каждое с новой строки (до {LIMIT}) — или перетащите сюда таблицу Excel/CSV.
          Система подберёт код ОКПД2 и покажет, действует ли запрет, ограничение или преимущество.
        </Text>
      </div>

      <Paper p="lg" className="drop-target" data-dragging={dragging || undefined} {...dragProps}>
        {dragging && <div className="drop-target__overlay">Отпустите файл, чтобы проверить список</div>}
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
          <Text size="xs" c="dimmed">
            Файл: товары в одной колонке, шапка и номера не мешают.{" "}
            <Anchor component="button" type="button" size="xs" onClick={downloadTemplate}>Скачать шаблон</Anchor>
          </Text>
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
          <Group justify="space-between" mb="sm" align="flex-start">
            <ResultsSummary results={results} value={filter} onChange={setFilter} />
            {exportUrl ? (
              <Button component="a" href={exportUrl} variant="light">Скачать Excel</Button>
            ) : (
              <Button variant="light" onClick={() => downloadCsv(results)}>Скачать таблицу (CSV)</Button>
            )}
          </Group>
          {shown.length > 0 ? (
            // key: при смене фильтра сбрасываем раскрытые строки (они по индексу)
            <ResultsTable key={filter} results={shown} />
          ) : (
            <Text c="dimmed" size="sm">Нет строк с таким результатом.</Text>
          )}
        </Paper>
      )}

      {!results && !busy && <HowItWorks />}

      <HistoryList
        entries={history}
        onOpen={openHistory}
        onRemove={(id) => setHistory(removeFromHistory(id))}
        onClear={() => setHistory(clearHistory())}
      />
    </Stack>
  );
}
