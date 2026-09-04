export type DocumentType =
  | "cover_letter"
  | "general_forensic_exam"
  | "epicrisis"
  | "department_exam_note"
  | "other"
  | "unknown";

export type FieldStatus = "extracted" | "user_corrected" | "missing" | "conflict";
export type FieldValue = string | string[] | null;

export type Polygon = [number, number][] | null;

export interface Provenance {
  source_document_id: string | null;
  page: number | null;
  evidence_text: string | null;
  ocr_confidence: number | null;
  polygon: Polygon;
}

export interface Candidate {
  value: FieldValue;
  original_value: FieldValue;
  provenance: Provenance;
}

export interface EvidenceField {
  value: FieldValue;
  original_value: FieldValue;
  status: FieldStatus;
  approved: boolean;
  provenance: Provenance;
  candidates: Candidate[];
}

export interface Warning {
  code: string;
  message: string;
  severity: "info" | "warning" | "blocking";
  field_path: string | null;
}

export interface Page {
  page: number;
  width: number | null;
  height: number | null;
  transform: {
    revision: number;
    operations: Array<Record<string, unknown>>;
  };
  image_endpoint: string;
}

export interface CropSelection {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface OcrLine {
  text: string;
  confidence: number;
  polygon: [number, number][];
  reading_order: number;
  page: number;
}

export interface CaseDocument {
  document_id: string;
  file_name: string;
  mime_type: string;
  type: DocumentType;
  classification_confidence: number | null;
  user_confirmed_type: boolean;
  pages: Page[];
  ocr_status: "not_started" | "completed" | "error";
  ocr_error: string | null;
  ocr_lines: OcrLine[];
  is_synthetic: boolean;
}

export interface Extraction {
  schema_version: "1.2.0";
  case_id: string;
  patient: Record<string, EvidenceField>;
  request: Record<string, EvidenceField>;
  medical: Record<string, EvidenceField>;
  documents: Array<{
    document_id: string;
    type: DocumentType;
    file_name: string;
    page_count: number;
    classification_confidence: number | null;
    user_confirmed_type: boolean;
  }>;
  warnings: Warning[];
  ready_to_generate: false;
}

export interface ReportDraftMetadata {
  draft_id: string;
  created_at: string;
  status: "review_required" | "invalidated";
  model_name: string;
  prompt_version: string;
}

export interface ReportDraft {
  schema_version: "1.0.0";
  draft_id: string;
  case_id: string;
  created_at: string;
  status: "review_required";
  generation: {
    provider: string;
    model_name: string;
    model_revision: string;
    prompt_version: string;
    local_only: true;
  };
  source_extraction_version: "1.2.0";
  sections: Array<{
    id: "introduction" | "general_forensic_exam" | "conclusion";
    title: string;
    text: string;
    source_field_paths: string[];
  }>;
  blockers: [];
}

export interface LlmStatus {
  provider: string;
  model_name: string;
  model_files_ready: boolean;
  runtime_ready: boolean;
  loaded: boolean;
  local_only: true;
}

export interface BulkApprovalResponse {
  case: CaseState;
  approved_field_paths: string[];
  skipped: Array<{
    field_path: string;
    reason: "missing" | "conflict" | "invalid_tckn";
  }>;
}

export interface DocxStatus {
  available: boolean;
  blockers: Array<{
    code: string;
    message: string;
  }>;
  template: {
    file_name: string;
    sha256: string;
    mapped_field_count: number;
  } | null;
  sayi_mode: "manual";
  sayi_auto_generate: false;
}

export interface DocxInput {
  document_number: string;
  document_date: string;
  examination_date: string;
  history: string;
  current_exam_findings: string;
}

export interface DocxReport {
  report_id: string;
  file_name: string;
  status: "review_required" | "superseded";
  template_sha256: string;
  mapping_sha256: string;
  source_field_paths: string[];
  download_endpoint: string;
}

export interface CaseState {
  case_id: string;
  documents: CaseDocument[];
  extraction: Extraction | null;
  report_drafts: ReportDraftMetadata[];
  docx_input: {
    values: DocxInput;
    status: "review_required" | "approved";
  } | null;
  docx_reports: DocxReport[];
  report_draft_eligibility: {
    ready: boolean;
    missing_approvals: string[];
  };
  stage: "documents" | "review";
}

export interface ReportDraftResponse {
  case: CaseState;
  draft: ReportDraft;
}

export interface DocxReportResponse {
  case: CaseState;
  report: DocxReport;
}
