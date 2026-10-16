import { screen } from "@testing-library/react";
import { render } from "../test/render";
import { NpaItemModal } from "./NpaItemModal";

describe("NpaItemModal", () => {
  it("собирает текст пункта из полей ответа /api/npa/items/{id}", async () => {
    render(<NpaItemModal itemId={662} onClose={() => {}} />); // прил. 3, п. 37 из заглушек
    expect(await screen.findByText("Приложение № 3, пункт 37")).toBeInTheDocument();
    expect(screen.getByText("ПРЕИМУЩЕСТВО")).toBeInTheDocument();
    expect(screen.getByText("мин. доля 80%")).toBeInTheDocument();
    expect(screen.getByText("26.20.11")).toBeInTheDocument();
    expect(screen.getByText("Открыть текст постановления")).toBeInTheDocument();
  });

  it("предупреждает о дополнительных условиях пункта", async () => {
    render(<NpaItemModal itemId={455} onClose={() => {}} />); // прил. 2, п. 300 — медизделия по кодам НКМИ
    expect(await screen.findByText(/есть дополнительные условия/)).toBeInTheDocument();
  });
});
