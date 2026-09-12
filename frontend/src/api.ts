import type { BulkApprovalResponse, CaseState, CropSelection, DocxInput, DocxReportResponse, DocxStatus, DocumentType, FieldValue, HealthStatus, LlmStatus, ReportDraftResponse } from "./types";
import { userFacingServiceError } from "./ui-copy";

// API yolları aşağıda zaten `/api/...` ile başlar. Eski Docker yapılarında
// VITE_API_BASE `/api` olarak kalmış olsa bile yolu iki kez eklemeyelim.
const configuredApiBase = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export function normalizeApiBase(value: string): string {
  return value.replace(/\/api\/?$/, "");
}

export function apiUrl(base: string, endpoint: string): string {
  return `${normalizeApiBase(base)}${endpoint}`;
}

const apiBase = normalizeApiBase(configuredApiBase);

type ApiErrorPayload = { detail?: unknown };

const validationFieldLabels: Record<string, string> = {
  document_number: "Manuel SAYI",
  document_date: "Rapor düzenleme tarihi",
  examination_date: "Muayene tarihi ve saati",
  history: "Anamnez ve olay öyküsü",
  current_exam_findings: "Güncel muayene bulguları",
};

export function apiErrorMessage(payload: unknown): string {
  const detail = (payload as ApiErrorPayload | null)?.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail) && "message" in detail && typeof detail.message === "string") {
    const code = "code" in detail && typeof detail.code === "string" ? detail.code : null;
    return userFacingServiceError(code, detail.message);
  }
  // Eski sunucu sürümü veya başka bir FastAPI doğrulama rotası yine standart
  // 422 dizisi döndürürse, kullanıcıya boş genel hata yerine alanı göster.
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { loc?: unknown };
    const loc = Array.isArray(first.loc) ? first.loc : [];
    const field = typeof loc.at(-1) === "string" ? loc.at(-1) : null;
    if (field) return `${validationFieldLabels[field] ?? field} alanındaki değeri kontrol edip yeniden deneyin.`;
  }
  return "Yerel uygulama isteği tamamlanamadı.";
}

export function assetUrl(endpoint: string): string {
  return apiUrl(apiBase, endpoint);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(apiBase, path), init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(apiErrorMessage(payload));
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthStatus>("/api/health"),
  createCase: () => request<CaseState>("/api/cases", { method: "POST" }),
  createDemoCase: () => request<CaseState>("/api/demo-case", { method: "POST" }),
  getCase: (caseId: string) => request<CaseState>(`/api/cases/${caseId}`),
  deleteCase: (caseId: string) => request<{ deleted: true; case_id: string }>(`/api/cases/${caseId}`, { method: "DELETE" }),
  process: (caseId: string) => request<CaseState>(`/api/cases/${caseId}/process`, { method: "POST" }),
  setDocumentType: (caseId: string, documentId: string, documentType: DocumentType) =>
    request<CaseState>(`/api/documents/${documentId}/type?case_id=${encodeURIComponent(caseId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_type: documentType }),
    }),
  deleteDocument: (caseId: string, documentId: string) =>
    request<CaseState>(`/api/cases/${caseId}/documents/${documentId}`, { method: "DELETE" }),
  updateField: (caseId: string, fieldPath: string, value: FieldValue) =>
    request<CaseState>(`/api/cases/${caseId}/fields/${fieldPath}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    }),
  approveField: (caseId: string, fieldPath: string) =>
    request<CaseState>(`/api/cases/${caseId}/fields/${fieldPath}/approve`, { method: "POST" }),
  approveAllFields: (caseId: string) =>
    request<BulkApprovalResponse>(`/api/cases/${caseId}/fields/approve-all`, { method: "POST" }),
  llmStatus: () => request<LlmStatus>("/api/llm/status"),
  docxStatus: () => request<DocxStatus>("/api/docx/status"),
  saveDocxInput: (caseId: string, values: DocxInput) =>
    request<CaseState>(`/api/cases/${caseId}/docx-input`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    }),
  createDocx: (caseId: string) =>
    request<DocxReportResponse>(`/api/cases/${caseId}/docx`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmed: true }),
    }),
  createReportDraft: (caseId: string) =>
    request<ReportDraftResponse>(`/api/cases/${caseId}/report-drafts`, { method: "POST" }),
  transformPage: (
    caseId: string,
    documentId: string,
    pageNumber: number,
    operation: "rotate_clockwise" | "rotate_counterclockwise" | "crop" | "reset",
    crop?: CropSelection,
  ) =>
    request<CaseState>(`/api/cases/${caseId}/documents/${documentId}/pages/${pageNumber}/transform`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ operation, ...(crop ? { crop } : {}) }),
    }),
  upload: (caseId: string, file: File) => {
    const form = new FormData();
    form.set("file", file);
    return request<CaseState>(`/api/cases/${caseId}/documents`, { method: "POST", body: form });
  },
};
