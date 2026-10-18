import { resultsToCsv } from "./exportCsv";
import { classifySync } from "./mocks";

const CRLF = String.fromCharCode(13, 10);
const BOM = String.fromCharCode(0xfeff);

describe("resultsToCsv", () => {
  it("BOM, шапка и экранирование кавычек и «;»", () => {
    const csv = resultsToCsv([classifySync('Ноутбук "Lenovo"; 15"')]);
    const [header, row] = csv.slice(1).split(CRLF);
    expect(csv.startsWith(BOM)).toBe(true);
    expect(header).toBe("Товар;Код ОКПД2;Наименование ОКПД2;Режим;Приложение;Пункт;Уверенность, %;Проверить вручную");
    expect(row.startsWith('"Ноутбук ""Lenovo""; 15"""')).toBe(true);
    expect(row).toContain("ОГРАНИЧЕНИЕ;2;2:195, 3:37;93;");
  });

  it("«не подпадает»: в колонке пунктов — пометка, а не пустота", () => {
    const row = resultsToCsv([classifySync("Хлеб пшеничный")]).split(CRLF)[1];
    expect(row).toContain("НЕ ПОДПАДАЕТ;;не входит в прил. 1–3;");
  });
});
