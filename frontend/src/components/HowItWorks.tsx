import { Box, Group, SimpleGrid, Text } from "@mantine/core";

const STEPS = [
  {
    title: "Наименование → код ОКПД2",
    text: "Модель ИИ понимает смысл названия («ноут 15 дюймов» ≈ «Ноутбуки») и подбирает код среди 15 тыс. кодов ОКПД2.",
  },
  {
    title: "Код → пункт ПП № 1875",
    text: "Код сверяется с приложениями 1–3 постановления обычным алгоритмом, без ИИ: пункт закона не «придумывается».",
  },
  {
    title: "Результат с уверенностью",
    text: "Режим — запрет, ограничение, преимущество или не подпадает — со ссылкой на пункт. Если система не уверена, строка помечается «⚠ Проверьте вручную».",
  },
];

/** Пустое состояние до первой проверки: как работает сервис (в стиле блоков-разделов ЕИС). */
export function HowItWorks() {
  return (
    <div>
      <Text className="caps-label" c="dimmed" mb="sm">Как это работает</Text>
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        {STEPS.map((s, i) => (
          <Box key={s.title} className="how-step">
            <Group gap="sm" wrap="nowrap" align="flex-start">
              <div className="how-step__num" aria-hidden>{i + 1}</div>
              <div>
                <Text fw={500} c="eis.6">{s.title}</Text>
                <Text size="sm" c="dimmed" mt={4}>{s.text}</Text>
              </div>
            </Group>
          </Box>
        ))}
      </SimpleGrid>
    </div>
  );
}
