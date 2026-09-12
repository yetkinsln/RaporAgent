import { ChangeEvent, DragEvent, PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { api, assetUrl } from "./api";
import { cropPointFromSvg, normaliseCrop } from "./crop-utils";
import { displayValue, inputToFieldValue, maskTckn } from "./field-utils";
import { documentCreationBlockerMessage, documentReadingErrorMessage, extractionWarningMessage } from "./ui-copy";
import type { CaseDocument, CaseState, CropSelection, DocxInput, DocxReport, DocxStatus, EvidenceField, FieldValue, HealthStatus, Provenance, ReportDraft } from "./types";

export const GROUPS = [
  { id: "patient", title: "Hasta kimliği", key: "patient", fields: ["full_name", "tckn", "birth_place", "birth_date"] },
  { id: "request", title: "Üst yazı", key: "request", fields: ["sender_authority", "letter_date", "letter_number", "incident", "requested_questions"] },
  {
    id: "medical",
    title: "Genel adli muayene",
    key: "medical",
    fields: ["issuing_institution", "protocol_number", "report_date", "report_number", "incident_date_time", "incident_type", "clinical_findings", "general_forensic_exam_summary", "life_threat", "simple_medical_intervention"],
  },
  { id: "supplemental-medical", title: "Ek klinik belgeler", key: "medical", fields: ["epicrisis_summary", "department_exam_summary"] },
] as const;

const LABELS: Record<string, string> = {
  full_name: "Adı soyadı",
  tckn: "TCKN",
  birth_place: "Doğum yeri",
  birth_date: "Doğum tarihi",
  sender_authority: "Gönderen makam",
  letter_date: "Yazı tarihi",
  letter_number: "Yazı sayısı",
  incident: "İlgili olay",
  requested_questions: "İstenen hususlar",
  issuing_institution: "Kurum",
  protocol_number: "Protokol no",
  report_date: "Rapor tarihi",
  report_number: "Rapor sayısı",
  incident_date_time: "Başvuru/olay tarihi",
  incident_type: "Başvuru nedeni",
  clinical_findings: "Klinik bulgular",
  general_forensic_exam_summary: "Genel adli muayene özeti",
  life_threat: "Hayati tehlike",
  simple_medical_intervention: "BTM değerlendirmesi",
  epicrisis_summary: "Epikriz / acil servis özeti",
  department_exam_summary: "Adli Tıp Anabilim Dalı özeti",
};

const TYPE_LABELS: Record<CaseDocument["type"], string> = {
  cover_letter: "Üst yazı",
  general_forensic_exam: "Genel adli muayene",
  epicrisis: "Epikriz / acil servis notu",
  department_exam_note: "Adli Tıp muayene notu",
  other: "Diğer",
  unknown: "Belirsiz",
};

const BULK_SKIP_LABELS = {
  missing: "Kaynakta bulunamadı",
  conflict: "Çelişkili değer",
  invalid_tckn: "T.C. kimlik numarası doğrulanamadı",
} as const;

const FIELD_STATUS_LABELS = {
  extracted: "Belgeden okundu",
  user_corrected: "Kullanıcı düzeltti",
  missing: "Bulunamadı",
  conflict: "Çelişkili",
} as const;

const BUSY_LABELS: Record<string, string> = {
  restore: "Son yerel vaka açılıyor…",
  demo: "Sentetik vaka hazırlanıyor…",
  upload: "Belgeler güvenli biçimde yükleniyor…",
  process: "Belgeler okunuyor ve bilgiler hazırlanıyor…",
  type: "Belge türü kaydediliyor…",
  delete: "Belge yerel depodan siliniyor…",
  "delete-case": "Vaka ve yerel dosyaları siliniyor…",
  field: "Alan düzeltmesi kaydediliyor…",
  approve: "Alan onayı kaydediliyor…",
  "approve-all": "Uygun alanlar onaylanıyor…",
  transform: "Sayfa görünümü güncelleniyor…",
  draft: "Rapor taslağı hazırlanıyor…",
  "docx-input": "Rapor bilgileri kaydediliyor…",
  docx: "Kurumsal rapor dosyası oluşturuluyor…",
};

const WORKFLOW_STEPS = [
  "Belgeler",
  "Sayfa kontrolü",
  "Belge okuma",
  "Kullanıcı onayı",
  "Rapor taslağı",
  "Dosyayı indir",
] as const;

const LAST_CASE_STORAGE_KEY = "rapor-agent.last-case-id";

type SelectedSource = { fieldPath: string; provenance: Provenance } | null;

function defaultDocxInput(): DocxInput {
  const today = new Date();
  const date = `${String(today.getDate()).padStart(2, "0")}.${String(today.getMonth() + 1).padStart(2, "0")}.${today.getFullYear()}`;
  return {
    document_number: "",
    document_date: date,
    examination_date: "",
    history: "",
    current_exam_findings: "",
  };
}

export default function App() {
  const [caseState, setCaseState] = useState<CaseState | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [selectedSource, setSelectedSource] = useState<SelectedSource>(null);
  const [showTextBoxes, setShowTextBoxes] = useState(true);
  const [cropMode, setCropMode] = useState(false);
  const [cropDraft, setCropDraft] = useState<CropSelection | null>(null);
  const [reportDraft, setReportDraft] = useState<ReportDraft | null>(null);
  const [healthStatus, setHealthStatus] = useState<HealthStatus | null>(null);
  const [docxStatus, setDocxStatus] = useState<DocxStatus | null>(null);
  const [docxInput, setDocxInput] = useState<DocxInput>(() => defaultDocxInput());
  const [docxConfirmed, setDocxConfirmed] = useState(false);
  const [generatedDocx, setGeneratedDocx] = useState<DocxReport | null>(null);
  const [bulkApprovalResult, setBulkApprovalResult] = useState<{ approved: number; skipped: Array<{ field_path: string; reason: keyof typeof BULK_SKIP_LABELS }> } | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const cropStart = useRef<{ x: number; y: number } | null>(null);
  const cropPointerId = useRef<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedDocument = useMemo(
    () => caseState?.documents.find((document) => document.document_id === selectedDocumentId) ?? caseState?.documents[0] ?? null,
    [caseState, selectedDocumentId],
  );
  const selectedPage = selectedDocument?.pages[0] ?? null;

  useEffect(() => {
    void api.health().then(setHealthStatus).catch(() => setHealthStatus(null));
    void api.docxStatus().then(setDocxStatus).catch(() => setDocxStatus(null));
    const lastCaseId = window.localStorage.getItem(LAST_CASE_STORAGE_KEY);
    if (lastCaseId && /^[a-f0-9]{32}$/.test(lastCaseId)) {
      setBusy("restore");
      void api.getCase(lastCaseId)
        .then((restored) => {
          setCaseState(restored);
          setSelectedDocumentId(restored.documents[0]?.document_id ?? null);
        })
        .catch(() => window.localStorage.removeItem(LAST_CASE_STORAGE_KEY))
        .finally(() => setBusy(null));
    }
  }, []);

  useEffect(() => {
    if (caseState?.case_id) window.localStorage.setItem(LAST_CASE_STORAGE_KEY, caseState.case_id);
  }, [caseState?.case_id]);

  useEffect(() => {
    if (caseState?.docx_input?.values) setDocxInput(caseState.docx_input.values);
  }, [caseState?.case_id, caseState?.docx_input]);

  async function run(label: string, action: () => Promise<CaseState>) {
    setBusy(label);
    setError(null);
    setNotice(null);
    try {
      const next = await action();
      setCaseState(next);
      if (!selectedDocumentId && next.documents[0]) setSelectedDocumentId(next.documents[0].document_id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "İşlem tamamlanamadı.");
    } finally {
      setBusy(null);
    }
  }

  function createDemo() {
    setSelectedSource(null);
    setReportDraft(null);
    setBulkApprovalResult(null);
    setGeneratedDocx(null);
    setDocxConfirmed(false);
    setSelectedDocumentId(null);
    void run("demo", api.createDemoCase);
  }

  function processCase() {
    if (!caseState) return;
    setReportDraft(null);
    setBulkApprovalResult(null);
    setGeneratedDocx(null);
    void run("process", () => api.process(caseState.case_id));
  }

  async function uploadSelectedFiles(files: File[]) {
    if (!files.length) return;
    setBusy("upload");
    setError(null);
    setNotice(null);
    try {
      let current = caseState ?? (await api.createCase());
      for (const file of files) current = await api.upload(current.case_id, file);
      setCaseState(current);
      setReportDraft(null);
      setBulkApprovalResult(null);
      setGeneratedDocx(null);
      setDocxConfirmed(false);
      setSelectedDocumentId(current.documents.at(-1)?.document_id ?? null);
      setNotice(`${files.length} belge vakaya eklendi.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Yükleme tamamlanamadı.");
    } finally {
      setBusy(null);
    }
  }

  function uploadFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    void uploadSelectedFiles(files);
  }

  function dropFiles(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragActive(false);
    if (busy !== null) return;
    void uploadSelectedFiles(Array.from(event.dataTransfer.files));
  }

  function deleteCase() {
    if (!caseState || !window.confirm("Bu vaka; yüklenen belgeler, okunan bilgiler, düzeltmeler ve üretilen taslaklarla birlikte bu bilgisayardan kalıcı olarak silinecek. Devam etmek istiyor musunuz?")) return;
    const caseId = caseState.case_id;
    void (async () => {
      setBusy("delete-case");
      setError(null);
      setNotice(null);
      try {
        await api.deleteCase(caseId);
        window.localStorage.removeItem(LAST_CASE_STORAGE_KEY);
        setCaseState(null);
        setSelectedDocumentId(null);
        setSelectedSource(null);
        setReportDraft(null);
        setBulkApprovalResult(null);
        setGeneratedDocx(null);
        setDocxConfirmed(false);
        setNotice("Vaka ve vakaya ait tüm dosyalar silindi.");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Vaka silinemedi.");
      } finally {
        setBusy(null);
      }
    })();
  }

  function updateType(documentId: string, type: CaseDocument["type"]) {
    if (!caseState) return;
    setReportDraft(null);
    setBulkApprovalResult(null);
    setGeneratedDocx(null);
    void run("type", () => api.setDocumentType(caseState.case_id, documentId, type));
  }

  function deleteDocument(documentId: string, fileName: string) {
    if (!caseState || !window.confirm(`“${fileName}” belgesini ve bu belgeye ait yerel sayfa dosyalarını silmek istiyor musunuz?`)) return;

    setSelectedSource(null);
    setCropMode(false);
    setCropDraft(null);
    setBulkApprovalResult(null);
    setGeneratedDocx(null);
    void (async () => {
      setBusy("delete");
      setError(null);
      try {
        const next = await api.deleteDocument(caseState.case_id, documentId);
        setCaseState(next);
        setSelectedDocumentId((current) => {
          if (current !== documentId) return current;
          return next.documents[0]?.document_id ?? null;
        });
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Belge silinemedi.");
      } finally {
        setBusy(null);
      }
    })();
  }

  function selectSource(fieldPath: string, provenance: Provenance) {
    setSelectedSource({ fieldPath, provenance });
    if (provenance.source_document_id) setSelectedDocumentId(provenance.source_document_id);
  }

  function saveField(fieldPath: string, value: FieldValue) {
    if (!caseState) return;
    setReportDraft(null);
    setBulkApprovalResult(null);
    setGeneratedDocx(null);
    void run("field", () => api.updateField(caseState.case_id, fieldPath, value));
  }

  function approveField(fieldPath: string) {
    if (!caseState) return;
    void run("approve", () => api.approveField(caseState.case_id, fieldPath));
  }

  function approveAllFields() {
    if (!caseState) return;
    const confirmed = window.confirm(
      "Bu işlem, belgelerde bulunan tüm uygun bilgileri sizin onayınızla işaretler. Eksik, çelişkili ve doğrulanamayan T.C. kimlik numarası alanları atlanır. Devam etmek istiyor musunuz?",
    );
    if (!confirmed) return;
    void (async () => {
      setBusy("approve-all");
      setError(null);
      try {
        const result = await api.approveAllFields(caseState.case_id);
        setCaseState(result.case);
        setBulkApprovalResult({ approved: result.approved_field_paths.length, skipped: result.skipped });
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Toplu onay tamamlanamadı.");
      } finally {
        setBusy(null);
      }
    })();
  }

  function createReportDraft() {
    if (!caseState) return;
    void (async () => {
      setBusy("draft");
      setError(null);
      try {
        const result = await api.createReportDraft(caseState.case_id);
        setCaseState(result.case);
        setReportDraft(result.draft);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Taslak üretilemedi.");
      } finally {
        setBusy(null);
      }
    })();
  }

  function saveDocxInput() {
    if (!caseState) return;
    setDocxConfirmed(false);
    void run("docx-input", () => api.saveDocxInput(caseState.case_id, docxInput));
  }

  function createDocx() {
    if (!caseState || !docxConfirmed) return;
    const confirmed = window.confirm(
      "Manuel SAYI, güncel muayene bilgileri ve onayladığınız belge bilgileri kurumsal rapor şablonuna aktarılacak. Rapor dosyasını oluşturmak istiyor musunuz?",
    );
    if (!confirmed) return;
    void (async () => {
      setBusy("docx");
      setError(null);
      try {
        const saved = await api.saveDocxInput(caseState.case_id, docxInput);
        setCaseState(saved);
        const result = await api.createDocx(caseState.case_id);
        setCaseState(result.case);
        setGeneratedDocx(result.report);
        setDocxConfirmed(false);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Rapor dosyası oluşturulamadı.");
      } finally {
        setBusy(null);
      }
    })();
  }

  function transformPage(operation: "rotate_clockwise" | "rotate_counterclockwise" | "crop" | "reset", crop?: CropSelection) {
    if (!caseState || !selectedDocument || !selectedPage) return;
    setSelectedSource(null);
    setCropMode(false);
    setCropDraft(null);
    setReportDraft(null);
    setBulkApprovalResult(null);
    setGeneratedDocx(null);
    void run("transform", () => api.transformPage(caseState.case_id, selectedDocument.document_id, selectedPage.page, operation, crop));
  }

  function startCrop(event: PointerEvent<SVGSVGElement>) {
    if (!cropMode) return;
    event.preventDefault();
    const point = cropPointFromSvg(event.currentTarget, event.clientX, event.clientY);
    cropStart.current = point;
    cropPointerId.current = event.pointerId;
    event.currentTarget.setPointerCapture(event.pointerId);
    setCropDraft({ left: point.x, top: point.y, right: point.x, bottom: point.y });
  }

  function updateCrop(event: PointerEvent<SVGSVGElement>) {
    if (!cropMode || cropPointerId.current !== event.pointerId || !cropStart.current) return;
    event.preventDefault();
    const point = cropPointFromSvg(event.currentTarget, event.clientX, event.clientY);
    setCropDraft({ left: cropStart.current.x, top: cropStart.current.y, right: point.x, bottom: point.y });
  }

  function finishCrop(event: PointerEvent<SVGSVGElement>) {
    if (cropPointerId.current !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    cropPointerId.current = null;
    cropStart.current = null;
  }

  const normalisedCrop = cropDraft ? normaliseCrop(cropDraft, selectedPage?.width, selectedPage?.height) : null;
  const bulkApprovalEligibleCount = useMemo(() => {
    if (!caseState?.extraction) return 0;
    return GROUPS.flatMap(({ key, fields }) => fields.map((name) => caseState.extraction?.[key]?.[name]))
      .filter((field): field is EvidenceField => Boolean(
        field
        && !field.approved
        && field.status !== "missing"
        && field.status !== "conflict"
        && field.value !== null
        && field.value !== ""
        && (!Array.isArray(field.value) || field.value.length > 0),
      )).length;
  }, [caseState]);

  const fieldSummary = useMemo(() => {
    if (!caseState?.extraction) return { total: 0, populated: 0, approved: 0 };
    const fields = GROUPS.flatMap(({ key, fields }) => fields.map((name) => caseState.extraction?.[key]?.[name])).filter((field): field is EvidenceField => Boolean(field));
    return {
      total: fields.length,
      populated: fields.filter((field) => field.value !== null && field.value !== "" && (!Array.isArray(field.value) || field.value.length > 0)).length,
      approved: fields.filter((field) => field.approved).length,
    };
  }, [caseState]);
  const completedDocumentCount = caseState?.documents.filter((document) => document.ocr_status === "completed").length ?? 0;
  const blockingWarningCount = caseState?.extraction?.warnings.filter((warning) => warning.severity === "blocking").length ?? 0;
  const hasActiveDraft = Boolean(reportDraft || caseState?.report_drafts.some((draft) => draft.status === "review_required"));
  const hasActiveDocx = Boolean(caseState?.docx_reports.some((report) => report.status === "review_required"));
  const currentStep = hasActiveDocx ? 6 : !caseState?.documents.length ? 1
    : !caseState.extraction ? 3
      : !caseState.report_draft_eligibility.ready ? 4
        : !hasActiveDraft ? 5 : 6;
  const systemState = healthStatus === null ? "checking" : healthStatus.status === "ready" ? "ready" : "unavailable";
  const systemLabel = systemState === "checking" ? "Hazırlanıyor" : systemState === "ready" ? "Sistem hazır" : "Kontrol gerekiyor";

  return (
    <main id="main-content">
      <header className="app-header">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">AR</span>
          <div>
            <p className="eyebrow">PAMUKKALE ÜNİVERSİTESİ · YEREL ÇALIŞMA ALANI</p>
            <h1>Adli Rapor Çalışma Alanı</h1>
            <p className="subtitle">Belgeleri inceleyin, bilgileri doğrulayın ve kurumsal rapor taslağını güvenle oluşturun.</p>
          </div>
        </div>
        <div className="header-actions">
          <span className={`system-status ${systemState}`} role="status"><i aria-hidden="true" />{systemLabel}</span>
          <span className="privacy-badge"><span aria-hidden="true">◆</span> Bilgiler bu cihazda kalır</span>
          {!caseState && <button className="secondary" onClick={createDemo} disabled={busy !== null}>Örnek vakayla dene</button>}
        </div>
      </header>

      <section className="safety-strip" aria-label="Kullanım uyarısı">
        <b>Karar destek taslağı</b>
        <span>Bu uygulama nihai tıbbi karar vermez. Her alan ve çıktı yetkili kullanıcı incelemesi gerektirir.</span>
      </section>

      {busy && <div className="operation-bar" role="status" aria-live="polite"><span className="spinner" aria-hidden="true" />{BUSY_LABELS[busy] ?? "İşlem sürüyor…"}</div>}
      {error && <div className="alert error" role="alert"><span>{error}</span><button onClick={() => setError(null)} aria-label="Hata bildirimini kapat">×</button></div>}
      {notice && <div className="alert success" role="status"><span>{notice}</span><button onClick={() => setNotice(null)} aria-label="Bildirimi kapat">×</button></div>}

      <section className="workflow" aria-label="İşlem aşamaları">
        {WORKFLOW_STEPS.map((label, index) => {
          const number = index + 1;
          const complete = number < currentStep || (number === 6 && hasActiveDocx);
          return <span className={`${number === currentStep ? "current" : ""} ${complete ? "complete" : ""}`} key={label}><b>{complete ? "✓" : number}</b><em>{label}</em></span>;
        })}
      </section>

      <section className="case-overview" aria-label="Vaka özeti">
        <article><span>Belgeler</span><b>{caseState?.documents.length ?? 0}</b><small>{caseState ? `${completedDocumentCount} belge okundu` : "Henüz vaka açılmadı"}</small></article>
        <article><span>Onaylanan bilgiler</span><b>{fieldSummary.approved}<i>/{fieldSummary.populated || fieldSummary.total}</i></b><small>{fieldSummary.populated ? `${fieldSummary.populated} bilgi bulundu` : "Henüz bilgi çıkarılmadı"}</small></article>
        <article className={blockingWarningCount ? "attention" : ""}><span>Bekleyen kontroller</span><b>{blockingWarningCount}</b><small>{blockingWarningCount ? "İncelemeniz gerekiyor" : "Her şey yolunda"}</small></article>
      </section>

      <section className="workspace">
        <aside className="documents-panel panel">
          <div className="panel-heading">
            <div><p className="eyebrow">01 · VAKA BELGELERİ</p><h2>Belge yönetimi</h2></div>
            {caseState && <button className="case-delete" onClick={deleteCase} disabled={busy !== null} title="Vaka ve tüm yerel dosyalarını sil">Vakayı sil</button>}
          </div>
          <label
            className={`upload-zone ${dragActive ? "drag-active" : ""} ${busy ? "disabled" : ""}`}
            onDragEnter={(event) => { event.preventDefault(); if (!busy) setDragActive(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragActive(false)}
            onDrop={dropFiles}
          >
            <input type="file" accept="application/pdf,image/png,image/jpeg" multiple onChange={uploadFiles} disabled={busy !== null} />
            <span className="upload-icon" aria-hidden="true">＋</span>
            <strong>{dragActive ? "Belgeleri buraya bırakın" : "Belge ekleyin veya sürükleyin"}</strong>
            <span>PDF, PNG veya JPEG · Belge başına en fazla 20 MB · PDF için 25 sayfa</span>
          </label>
          {!caseState?.documents.length && (
            <div className="empty-state rich-empty"><span aria-hidden="true">▤</span><div><b>İncelemeye belgeyle başlayın</b><p>Belgelerinizi yükleyin veya uygulamayı tanımak için örnek vakayı açın.</p></div></div>
          )}
          <div className="document-list">
            {caseState?.documents.map((document) => (
              <article className={`document-card ${selectedDocument?.document_id === document.document_id ? "active" : ""}`} key={document.document_id}>
                <button className="document-select" onClick={() => setSelectedDocumentId(document.document_id)}>
                  <strong>{document.file_name}</strong>
                  <span>{document.pages.length} sayfa · {document.is_synthetic ? "Örnek belge" : "Yüklenen belge"}</span>
                </button>
                <label className="type-select">
                  <span>Belge türü</span>
                  <select value={document.type} onChange={(event) => updateType(document.document_id, event.target.value as CaseDocument["type"])} disabled={busy !== null}>
                    {Object.entries(TYPE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                  </select>
                </label>
                <div className="document-meta">
                  <span className={`status ${document.ocr_status}`}>{document.ocr_status === "completed" ? "Okundu" : document.ocr_status === "error" ? "Okunamadı" : "Okunmayı bekliyor"}</span>
                  {document.classification_confidence !== null && <span>Tür eşleşmesi %{Math.round(document.classification_confidence * 100)}</span>}
                </div>
                {document.ocr_error && <small className="error-text">{documentReadingErrorMessage(document.ocr_error)}</small>}
                <div className="document-actions">
                  <button className="small danger" onClick={() => deleteDocument(document.document_id, document.file_name)} disabled={busy !== null}>Belgeyi sil</button>
                </div>
              </article>
            ))}
          </div>
          <button className="primary process-button" onClick={processCase} disabled={!caseState?.documents.length || busy !== null}>
            {busy === "process" ? "Belgeler okunuyor…" : caseState?.extraction ? "Belgeleri yeniden oku" : "Belgeleri oku ve bilgileri çıkar"}
          </button>
          <small className="local-note"><span aria-hidden="true">●</span> Belgeler yalnızca bu bilgisayarda işlenir.</small>
        </aside>

        <section className="viewer-panel panel">
          <div className="panel-heading viewer-heading">
            <div><p className="eyebrow">02 · KAYNAK SAYFA</p><h2>{selectedDocument?.file_name ?? "Sayfa seçilmedi"}</h2>{selectedPage && <small className="page-meta">Sayfa {selectedPage.page}</small>}</div>
            <div className="viewer-controls">
              <button className="icon-button" title="90° sola döndür" onClick={() => transformPage("rotate_counterclockwise")} disabled={!selectedPage || busy !== null}>↶</button>
              <button className="icon-button" title="90° sağa döndür" onClick={() => transformPage("rotate_clockwise")} disabled={!selectedPage || busy !== null}>↷</button>
              {cropMode ? (
                <>
                  <button className="small primary" onClick={() => normalisedCrop && transformPage("crop", normalisedCrop)} disabled={!normalisedCrop || busy !== null}>Kırpmayı uygula</button>
                  <button className="small ghost" onClick={() => { setCropMode(false); setCropDraft(null); }}>Vazgeç</button>
                </>
              ) : <button className="small ghost" onClick={() => { setCropMode(true); setCropDraft(null); }} disabled={!selectedPage || busy !== null}>Kırp</button>}
              <button className="small ghost" title="Özgün sayfaya dön" onClick={() => transformPage("reset")} disabled={!selectedPage?.transform?.operations.length || busy !== null}>Sıfırla</button>
              <label className="toggle"><input type="checkbox" checked={showTextBoxes} onChange={(event) => setShowTextBoxes(event.target.checked)} /> Metin kutuları</label>
            </div>
          </div>
          {selectedPage && selectedDocument ? (
            <div className="page-frame">
              <svg className={`page-svg ${cropMode ? "cropping" : ""}`} viewBox={`0 0 ${selectedPage.width ?? 1000} ${selectedPage.height ?? 1400}`} role="img" aria-label={`${selectedDocument.file_name}, sayfa ${selectedPage.page}`} onPointerDown={startCrop} onPointerMove={updateCrop} onPointerUp={finishCrop} onPointerCancel={finishCrop} onLostPointerCapture={finishCrop}>
                <image href={assetUrl(`${selectedPage.image_endpoint}?revision=${selectedPage.transform?.revision ?? 0}`)} width="100%" height="100%" preserveAspectRatio="none" />
                {showTextBoxes && selectedDocument.ocr_lines.filter((line) => line.page === selectedPage.page).map((line) => {
                  const selected = samePolygon(selectedSource?.provenance.polygon, line.polygon);
                  return <polygon key={`${line.reading_order}-${line.text}`} points={line.polygon.map((point) => point.join(",")).join(" ")} className={selected ? "selected" : ""} />;
                })}
                {normalisedCrop && <rect className="crop-selection" x={normalisedCrop.left * (selectedPage.width ?? 1000)} y={normalisedCrop.top * (selectedPage.height ?? 1400)} width={(normalisedCrop.right - normalisedCrop.left) * (selectedPage.width ?? 1000)} height={(normalisedCrop.bottom - normalisedCrop.top) * (selectedPage.height ?? 1400)} />}
              </svg>
              {!selectedDocument.ocr_lines.length && <div className="viewer-message">Belge okunduğunda bulunan metinler burada işaretlenir.</div>}
              {cropMode && <div className="crop-instruction">Kullanmak istediğiniz alanı sayfa üzerinde sürükleyerek seçin. Uyguladığınızda belge yeniden okunur.</div>}
            </div>
          ) : <div className="viewer-empty"><span className="viewer-empty-icon" aria-hidden="true">▧</span><b>Kaynak sayfa burada görüntülenir</b><p>Sol panelden bir belge yükleyin veya örnek vakayla deneme yapın.</p></div>}
          {selectedSource?.provenance.evidence_text && <div className="evidence-bar"><b>Seçili kanıt</b><span>“{selectedSource.provenance.evidence_text}”</span></div>}
        </section>

        <aside className="review-panel panel">
          <div className="panel-heading">
            <div><p className="eyebrow">03 · BİLGİ KONTROLÜ</p><h2>Bulunan bilgiler</h2></div>
          </div>
          {!caseState?.extraction && <div className="empty-state rich-empty"><span aria-hidden="true">✓</span><div><b>Bilgi kontrolü henüz başlamadı</b><p>Belgeler okunduğunda bulunan bilgiler, kaynakları ve güven oranlarıyla burada listelenir.</p></div></div>}
          {caseState?.extraction && (
            <>
              <div className="warnings">
                {caseState.extraction.warnings.map((warning, index) => (
                  <button className={`warning ${warning.severity}`} key={`${warning.code}-${index}`} onClick={() => warning.field_path && focusField(warning.field_path, caseState, selectSource)}>
                    <b>{warning.severity === "blocking" ? "Engel" : warning.severity === "warning" ? "Uyarı" : "Bilgi"}</b>{extractionWarningMessage(warning.code, warning.message)}
                  </button>
                ))}
              </div>
              <section className="bulk-approval" aria-label="Toplu alan onayı">
                <div>
                  <h3>Toplu onay</h3>
                  <p>{bulkApprovalEligibleCount ? `${bulkApprovalEligibleCount} kaynaklı alan toplu onay için uygun.` : "Toplu onaylanabilecek alan yok."} Bu işlem otomatik karar vermez; yalnızca sizin açık onayınızı kaydeder.</p>
                </div>
                <button className="secondary" onClick={approveAllFields} disabled={bulkApprovalEligibleCount === 0 || busy !== null}>
                  {busy === "approve-all" ? "Alanlar onaylanıyor…" : "Okunan alanları topluca onayla"}
                </button>
                {bulkApprovalResult && (
                  <div className="bulk-result" role="status">
                    <b>{bulkApprovalResult.approved} alan onaylandı.</b>
                    {bulkApprovalResult.skipped.length > 0 && (
                      <span>Atlanan: {bulkApprovalResult.skipped.map((item) => `${LABELS[item.field_path.split(".")[1]] ?? item.field_path} (${BULK_SKIP_LABELS[item.reason]})`).join(", ")}</span>
                    )}
                  </div>
                )}
              </section>
              <div className="field-groups">
                {GROUPS.map((group) => (
                  <section className="field-group" key={group.id}>
                    <h3>{group.title}</h3>
                    {group.fields.map((name) => {
                      const field = caseState.extraction?.[group.key]?.[name];
                      return field ? <FieldCard key={name} fieldPath={`${group.key}.${name}`} label={LABELS[name]} field={field} onShow={selectSource} onSave={saveField} onApprove={approveField} busy={busy !== null} /> : null;
                    })}
                  </section>
                ))}
              </div>
              <section className="report-draft-panel" aria-label="Yerel rapor taslağı">
                <div className="report-draft-heading">
                  <div><p className="eyebrow">RAPOR TASLAĞI</p><h3>Önizleme ve kayıt</h3></div>
                </div>
                <p className="report-draft-note">Taslak yalnızca onayladığınız bilgilerle hazırlanır. Kaynakta olmayan bilgi eklenmez.</p>
                {!caseState.report_draft_eligibility.ready && <p className="report-draft-warning">Taslak için {caseState.report_draft_eligibility.missing_approvals.length} kritik alanın onayı eksik veya alan çelişkili.</p>}
                <button className="primary process-button" onClick={createReportDraft} disabled={!caseState.report_draft_eligibility.ready || busy !== null} title={!caseState.report_draft_eligibility.ready ? "Eksik veya onaylanmamış kritik alanları tamamlayın." : "Onaylanan bilgilerle rapor taslağını hazırla."}>
                  {busy === "draft" ? "Rapor taslağı hazırlanıyor…" : "Rapor taslağını hazırla"}
                </button>
                {reportDraft && (
                  <article className="draft-preview">
                    <div className="draft-saved"><b>Taslak kaydedildi</b></div>
                    {reportDraft.sections.map((section) => (
                      <section key={section.id} className="draft-section">
                        <h4>{section.title}</h4>
                        <p>{section.text}</p>
                        <div className="draft-sources">{section.source_field_paths.map((path) => <button key={path} onClick={() => focusField(path, caseState, selectSource)}>{LABELS[path.split(".")[1]] ?? path}</button>)}</div>
                      </section>
                    ))}
                    <p className="report-draft-warning">Bu taslak incelemeniz içindir. Rapor dosyasını oluşturmadan önce manuel SAYI ve muayene bilgilerini de kontrol etmeniz gerekir.</p>
                  </article>
                )}
              </section>
              <WordGenerationPanel
                status={docxStatus}
                input={docxInput}
                onInputChange={(name, value) => { setDocxInput((current) => ({ ...current, [name]: value })); setDocxConfirmed(false); }}
                confirmed={docxConfirmed}
                onConfirmedChange={setDocxConfirmed}
                onSave={saveDocxInput}
                onCreate={createDocx}
                busy={busy !== null}
                approvalsReady={caseState.report_draft_eligibility.ready}
                generated={generatedDocx}
                reports={caseState.docx_reports}
              />
            </>
          )}
        </aside>
      </section>
      <footer className="app-footer">
        <span><b>Rapor Agent</b> · Kaynakları gösteren rapor çalışma alanı</span>
        <span>Hasta verisi bu cihazdan ayrılmaz · Nihai değerlendirme kullanıcı sorumluluğundadır</span>
      </footer>
    </main>
  );
}

function WordGenerationPanel({
  status,
  input,
  onInputChange,
  confirmed,
  onConfirmedChange,
  onSave,
  onCreate,
  busy,
  approvalsReady,
  generated,
  reports,
}: {
  status: DocxStatus | null;
  input: DocxInput;
  onInputChange: (name: keyof DocxInput, value: string) => void;
  confirmed: boolean;
  onConfirmedChange: (value: boolean) => void;
  onSave: () => void;
  onCreate: () => void;
  busy: boolean;
  approvalsReady: boolean;
  generated: DocxReport | null;
  reports: DocxReport[];
}) {
  const activeReports = reports.filter((report) => report.status === "review_required");
  const newest = generated ?? activeReports.at(-1) ?? null;
  const inputReady = Object.values(input).every((value) => value.trim().length > 0);

  return (
    <section className={`docx-gate ${status?.available ? "ready" : ""}`} aria-label="Rapor dosyası oluşturma">
      <div><p className="eyebrow">SON KONTROL</p><h3>{status?.available ? "Kurumsal rapor dosyasını oluştur" : "Belge oluşturma kullanılamıyor"}</h3></div>
      <p>Onayladığınız bilgiler kurumun rapor şablonuna aktarılır. SAYI alanını kurum kaydındaki biçimiyle siz girersiniz.</p>
      {!status && <p className="docx-blocker">Belge oluşturma durumu kontrol edilemedi. Uygulamayı yeniden başlatıp tekrar deneyin.</p>}
      {status?.blockers.map((blocker) => <p className="docx-blocker" key={blocker.code}>{documentCreationBlockerMessage(blocker.code, blocker.message)}</p>)}
      {status?.available && (
        <>
          {!approvalsReady && <p className="report-draft-warning">Rapor dosyası için önce tüm kritik bilgileri düzeltip onaylayın.</p>}
          <div className="docx-form">
            <label>SAYI (manuel) *
              <input value={input.document_number} placeholder="Kurumdaki SAYI değerini aynen girin" onChange={(event) => onInputChange("document_number", event.target.value)} disabled={busy} maxLength={80} autoComplete="off" required />
              <small>Bu alanı siz doldurursunuz; uygulama numara üretmez veya önermez.</small>
            </label>
            <label>Rapor düzenleme tarihi *
              <input value={input.document_date} placeholder="GG.AA.YYYY" onChange={(event) => onInputChange("document_date", event.target.value)} disabled={busy} maxLength={20} inputMode="numeric" autoComplete="off" required />
            </label>
            <label>Muayene tarihi ve saati *
              <input value={input.examination_date} placeholder="GG.AA.YYYY SS:DD" onChange={(event) => onInputChange("examination_date", event.target.value)} disabled={busy} maxLength={30} inputMode="numeric" autoComplete="off" required />
            </label>
            <label className="docx-history">Anamnez ve olay öyküsü *
              <textarea value={input.history} rows={4} onChange={(event) => onInputChange("history", event.target.value)} disabled={busy} maxLength={4000} required />
            </label>
            <label className="docx-history">Güncel muayene bulguları *
              <textarea value={input.current_exam_findings} rows={4} onChange={(event) => onInputChange("current_exam_findings", event.target.value)} disabled={busy} maxLength={4000} required />
            </label>
          </div>
          <div className="docx-actions">
            <button className="secondary" onClick={onSave} disabled={busy || !inputReady}>Bilgileri kaydet</button>
            <label className="docx-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => onConfirmedChange(event.target.checked)} disabled={busy} /> Şablona aktarılacak alanları kontrol ettim ve onaylıyorum.</label>
            <button className="primary" onClick={onCreate} disabled={busy || !approvalsReady || !inputReady || !confirmed} title={!approvalsReady ? "Önce kritik bilgileri onaylayın." : !inputReady ? "Tüm zorunlu rapor alanlarını doldurun." : !confirmed ? "Aktarılacak bilgiler için açık onay gereklidir." : "Kurumsal rapor dosyasını oluştur."}>{busy ? "Rapor dosyası oluşturuluyor…" : "Rapor dosyasını oluştur"}</button>
          </div>
        </>
      )}
      {newest && newest.status === "review_required" && (
        <div className="docx-result" role="status">
          <b>Rapor dosyası oluşturuldu: {newest.file_name}</b>
          <a className="primary download-link" href={assetUrl(newest.download_endpoint)}>Rapor dosyasını indir</a>
        </div>
      )}
      {reports.some((report) => report.status === "superseded") && <p className="docx-blocker">Bilgileri değişen eski rapor dosyaları indirilemez. Güncel bilgilerle yeniden oluşturun.</p>}
    </section>
  );
}

function FieldCard({ fieldPath, label, field, onShow, onSave, onApprove, busy }: { fieldPath: string; label: string; field: EvidenceField; onShow: (fieldPath: string, provenance: Provenance) => void; onSave: (fieldPath: string, value: FieldValue) => void; onApprove: (fieldPath: string) => void; busy: boolean }) {
  const [editing, setEditing] = useState(false);
  const [showTckn, setShowTckn] = useState(false);
  const [draft, setDraft] = useState(displayValue(field.value));
  const canApprove = field.status !== "missing" && field.status !== "conflict" && field.value !== null && field.value !== "" && (!Array.isArray(field.value) || field.value.length > 0);
  const arrayValue = Array.isArray(field.value) || fieldPath === "request.requested_questions";
  const humanisedValue = fieldPath === "medical.life_threat" || fieldPath === "medical.simple_medical_intervention"
    ? field.value === "yes" ? "Evet" : field.value === "no" ? "Hayır" : displayValue(field.value)
    : displayValue(field.value);
  const displayedValue = fieldPath === "patient.tckn" && !showTckn ? maskTckn(field.value, fieldPath) : humanisedValue;

  function startEditing() {
    setDraft(displayValue(field.value));
    setEditing(true);
  }

  return (
    <article className={`field-card ${field.status} ${field.approved ? "approved" : ""} ${field.provenance.ocr_confidence !== null && field.provenance.ocr_confidence < .85 ? "low-confidence" : ""}`}>
      <div className="field-topline"><h4>{label}</h4><span className={`status ${field.status}`}>{FIELD_STATUS_LABELS[field.status]}</span></div>
      {editing ? (
        <>
          <textarea aria-label={`${label} değeri`} value={draft} onChange={(event) => setDraft(event.target.value)} rows={arrayValue ? 3 : 2} />
          <div className="card-actions"><button className="small primary" onClick={() => { onSave(fieldPath, inputToFieldValue(draft, arrayValue)); setEditing(false); }} disabled={busy}>Kaydet</button><button className="small ghost" onClick={() => setEditing(false)}>Vazgeç</button></div>
        </>
      ) : (
        <p className="field-value">{displayedValue}</p>
      )}
      {fieldPath === "patient.tckn" && !editing && <button className="small ghost" onClick={() => setShowTckn((visible) => !visible)}>{showTckn ? "Maskle" : "Açık göster"}</button>}
      <button className="source" onClick={() => onShow(fieldPath, field.provenance)} disabled={!field.provenance.source_document_id}>Kaynak: {field.provenance.page ? `sayfa ${field.provenance.page}` : "yok"} · {field.provenance.ocr_confidence === null ? "Güven belirtilmemiş" : `Okuma güveni %${Math.round(field.provenance.ocr_confidence * 100)}`}</button>
      {field.status === "conflict" && <div className="conflicts">{field.candidates.map((candidate, index) => <button key={index} onClick={() => onShow(fieldPath, candidate.provenance)}>Aday {index + 1}: {displayValue(candidate.value)} · s.{candidate.provenance.page}</button>)}</div>}
      <div className="card-actions">
        {!editing && <button className="small ghost" onClick={startEditing} disabled={busy}>Düzelt</button>}
        {field.approved ? <span className="approved-label">Onaylandı</span> : <button className="small approve" onClick={() => onApprove(fieldPath)} disabled={!canApprove || busy}>Onayla</button>}
      </div>
    </article>
  );
}

function focusField(fieldPath: string, state: CaseState, select: (fieldPath: string, provenance: Provenance) => void) {
  const [group, field] = fieldPath.split(".");
  const selected = state.extraction?.[group as keyof Pick<NonNullable<CaseState["extraction"]>, "patient" | "request" | "medical">]?.[field];
  if (selected) select(fieldPath, selected.provenance);
}

function samePolygon(left: Provenance["polygon"] | undefined, right: Provenance["polygon"]): boolean {
  return Boolean(left && right && JSON.stringify(left) === JSON.stringify(right));
}
