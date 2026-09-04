import { describe, expect, it } from "vitest";

import { apiErrorMessage, apiUrl, normalizeApiBase } from "./api";

describe("API base adresi", () => {
  it("/api önekini yalnızca bir kez kullanır", () => {
    expect(normalizeApiBase("/api")).toBe("");
    expect(apiUrl("/api", "/api/cases")).toBe("/api/cases");
  });

  it("doğrudan yerel API adresini korur", () => {
    expect(apiUrl("http://127.0.0.1:8000", "/api/cases")).toBe("http://127.0.0.1:8000/api/cases");
  });

  it("FastAPI doğrulama dizisindeki alanı kullanıcıya gösterir", () => {
    expect(apiErrorMessage({ detail: [{ loc: ["body", "history"], msg: "Field required" }] }))
      .toBe("Anamnez ve olay öyküsü alanındaki değeri kontrol edip yeniden deneyin.");
  });

  it("sunucunun eyleme dönük hata metnini korur", () => {
    expect(apiErrorMessage({ detail: { code: "invalid_document_number", message: "Manuel SAYI değeri geçersiz." } }))
      .toBe("Manuel SAYI değeri geçersiz.");
  });
});
