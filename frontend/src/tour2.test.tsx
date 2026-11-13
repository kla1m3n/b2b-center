// Второй тур: сводный отчёт по списку (задача A) и проверка одного товара с объяснением и альтернативами (задача B).
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { JustificationBlock } from "./components/JustificationBlock";
import { ResultDetails } from "./components/ResultDetails";
import { SummaryBlock } from "./components/SummaryBlock";
import * as download from "./download";
import { classifySync } from "./mocks";
import { partitionPcts, sharePct, shortAction, summarize } from "./summary";
import { render } from "./test/render";
import type { ClassificationResult } from "./types";

const noop = () => {};
// 8 позиций: 1 запрет, 2 ограничения, 1 минимальная доля, 3 «не подпадает» (одна с низкой уверенностью), 1 ошибка
const batch = ["Бумага А4", "Ноутбук", "Щебень", "Лифт", "Хлеб", "Батон", "Непонятная штука", "123"].map(classifySync);

describe("сводка по списку", () => {
  it("считает позиции и доли по режимам, ручную проверку и ошибки — как backend", () => {
    const s = summarize(batch);
    expect(s.total).toBe(8);
    expect(s.errors).toBe(1);
    expect(s.by_regime.map((x) => [x.regime, x.count, x.share])).toEqual([
      ["ban", 1, 0.125], ["restriction", 2, 0.25], ["advantage", 1, 0.125], ["none", 3, 0.375],
    ]);
    expect(s.needs_review).toBe(1);
    expect(s.needs_review_share).toBe(0.125);
  });

  it("позиции с наименьшей уверенностью — по возрастанию, с номером в списке, без нераспознанных", () => {
    const s = summarize(batch);
    expect(s.lowest_confidence).toHaveLength(5);
    expect(s.lowest_confidence[0]).toMatchObject({ idx: 7, input: "Непонятная штука", confidence: 0.09 });
    expect(s.lowest_confidence.map((x) => x.idx)).toEqual([7, 4, 5, 6, 1]);
    expect(s.lowest_confidence.some((x) => x.input === "123")).toBe(false);
  });

  it("пустой список и подписи долей", () => {
    expect(summarize([])).toMatchObject({ total: 0, errors: 0, needs_review: 0, needs_review_share: 0, lowest_confidence: [] });
    expect([0, 0.004, 0.125, 0.375, 1].map(sharePct)).toEqual(["0%", "<1%", "13%", "38%", "100%"]);
  });

  it("доли режимов в сумме дают ровно 100% (метод наибольшего остатка)", () => {
    // было 50% + 38% + 13% = 101%: 37,5 и 12,5 округлялись вверх оба
    expect(partitionPcts([4, 3, 0, 1])).toEqual([50, 38, 0, 12]);
    expect(partitionPcts([1, 2, 1, 3, 1])).toEqual([13, 25, 12, 38, 12]);
    expect(partitionPcts([1, 1, 1])).toEqual([34, 33, 33]);
    expect(partitionPcts([0, 0])).toEqual([0, 0]);
    for (const counts of [[1, 1, 1], [2, 5, 7, 9], [1, 2, 3, 4, 5, 6], [97, 1, 1, 1]]) {
      expect(partitionPcts(counts).reduce((a, b) => a + b, 0)).toBe(100);
    }
  });

  it("короткое действие в строке таблицы зависит от режима и пометки", () => {
    expect(batch.map(shortAction)).toEqual([
      "Закупать российский товар", "Установить ограничение", "Установить ограничение", "Учесть в доле закупок",
      "Закупать на общих основаниях", "Закупать на общих основаниях", "Сначала проверить код", "Уточнить наименование",
    ]);
  });
});

