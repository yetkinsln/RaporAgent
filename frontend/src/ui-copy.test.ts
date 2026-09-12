import { describe, expect, it } from "vitest";

import { documentCreationBlockerMessage, documentReadingErrorMessage, extractionWarningMessage, userFacingServiceError } from "./ui-copy";

describe("kullanıcı arayüzü hata metinleri", () => {
  it("rapor hazırlama altyapısının teknik ayrıntılarını göstermez", () => {
    const message = userFacingServiceError("llm_unavailable", "Yerel Qwen3 modeli GPU belleğine yüklenemedi.");
    expect(message).toBe("Rapor taslağı hazırlama özelliği şu anda kullanılamıyor. Uygulamayı yeniden başlatıp tekrar deneyin.");
    expect(message).not.toMatch(/Qwen|GPU|LLM/i);
  });

  it("belge okuma altyapısının marka adını göstermez", () => {
    const message = documentReadingErrorMessage("Yerel PaddleOCR paketi kullanıma hazır değil.");
    expect(message).toBe("Belge okuma özelliği şu anda hazır değil. Uygulamayı yeniden başlatıp tekrar deneyin.");
    expect(message).not.toMatch(/Paddle|OCR/i);
  });

  it("şablon eşleme ayrıntısını eyleme dönük metne çevirir", () => {
    const message = documentCreationBlockerMessage("docx_mapping_template_mismatch", "JSON alan eşlemesi uyuşmuyor.");
    expect(message).toBe("Kurumsal rapor şablonu güncellenmeli. Sistem yöneticinize başvurun.");
    expect(message).not.toMatch(/JSON|eşleme/i);
  });

  it("alan uyarılarında teknik güven terimi yerine anlaşılır dil kullanır", () => {
    const message = extractionWarningMessage("critical_field_low_ocr_confidence", "Kritik alanın OCR güveni düşük.");
    expect(message).toBe("Bu kritik bilginin okuma güveni düşük. Kaynak görüntüyü kontrol edip düzeltin veya onaylayın.");
    expect(message).not.toMatch(/OCR/i);
  });

  it("zaten anlaşılır olan alan hatasını korur", () => {
    expect(userFacingServiceError("invalid_document_number", "Manuel SAYI değeri geçersiz."))
      .toBe("Manuel SAYI değeri geçersiz.");
  });
});
