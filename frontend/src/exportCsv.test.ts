import { resultsToCsv } from "./exportCsv";
import { classifySync } from "./mocks";

describe("resultsToCsv", () => {
  it("BOM, шапка и экранирование кавычек и «;»", () => {
    const csv = resultsToCsv([classifySync('Ноутбук "Lenovo"; 15"')]);
    const [header, row] = csv.slice(1).split("\r\n");
    expect(csv.startsWith("﻿")).toBe(true);
    expect(header).toBe("Товар;Код ОКПД2;Наименование ОКПД2;Режим;Приложение;Пункт;Уверенность, %;Проверить вручную");
    expect(row.startsWith('"Ноутбук ""Lenovo""; 15"""')).toBe(true);
    expect(row).toContain("ОГРАНИЧЕНИЕ;2;2:195, 3:37;93;");
  });
});
