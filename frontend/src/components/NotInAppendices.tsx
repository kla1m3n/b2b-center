import { Anchor, Text } from "@mantine/core";

/** «Не подпадает»: пунктов приложений нет, но ссылка на текст постановления есть всегда. */
export function NotInAppendices({ url }: { url: string }) {
  const label = "не входит в прил. 1–3";
  return url ? (
    <Anchor href={url} target="_blank" rel="noreferrer" size="sm" title="Открыть текст ПП № 1875">{label}</Anchor>
  ) : (
    <Text size="sm" c="dimmed">{label}</Text>
  );
}