describe("блок-сводка над таблицей", () => {
  it("показывает число позиций, доли, ручную проверку и наименьшую уверенность", () => {
    render(<SummaryBlock results={batch} filter="all" onFilter={noop} />);
    expect(screen.getByText("Сводка по списку")).toBeInTheDocument();
    expect(screen.getByText("8 позиций · режим по ПП № 1875")).toBeInTheDocument();
    expect(screen.getByText("Запрет: 1 · 13%")).toBeInTheDocument();
    expect(screen.getByText("Ограничение: 2 · 25%")).toBeInTheDocument();
    expect(screen.getByText("Не подпадает: 3 · 38%")).toBeInTheDocument();
    expect(screen.getByText("Мин. доля: 1 · 12%")).toBeInTheDocument();
    expect(screen.getByText("Не распознано: 1 · 12%")).toBeInTheDocument();  // 13 + 25 + 12 + 38 + 12 = 100
    // ручная проверка: низкая уверенность + нераспознанное наименование
    expect(screen.getByText("Требуют ручной проверки: 2 из 8 (25%)")).toBeInTheDocument();
    const lowest = screen.getAllByTestId("lowest-item");
    expect(lowest).toHaveLength(5);
    expect(within(lowest[0]).getByText("Непонятная штука")).toBeInTheDocument();
    expect(within(lowest[0]).getByText("9%")).toBeInTheDocument();
    expect(within(lowest[0]).getByText("№ 7")).toBeInTheDocument();
  });

  it("«Показать только их» включает фильтр ручной проверки и снимает его", () => {
    const onFilter = vi.fn();
    const { rerender } = render(<SummaryBlock results={batch} filter="all" onFilter={onFilter} />);
    fireEvent.click(screen.getByText("Показать только их"));
    expect(onFilter).toHaveBeenLastCalledWith("review");
    rerender(<SummaryBlock results={batch} filter="review" onFilter={onFilter} />);
    fireEvent.click(screen.getByText("Показать все"));
    expect(onFilter).toHaveBeenLastCalledWith("all");
  });

  it("если проверять нечего — так и пишет", () => {
    render(<SummaryBlock results={["Ноутбук", "Хлеб"].map(classifySync)} filter="all" onFilter={noop} />);
    expect(screen.getByText("Все позиции определены уверенно — ручная проверка не требуется.")).toBeInTheDocument();
    expect(screen.queryByText("Показать только их")).not.toBeInTheDocument();
  });
});

describe("рекомендация по действию", () => {
  const rec = (name: string) => classifySync(name).recommendation;

  it("зависит от режима и называет пункт ПП", () => {
    expect(rec("Бумага А4")).toContain("запрещена (прил. № 1, п. 10)");
    expect(rec("Бумага А4")).toContain("обоснование невозможности соблюдения запрета");
    expect(rec("Ноутбук")).toContain("ограничение закупок иностранных товаров (прил. № 2, п. 195)");
    expect(rec("Ноутбук")).toContain("минимальная обязательная доля товаров российского происхождения — 80%");
    expect(rec("Лифт")).toMatch(/^Запрета и ограничения нет/);
    expect(rec("Хлеб")).toContain("не входит в приложения № 1–3");
    expect(rec("123")).toContain("не распознано");
  });

  it("при низкой уверенности сначала просит подтвердить код", () => {
    expect(rec("Катетер")).toMatch(/^Сначала подтвердите код ОКПД2 вручную: уверенность 54%\./);
  });

  it("показывается в подробностях результата", () => {
    const r = classifySync("Бумага А4");
    render(<ResultDetails result={r} onOpenItem={noop} />);
    expect(within(screen.getByTestId("recommendation")).getByText(r.recommendation)).toBeInTheDocument();
  });
});

