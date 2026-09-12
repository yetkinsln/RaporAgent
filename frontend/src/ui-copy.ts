const TECHNICAL_TERMS = /\b(?:paddleocr|ocr|qwen3?|llm|gpu|cuda|docker|json|schema|model|runtime|docx|fastapi)\b/i;

const SERVICE_ERRORS: Record<string, string> = {
  llm_unavailable: "Rapor taslağı hazırlama özelliği şu anda kullanılamıyor. Uygulamayı yeniden başlatıp tekrar deneyin.",
  llm_invalid_structured_output: "Rapor taslağı güvenli biçimde hazırlanamadı. Bilgileri kontrol edip yeniden deneyin.",
};

const DOCUMENT_CREATION_BLOCKERS: Record<string, string> = {
  docx_contract_files_missing: "Kurumsal rapor şablonu bulunamadı. Sistem yöneticinize başvurun.",
  docx_contract_unreadable: "Kurumsal rapor şablonu açılamadı. Sistem yöneticinize başvurun.",
  docx_mapping_template_mismatch: "Kurumsal rapor şablonu güncellenmeli. Sistem yöneticinize başvurun.",
  docx_runtime_unavailable: "Rapor dosyası oluşturma özelliği şu anda kullanılamıyor. Uygulamayı yeniden başlatıp tekrar deneyin.",
};

const EXTRACTION_WARNINGS: Record<string, string> = {
  critical_field_low_ocr_confidence: "Bu kritik bilginin okuma güveni düşük. Kaynak görüntüyü kontrol edip düzeltin veya onaylayın.",
  invalid_tckn_checksum: "T.C. kimlik numarası doğrulanamadı. Kaynak görüntüden kontrol edip yeniden onaylayın.",
};

export function userFacingServiceError(code: string | null, message: string): string {
  if (code && SERVICE_ERRORS[code]) return SERVICE_ERRORS[code];
  if (TECHNICAL_TERMS.test(message)) return "İşlem şu anda tamamlanamadı. Uygulamayı yeniden başlatıp tekrar deneyin.";
  return message;
}

export function documentReadingErrorMessage(message: string): string {
  if (/hazır değil|kurulum|paddleocr/i.test(message)) {
    return "Belge okuma özelliği şu anda hazır değil. Uygulamayı yeniden başlatıp tekrar deneyin.";
  }
  return "Belge okunamadı. Sayfa görüntüsünü kontrol edip yeniden deneyin.";
}

export function documentCreationBlockerMessage(code: string, message: string): string {
  if (DOCUMENT_CREATION_BLOCKERS[code]) return DOCUMENT_CREATION_BLOCKERS[code];
  return userFacingServiceError(code, message);
}

export function extractionWarningMessage(code: string, message: string): string {
  if (EXTRACTION_WARNINGS[code]) return EXTRACTION_WARNINGS[code];
  return userFacingServiceError(code, message);
}
