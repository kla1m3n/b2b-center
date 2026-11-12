// Выбор кода ОКПД2 специалистом с пересчётом и возврат загруженной таблицы с результатами.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import * as api from "./api";
import { ResultDetails } from "./components/ResultDetails";
import { ResultsTable } from "./components/ResultsTable";
import * as download from "./download";
import { classifySync, withCodeSync } from "./mocks";
import { shortAction, summarize } from "./summary";
import { render } from "./test/render";

const noop = () => {};

describe("код, выбранный специалистом", () => {
  it("режим и пункты пересчитываются по новому коду, прежний код уходит в альтернативы", () => {
    const base = classifySync("Щебень гранитный"); // 08.12.12.140 — ограничение; альтернатива «Гравий» вне приложений
    const r = withCodeSync(base, "08.12.12.130");
    expect(r).toMatchObject({ code_confirmed: true, auto_code: "08.12.12.140", needs_review: false, verdict: "none", npa_matches: [] });
    expect(r.okpd2).toEqual({ code: "08.12.12.130", title: "Гравий" });
    expect(r.alternatives).toHaveLength(1);
    expect(r.alternatives[0]).toMatchObject({ code: "08.12.12.140", verdict: "restriction", regime_differs: true });
    expect(r.recommendation).toContain("не входит в приложения № 1–3");
    expect(r.justification).toContain("Код ОКПД2: 08.12.12.130 — Гравий");
    expect(r.justification).toContain("код выбран специалистом вручную (автоматически предлагался код 08.12.12.140)");
    expect(r.justification).not.toContain("Уверенность классификации");
  });

  it("подтверждение того же кода снимает пометку «проверьте вручную»", () => {
    const base = classifySync("Катетер уретральный");
    expect(base.needs_review).toBe(true);
    const r = withCodeSync(base, base.okpd2!.code);
    expect(r).toMatchObject({ code_confirmed: true, needs_review: false, verdict: base.verdict });
    expect(r.alternatives.map((a) => a.code)).toEqual(base.alternatives.map((a) => a.code));
    expect(r.recommendation).not.toContain("Сначала подтвердите");
    expect(r.justification).toContain("подтверждён специалистом");
    expect(shortAction(r)).toBe("Установить ограничение");
  });

  it("повторный выбор помнит исходный автоматический код", () => {
    const first = withCodeSync(classifySync("Щебень"), "08.12.12.130");
    expect(withCodeSync(first, "08.12.12.140")).toMatchObject({ auto_code: "08.12.12.140", verdict: "restriction" });
  });

  it("подтверждённая позиция не идёт в ручную проверку и в список наименьшей уверенности", () => {
    const base = ["Катетер", "Хлеб"].map(classifySync);
    expect(summarize(base)).toMatchObject({ needs_review: 1 });
    const s = summarize([withCodeSync(base[0], base[0].okpd2!.code), base[1]]);
    expect(s.needs_review).toBe(0);
    expect(s.lowest_confidence.map((x) => x.input)).toEqual(["Хлеб"]);
  });
});

