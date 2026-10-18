import { fireEvent, screen } from "@testing-library/react";
import { classifySync } from "../mocks";
import { render } from "../test/render";
import { ResultCards } from "./ResultCards";

const noop = () => {};

describe("ResultCards", () => {
  it("карточка: режим, товар, код ОКПД2 и пункт ПП", () => {
    render(<ResultCards results={[classifySync("Ноутбук Lenovo")]} expanded={new Set()} onToggle={noop} onOpenItem={noop} />);
    expect(screen.getByText("ОГРАНИЧЕНИЕ")).toBeInTheDocument();
    expect(screen.getByText("Ноутбук Lenovo")).toBeInTheDocument();
    expect(screen.getByText("26.20.11.110")).toBeInTheDocument();
    expect(screen.getByText("Прил. 2, п. 195")).toBeInTheDocument();
    expect(screen.getByText("и ещё 1")).toBeInTheDocument();
  });

  it("товар вне приложений и ошибка", () => {
    render(<ResultCards results={[classifySync("Хлеб"), classifySync("123")]} expanded={new Set()} onToggle={noop} onOpenItem={noop} />);
    // «не подпадает»: пунктов нет, но есть ссылка на текст постановления
    expect(screen.getByText("не входит в прил. 1–3").closest("a")).toHaveAttribute("href", "https://docs.cntd.ru/document/1310667825");
    expect(screen.getByText("Пустое или нераспознанное наименование")).toBeInTheDocument();
  });

  it("«Подробнее» вызывает раскрытие, раскрытая карточка показывает все пункты", () => {
    const onToggle = vi.fn();
    const { rerender } = render(
      <ResultCards results={[classifySync("Щебень")]} expanded={new Set()} onToggle={onToggle} onOpenItem={noop} />,
    );
    fireEvent.click(screen.getByText("Подробнее ▾"));
    expect(onToggle).toHaveBeenCalledWith(0);
    rerender(<ResultCards results={[classifySync("Щебень")]} expanded={new Set([0])} onToggle={onToggle} onOpenItem={noop} />);
    expect(screen.getByText("мин. доля 80%")).toBeInTheDocument();
  });
});
