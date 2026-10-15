import { fireEvent, screen } from "@testing-library/react";
import { classifySync } from "../mocks";
import { render } from "../test/render";
import type { ClassificationResult, Regime } from "../types";
import { RegimeBadge } from "./RegimeBadge";
import { ResultsTable } from "./ResultsTable";

describe("RegimeBadge", () => {
  it.each<[Regime, string]>([
    ["ban", "ЗАПРЕТ"],
    ["restriction", "ОГРАНИЧЕНИЕ"],
    ["advantage", "ПРЕИМУЩЕСТВО"],
    ["none", "НЕ ПОДПАДАЕТ"],
  ])("%s → «%s»", (regime, label) => {
    render(<RegimeBadge regime={regime} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

describe("ResultsTable", () => {
  it("помечает строки с низкой уверенностью «Проверьте вручную»", () => {
    const sure = classifySync("Ноутбук Lenovo");
    const unsure: ClassificationResult = { ...classifySync("Толстовка"), input: "Толстовка" };
    render(<ResultsTable results={[sure, unsure]} />);
    expect(screen.getAllByText("⚠ Проверьте вручную")).toHaveLength(1);
  });

  it("показывает режим, пункт ПП и уверенность", () => {
    render(<ResultsTable results={[classifySync("Щебень гранитный")]} />);
    expect(screen.getByText("ОГРАНИЧЕНИЕ")).toBeInTheDocument();
    expect(screen.getByText("Прил. 2, п. 1")).toBeInTheDocument();
    expect(screen.getByText("97%")).toBeInTheDocument();
  });

  it("показывает ошибку вместо результата", () => {
    render(<ResultsTable results={[classifySync("123 456")]} />);
    expect(screen.getByText("Пустое или нераспознанное наименование")).toBeInTheDocument();
  });

  it("раскрывает подробности: все пункты и альтернативы", () => {
    render(<ResultsTable results={[classifySync("Ноутбук")]} />);
    fireEvent.click(screen.getByLabelText("Показать подробности"));
    expect(screen.getByText("Прил. 3, п. 37")).toBeInTheDocument();
    expect(screen.getByText("мин. доля 80%")).toBeInTheDocument();
    expect(screen.getByText("Другие возможные коды ОКПД2")).toBeInTheDocument();
  });
});
