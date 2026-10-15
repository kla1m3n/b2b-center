import { Badge } from "@mantine/core";
import { REGIME_LABELS, type Regime } from "../types";

// Цвета по спеке §5: красный — запрет, жёлтый — ограничение, синий — преимущество, зелёный — не подпадает.
// Текст дублирует цвет, чтобы режим читался и без различения цветов.
export const REGIME_COLORS: Record<Regime, string> = {
  ban: "red",
  restriction: "yellow",
  advantage: "blue",
  none: "green",
};

export function RegimeBadge({ regime, size = "md" }: { regime: Regime; size?: "sm" | "md" | "lg" }) {
  return (
    <Badge color={REGIME_COLORS[regime]} variant="filled" size={size} autoContrast
      // Режим — главное в строке: подпись никогда не обрезаем многоточием
      styles={{ root: { flexShrink: 0, overflow: "visible" }, label: { overflow: "visible", textOverflow: "clip" } }}>
      {REGIME_LABELS[regime]}
    </Badge>
  );
}
