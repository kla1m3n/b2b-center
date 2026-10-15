import { Alert, Anchor, Loader, Modal, Stack, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { getNpaItem } from "../api";
import type { NpaItemDetails } from "../types";

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
          <Text style={{ whiteSpace: "pre-line" }}>{item.raw_text}</Text>
          {item.note && <Text size="sm" c="dimmed">{item.note}</Text>}
          <Anchor href={item.source_url} target="_blank" rel="noreferrer" size="sm">
            Открыть текст постановления
          </Anchor>
        </Stack>
      )}
    </Modal>
  );
}
