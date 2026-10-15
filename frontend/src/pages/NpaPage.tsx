import { Alert, Badge, Button, FileInput, Group, Paper, PasswordInput, Stack, Table, Text, TextInput, Title } from "@mantine/core";
import { useCallback, useEffect, useState } from "react";
import { getNpaVersions, uploadNpa } from "../api";
import type { NpaVersion, NpaVersionStatus } from "../types";

const STATUS: Record<NpaVersionStatus, { label: string; color: string }> = {
  parsing: { label: "разбирается…", color: "blue" },
  ready: { label: "готова", color: "green" },
  failed: { label: "ошибка", color: "red" },
};

const fmtDate = (iso: string) => new Date(iso).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });

export function NpaPage() {
  const [versions, setVersions] = useState<NpaVersion[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [token, setToken] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  const load = useCallback(() => getNpaVersions().then(setVersions, (e: Error) => setError(e.message)), []);

  useEffect(() => {
    load();
  }, [load]);

  // Пока какая-то версия разбирается — обновляем список раз в 2 с
  const parsing = versions?.some((v) => v.status === "parsing");
  useEffect(() => {
    if (!parsing) return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [parsing, load]);

  async function onUpload() {
    if (!file) return;
    setUploading(true);
    setUploadMsg(null);
    setError(null);
    try {
      await uploadNpa(file, title, sourceUrl, token);
      setUploadMsg("Файл принят. Новая редакция станет активной, когда разбор закончится; до этого работает текущая.");
      setFile(null);
      setTitle("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  const active = versions?.find((v) => v.is_active);

  return (
    <Stack gap="lg">
      <div>
        <Title order={2}>База ПП № 1875</Title>
        <Text c="dimmed" mt={4}>
          Когда постановление меняется, загрузите новую редакцию — перезапускать систему не нужно.
          Пока новая редакция разбирается, проверки идут по текущей.
        </Text>
      </div>

      {error && <Alert color="red" title="Ошибка">{error}</Alert>}

      <Paper p="lg">
        <Text fw={600}>Действующая редакция</Text>
        {active ? (
          <Text mt={4}>{active.title} · позиций: {active.items_count} · загружена {fmtDate(active.uploaded_at)}</Text>
        ) : (
          <Text mt={4} c="dimmed">{versions ? "Нет активной редакции" : "Загрузка…"}</Text>
        )}
      </Paper>

      <Paper p="lg">
        <Text fw={600} mb="sm">Загрузить новую редакцию</Text>
        <Stack gap="sm" maw={560}>
          <FileInput label="Файл редакции" description="JSON или XLSX в формате docs/npa-structure.md" placeholder="Выберите файл"
            accept=".json,.xlsx,.docx" value={file} onChange={setFile} clearable />
          <TextInput label="Название" placeholder="ПП РФ № 1875 (ред. на …)" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
          <TextInput label="Ссылка на источник" placeholder="https://…" value={sourceUrl} onChange={(e) => setSourceUrl(e.currentTarget.value)} />
          <PasswordInput label="Пароль администратора" description="Загрузка меняет базу для всех пользователей сайта"
            value={token} onChange={(e) => setToken(e.currentTarget.value)} />
          <Group>
            <Button onClick={onUpload} loading={uploading} disabled={!file}>Загрузить</Button>
          </Group>
          {uploadMsg && <Alert color="green">{uploadMsg}</Alert>}
        </Stack>
      </Paper>

      <Paper p="lg">
        <Text fw={600} mb="sm">История редакций</Text>
        <Table.ScrollContainer minWidth={560}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Редакция</Table.Th>
                <Table.Th>Загружена</Table.Th>
                <Table.Th>Статус</Table.Th>
                <Table.Th>Позиций</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {versions?.map((v) => (
                <Table.Tr key={v.id}>
                  <Table.Td>
                    {v.title} {v.is_active && <Badge size="sm" variant="light" ml={4}>действует</Badge>}
                    {v.error && <Text size="xs" c="red">{v.error}</Text>}
                  </Table.Td>
                  <Table.Td>{fmtDate(v.uploaded_at)}</Table.Td>
                  <Table.Td><Badge color={STATUS[v.status].color} variant="light">{STATUS[v.status].label}</Badge></Table.Td>
                  <Table.Td>{v.status === "ready" ? v.items_count : "—"}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Paper>
    </Stack>
  );
}