describe("альтернативные коды с режимом", () => {
  it("у альтернативы режим и пункт ПП её собственного кода", () => {
    const r = classifySync("Щебень гранитный");
    expect(r.verdict).toBe("restriction");
    expect(r.alternatives).toEqual([
      { code: "08.12.12.130", title: "Гравий", confidence: 0.02, verdict: "none", npa_matches: [], regime_differs: true },
    ]);
    const laptop = classifySync("Ноутбук").alternatives[0];
    expect(laptop).toMatchObject({ code: "26.20.11.130", verdict: "restriction", regime_differs: false });
    expect(laptop.npa_matches.map((m) => `${m.appendix}:${m.item_no}`)).toEqual(["2:195", "3:37"]);
  });

  it("таблица альтернатив: режим, пункт ПП, пометка «режим другой»", () => {
    const onOpenItem = vi.fn();
    render(<ResultDetails result={classifySync("Щебень гранитный")} onOpenItem={onOpenItem} />);
    const table = screen.getByTestId("alternatives");
    expect(within(table).getByText("08.12.12.130")).toBeInTheDocument();
    expect(within(table).getByText("НЕ ПОДПАДАЕТ")).toBeInTheDocument();
    expect(within(table).getByText("режим другой")).toBeInTheDocument();
    expect(within(table).getByText("не входит в прил. 1–3")).toBeInTheDocument();
    expect(screen.getByText(/при другом коде режим будет другим/)).toBeInTheDocument();
  });

  it("режим тот же — пометки нет, пункт открывается по клику", () => {
    const onOpenItem = vi.fn();
    render(<ResultDetails result={classifySync("Ноутбук")} onOpenItem={onOpenItem} />);
    const table = screen.getByTestId("alternatives");
    expect(within(table).getByText("ОГРАНИЧЕНИЕ")).toBeInTheDocument();
    expect(within(table).queryByText("режим другой")).not.toBeInTheDocument();
    expect(within(table).getByText("и ещё 1")).toBeInTheDocument();
    fireEvent.click(within(table).getByText("Прил. 2, п. 195"));
    expect(onOpenItem).toHaveBeenCalledWith(350);
    expect(screen.getByText("При любом из этих кодов режим тот же, что у выбранного.")).toBeInTheDocument();
  });
});

describe("обоснование для документации", () => {
  const r: ClassificationResult = classifySync("Ноутбук Lenovo IdeaPad 15");

  it("текст содержит всё, что нужно для документа", () => {
    const text = r.justification;
    expect(text).toContain("Наименование товара: Ноутбук Lenovo IdeaPad 15");
    expect(text).toContain("Код ОКПД2: 26.20.11.110 — Ноутбуки");
    expect(text).toContain("совпало с формулировкой «ноутбук»");
    expect(text).toContain("Режим по ПП № 1875: ограничение.");
    expect(text).toContain("приложение № 2, пункт 195 (ограничение)");
    expect(text).toContain("минимальная доля 80%");
    expect(text).toContain("Источник: ПП РФ № 1875 от 23.12.2024 (ред. на 30 сентября 2026 года) https://docs.cntd.ru/document/1310667825");
    expect(text).toContain("Уверенность классификации: 93%.");
    expect(text).toContain("26.20.11.130 — Планшетные компьютеры: ограничение (прил. № 2, п. 195; прил. № 3, п. 37 (мин. доля 80%)), уверенность 5%");
    expect(text).toContain(`Рекомендация: ${r.recommendation}`);
  });

  it("копируется в буфер обмена", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<JustificationBlock result={r} />);
    expect(screen.getByTestId("justification")).toHaveTextContent("Наименование товара: Ноутбук Lenovo IdeaPad 15");
    fireEvent.click(screen.getByText("Скопировать текст"));
    expect(writeText).toHaveBeenCalledWith(r.justification);
    await waitFor(() => expect(screen.getByText("Скопировано ✓")).toBeInTheDocument());
  });

  it("скачивается текстовым файлом", () => {
    const saveText = vi.spyOn(download, "saveText").mockImplementation(() => {});
    render(<JustificationBlock result={r} />);
    fireEvent.click(screen.getByText("Скачать .txt"));
    expect(saveText).toHaveBeenCalledWith(r.justification, "pp1875-obosnovanie.txt");
    saveText.mockRestore();
  });

  it("у нераспознанного наименования обоснования нет", () => {
    const { container } = render(<JustificationBlock result={classifySync("123")} />);
    expect(container.querySelector("[data-testid=justification]")).toBeNull();
  });
});