describe("выбор кода на сайте", () => {
  it("кнопка «Выбрать» у альтернативы передаёт её код", async () => {
    const onChooseCode = vi.fn().mockResolvedValue(undefined);
    render(<ResultDetails result={classifySync("Щебень гранитный")} onOpenItem={noop} onChooseCode={onChooseCode} />);
    fireEvent.click(within(screen.getByTestId("alternatives")).getByLabelText("Выбрать код 08.12.12.130"));
    await waitFor(() => expect(onChooseCode).toHaveBeenCalledWith("08.12.12.130"));
  });

  it("при низкой уверенности можно подтвердить текущий код; ошибка пересчёта показывается", async () => {
    const onChooseCode = vi.fn().mockRejectedValue(new Error("Код не найден в справочнике ОКПД2"));
    render(<ResultDetails result={classifySync("Катетер")} onOpenItem={noop} onChooseCode={onChooseCode} />);
    fireEvent.click(screen.getByText("Код 32.50.13.110 верный — подтвердить"));
    expect(onChooseCode).toHaveBeenCalledWith("32.50.13.110");
    expect(await screen.findByText("Код не найден в справочнике ОКПД2")).toBeInTheDocument();
  });

  it("уверенный результат и просмотр без пересчёта — без кнопки подтверждения", () => {
    const { rerender } = render(<ResultDetails result={classifySync("Ноутбук")} onOpenItem={noop} onChooseCode={vi.fn()} />);
    expect(screen.queryByText(/верный — подтвердить/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Выбрать код 26.20.11.130")).toBeInTheDocument();
    rerender(<ResultDetails result={classifySync("Катетер")} onOpenItem={noop} />);
    expect(screen.queryByText(/верный — подтвердить/)).not.toBeInTheDocument();
    expect(screen.queryByText("Выбрать")).not.toBeInTheDocument();
  });

  it("после выбора — пометка «код подтверждён» вместо «проверьте вручную»", () => {
    const r = withCodeSync(classifySync("Щебень"), "08.12.12.130");
    render(<ResultsTable results={[r]} />);
    expect(screen.getByText("✓ Код подтверждён")).toBeInTheDocument();
    expect(screen.queryByText("⚠ Проверьте вручную")).not.toBeInTheDocument();
    expect(screen.getByTestId("code-confirmed")).toHaveTextContent("✓ Код подтверждён специалистом (система предлагала 08.12.12.140)");
  });

  it("таблица передаёт позицию и выбранный код", async () => {
    const onChooseCode = vi.fn().mockResolvedValue(undefined);
    const item = classifySync("Щебень");
    render(<ResultsTable results={[item]} onChooseCode={onChooseCode} />);
    fireEvent.click(screen.getByLabelText("Выбрать код 08.12.12.130"));
    await waitFor(() => expect(onChooseCode).toHaveBeenCalledWith(item, "08.12.12.130"));
  });
});

describe("запросы отчётов", () => {
  const blob = new Blob(["x"]);
  let fetchMock: ReturnType<typeof vi.fn>;
  let saved: [Blob, string][];

  beforeEach(() => {
    saved = [];
    fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: async () => blob });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(download, "saveBlob").mockImplementation((b, name) => void saved.push([b, name]));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("без ручных кодов отчёт пакета берётся по задаче", async () => {
    await api.downloadReport("xlsx", "job-1", ["Ноутбук", "Хлеб"], [null, null]);
    expect(fetchMock).toHaveBeenCalledWith("/api/jobs/job-1/export.xlsx", undefined);
    expect(saved[0][1]).toBe("pp1875-otchet.xlsx");
  });

  it("с кодами специалиста отчёт строится по наименованиям и кодам, даже если есть задача", async () => {
    await api.downloadReport("docx", "job-1", ["Ноутбук", "Хлеб"], [null, "10.71.11.110"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/report.docx");
    expect(JSON.parse(init.body)).toEqual({ names: ["Ноутбук", "Хлеб"], codes: [null, "10.71.11.110"] });
  });

  it("обоснование Word — с выбранным кодом", async () => {
    await api.downloadJustification("Ноутбук", "26.20.11.130");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ name: "Ноутбук", code: "26.20.11.130" });
    await api.downloadJustification("Ноутбук");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ name: "Ноутбук" });
  });

  it("таблица специалиста отправляется файлом, коды — только если выбраны; имя файла сохраняется", async () => {
    const file = new File(["x"], "Спецификация.xlsx");
    await api.downloadAnnotated(file, [null, "26.20.17.110"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/report/annotated.xlsx");
    expect((init.body as FormData).get("file")).toBeInstanceOf(File);
    expect((init.body as FormData).get("codes")).toBe('[null,"26.20.17.110"]');
    expect(saved[0][1]).toBe("Спецификация — ПП 1875.xlsx");
    await api.downloadAnnotated(file, [null, null]);
    expect((fetchMock.mock.calls[1][1].body as FormData).get("codes")).toBeNull();
  });

  it("ошибка backend показывается текстом из ответа", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: "Код 99 не найден в справочнике ОКПД2" }) });
    await expect(api.downloadReport("xlsx", null, ["x"], ["99"])).rejects.toThrow("Код 99 не найден в справочнике ОКПД2");
  });
});
