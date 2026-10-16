import { Alert, Anchor, Badge, Group, Loader, Modal, Stack, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { getNpaItem } from "../api";
import type { NpaItemDetails } from "../types";
import { RegimeBadge } from "./RegimeBadge";

export const APPENDIX_NAMES: Record<number, string> = {
  1: "Перечень товаров, в отношении которых устанавливается запрет",
  2: "Перечень товаров, в отношении которых устанавливается ограничение",
  3: "Минимальная обязательная доля закупок российских товаров",
};

export function NpaItemModal({ itemId, onClose }: { itemId: number | null; onClose: () => void }) {
  const [item, setItem] = useState<NpaItemDetails | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (itemId === null) return;
    setItem(null);
    setError(null);
    getNpaItem(itemId).then(setItem, (e: Error) => setError(e.message));
  }, [itemId]);

  return (
    <Modal opened={itemId !== null} onClose={onClose} size="lg"
      title={item ? `Приложение № ${item.appendix}, пункт ${item.item_no}` : "Пункт ПП № 1875"}>
      {error && <Alert color="red">{error}</Alert>}
      {!item && !error && <Loader size="sm" />}
      {item && (
        <Stack gap="sm">
          <Group gap="xs">
            <RegimeBadge regime={item.regime} size="sm" />
            {item.quota !== null && <Badge variant="light" size="sm">мин. доля {item.quota}%</Badge>}
          </Group>
          <Text size="sm" c="dimmed">{APPENDIX_NAMES[item.appendix] ?? `Приложение № ${item.appendix}`}</Text>
          <Text>{item.title}</Text>
          <Text size="sm">
            <Text span c="dimmed">Коды ОКПД2: </Text>
            <Text span ff="monospace">{item.codes.join(", ")}</Text>
          </Text>
          {item.has_conditions && (
            <Alert color="orange" variant="light" p="xs">
              У пункта есть дополнительные условия (например, коды вида медицинского изделия) — сверьте товар с текстом пункта.
            </Alert>
          )}
          {item.note && <Text size="sm" c="dimmed">{item.note}</Text>}
          {item.source_url && (
            <Anchor href={item.source_url} target="_blank" rel="noreferrer" size="sm">
              Открыть текст постановления
            </Anchor>
          )}
        </Stack>
      )}
    </Modal>
  );
}
