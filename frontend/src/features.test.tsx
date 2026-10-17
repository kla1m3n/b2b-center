import { fireEvent, screen } from "@testing-library/react";
import { ResultsSummary } from "./components/ResultsSummary";
import { addToHistory, clearHistory, loadHistory, removeFromHistory } from "./history";
import { classifySync, namesFromCsv } from "./mocks";
import { countResults, matchesFilter } from "./resultFilters";
import { render } from "./test/render";

const batch = ["Ноутбук", "Бумага А4", "Хлеб", "Лифт", "Толстовка", "123"].map(classifySync);

describe("фильтры результатов", () => {
  it("считает режимы, «проверить вручную» и ошибки", () => {
    const c = countResults(batch);
    expect(c).toMatchObject({ all: 6, ban: 1, restriction: 1, advantage: 1, none: 2, review: 1, error: 1 });
  });

  it("ошибка не попадает в фильтр по режиму", () => {
    const err = batch[5];
    expect(matchesFilter(err, "none")).toBe(false);
    expect(matchesFilter(err, "error")).toBe(true);
  });

  it("клик по счётчику включает фильтр, повторный — снимает", () => {
    const onChange = vi.fn();
    const { rerender } = render(<ResultsSummary results={batch} value="all" onChange={onChange} />);
    fireEvent.click(screen.getByText("Запрет: 1"));
    expect(onChange).toHaveBeenLastCalledWith("ban");
    rerender(<ResultsSummary results={batch} value="ban" onChange={onChange} />);
    fireEvent.click(screen.getByText("Запрет: 1"));
    expect(onChange).toHaveBeenLastCalledWith("all");
  });
});

describe("разбор CSV как на backend", () => {
  it("шаблон: берёт колонку с наименованиями и пропускает шапку", () => {
    const csv = '﻿№;Наименование товара;Количество\r\n1;Ноутбук Lenovo;5\r\n2;Бумага офисная А4;100\r\n';
    expect(namesFromCsv(csv)).toEqual(["Ноутбук Lenovo", "Бумага офисная А4"]);
  });
});

describe("история проверок", () => {
  beforeEach(() => clearHistory());

  it("сохраняет новые записи сверху и не больше 10", () => {
    for (let i = 0; i < 12; i++) addToHistory(`проверка ${i}`, [batch[0]]);
    const h = loadHistory();
    expect(h).toHaveLength(10);
    expect(h[0].source).toBe("проверка 11");
  });

  it("удаляет запись", () => {
    addToHistory("первая", [batch[0]]);
    const [entry] = addToHistory("вторая", [batch[1]]);
    expect(removeFromHistory(entry.id).map((e) => e.source)).toEqual(["первая"]);
  });
});
