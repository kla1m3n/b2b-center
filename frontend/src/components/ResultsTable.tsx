import { ActionIcon, Anchor, Badge, Table, Text } from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import { Fragment, useState } from "react";
import type { ClassificationResult } from "../types";
import { ConfidenceCell } from "./ConfidenceCell";
import { NotInAppendices } from "./NotInAppendices";
import { NpaItemModal } from "./NpaItemModal";
import { ResultCards } from "./ResultCards";
import { RegimeBadge } from "./RegimeBadge";
import { ResultDetails } from "./ResultDetails";

const NOWRAP = { whiteSpace: "nowrap" } as const;

export function ResultsTable({ results }: { results: ClassificationResult[] }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [openItem, setOpenItem] = useState<number | null>(null);

  const toggle = (i: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  // На телефоне таблица не помещается — показываем карточки (sm = 48em в теме Mantine)
  const mobile = useMediaQuery("(max-width: 48em)");
  if (mobile) {
    return (
      <>
        <ResultCards results={results} expanded={expanded} onToggle={toggle} onOpenItem={setOpenItem} />
        <NpaItemModal itemId={openItem} onClose={() => setOpenItem(null)} />
      </>
    );
  }

  return (
    <>
      <Table.ScrollContainer minWidth={760}>
        <Table verticalSpacing="sm" highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={36} />
              <Table.Th>Товар</Table.Th>
              <Table.Th>Код ОКПД2</Table.Th>
              <Table.Th style={NOWRAP}>Режим</Table.Th>
              <Table.Th style={NOWRAP}>Пункт ПП</Table.Th>
              <Table.Th>Уверенность</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {results.map((r, i) => {
              const top = r.npa_matches[0];
              const isOpen = expanded.has(i);
              return (
                <Fragment key={i}>
                  <Table.Tr>
                    <Table.Td>
                      {!r.error && (
                        <ActionIcon variant="subtle" onClick={() => toggle(i)}
                          aria-label={isOpen ? "Скрыть подробности" : "Показать подробности"} aria-expanded={isOpen}>
                          {isOpen ? "▾" : "▸"}
                        </ActionIcon>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" lineClamp={2}>{r.input}</Text>
                      {r.needs_review && !r.error && (
                        <Badge color="orange" variant="light" size="sm" mt={4}>⚠ Проверьте вручную</Badge>
                      )}
                    </Table.Td>
                    {r.error ? (
                      <Table.Td colSpan={4}><Text size="sm" c="red">{r.error}</Text></Table.Td>
                    ) : (
                      <>
                        <Table.Td>
                          <Text size="sm" ff="monospace">{r.okpd2?.code}</Text>
                          <Text size="xs" c="dimmed" lineClamp={2}>{r.okpd2?.title}</Text>
                        </Table.Td>
                        <Table.Td><RegimeBadge regime={r.verdict} /></Table.Td>
                        <Table.Td style={NOWRAP}>
                          {top ? (
                            top.item_id !== null ? (
                              <Anchor component="button" type="button" size="sm" onClick={() => setOpenItem(top.item_id)}>
                                Прил. {top.appendix}, п. {top.item_no}
                              </Anchor>
                            ) : (
                              <Text size="sm">Прил. {top.appendix}, п. {top.item_no}</Text>
                            )
                          ) : (
                            <NotInAppendices url={r.npa_source_url} />
                          )}
                          {r.npa_matches.length > 1 && (
                            <Text size="xs" c="dimmed">и ещё {r.npa_matches.length - 1}</Text>
                          )}
                        </Table.Td>
                        <Table.Td><ConfidenceCell value={r.confidence} /></Table.Td>
                      </>
                    )}
                  </Table.Tr>
                  {isOpen && (
                    <Table.Tr>
                      <Table.Td />
                      <Table.Td colSpan={5}>
                        <ResultDetails result={r} onOpenItem={setOpenItem} />
                      </Table.Td>
                    </Table.Tr>
                  )}
                </Fragment>
              );
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <NpaItemModal itemId={openItem} onClose={() => setOpenItem(null)} />
    </>
  );
}
