import { ChangeEvent, PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { api, assetUrl } from "./api";
import { cropPointFromSvg, MINIMUM_CROP_PIXELS, normaliseCrop } from "./crop-utils";
import { displayValue, inputToFieldValue, maskTckn } from "./field-utils";
import type { CaseDocument, CaseState, CropSelection, DocxInput, DocxReport, DocxStatus, EvidenceField, FieldValue, LlmStatus, Provenance, ReportDraft } from "./types";

const GROUPS = [
  { title: "Hasta kimliği", key: "patient", fields: ["full_name", "tckn", "birth_place", "birth_date"] },
  { title: "Üst yazı", key: "request", fields: ["sender_authority", "letter_date", "letter_number", "incident", "requested_questions"] },
  {
    title: "Genel adli muayene",
    key: "medical",
    fields: ["issuing_institution", "protocol_number", "report_date", "report_number", "incident_date_time", "incident_type", "clinical_findings", "life_threat", "simple_medical_intervention"],
  },
  { title: "Ek klinik belgeler", key: "medical", fields: ["epicrisis_summary", "department_exam_summary"] },
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
  invalid_tckn: "TCKN checksum doğrulamasından geçmedi",
} as const;

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
  const [showOcr, setShowOcr] = useState(true);
  const [cropMode, setCropMode] = useState(false);
  const [cropDraft, setCropDraft] = useState<CropSelection | null>(null);
  const [reportDraft, setReportDraft] = useState<ReportDraft | null>(null);
  const [llmStatus, setLlmStatus] = useState<LlmStatus | null>(null);
  const [docxStatus, setDocxStatus] = useState<DocxStatus | null>(null);
  const [docxInput, setDocxInput] = useState<DocxInput>(() => defaultDocxInput());
  const [docxConfirmed, setDocxConfirmed] = useState(false);
  const [generatedDocx, setGeneratedDocx] = useState<DocxReport | null>(null);
  const [bulkApprovalResult, setBulkApprovalResult] = useState<{ approved: number; skipped: Array<{ field_path: string; reason: keyof typeof BULK_SKIP_LABELS }> } | null>(null);
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
    void api.llmStatus().then(setLlmStatus).catch(() => setLlmStatus(null));
    void api.docxStatus().then(setDocxStatus).catch(() => setDocxStatus(null));
  }, []);

  useEffect(() => {
    if (caseState?.docx_input?.values) setDocxInput(caseState.docx_input.values);
  }, [caseState?.case_id, caseState?.docx_input]);

  async function run(label: string, action: () => Promise<CaseState>) {
    setBusy(label);
    setError(null);
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
    void run("demo", api.createDemoCase);
  }

  function processCase() {
    if (!caseState) return;
    setReportDraft(null);
    setBulkApprovalResult(null);
    setGeneratedDocx(null);
    void run("process", () => api.process(caseState.case_id));
  }

  function uploadFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    void (async () => {
      setBusy("upload");
      setError(null);
      try {
        let current = caseState ?? (await api.createCase());
        for (const file of files) current = await api.upload(current.case_id, file);
        setCaseState(current);
        setReportDraft(null);
        setBulkApprovalResult(null);
        setGeneratedDocx(null);
        setDocxConfirmed(false);
        setSelectedDocumentId(current.documents.at(-1)?.document_id ?? null);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Yükleme tamamlanamadı.");
      } finally {
        setBusy(null);
        event.target.value = "";
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
      "Bu işlem, kaynakta değeri bulunan tüm OCR alanlarını kullanıcı onayıyla işaretler. Eksik, çelişkili ve geçersiz TCKN alanları atlanır. Onaylamak istiyor musunuz?",
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
        void api.llmStatus().then(setLlmStatus).catch(() => setLlmStatus(null));
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
      "Manuel SAYI, güncel muayene bilgileri ve kullanıcı onaylı OCR alanları kurumsal Word şablonuna aktarılacak. Word taslağını oluşturmak istiyor musunuz?",
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
        setError(caught instanceof Error ? caught.message : "Word taslağı oluşturulamadı.");
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

  return (
    <main>
      <header className="app-header">
        <div>
          <p className="eyebrow">YEREL İŞLEME · İLK DİKEY DİLİM</p>
          <h1>Kaynaklı alan doğrulama</h1>
          <p className="subtitle">Yükleme → sayfa → OCR poligonu → kaynaklı çıkarım → kullanıcı onayı → yerel taslak</p>
        </div>
        <div className="header-actions">
          <span className="privacy-badge">Buluta veri gönderilmez</span>
          <button className="secondary" onClick={createDemo} disabled={busy !== null}>
            Sentetik vakayı yükle
          </button>
        </div>
      </header>

      {error && <div className="alert error" role="alert">{error}</div>}

      <section className="workflow" aria-label="İşlem aşamaları">
        {[
          ["1", "Belgeler"],
          ["2", "Sayfa görüntüsü"],
          ["3", "OCR ve alan çıkarımı"],
          ["4", "Kullanıcı onayı"],
          ["5", "Yerel taslak"],
          ["6", "Word taslağı"],
        ].map(([number, label]) => <span key={number}><b>{number}</b>{label}</span>)}
      </section>

      <section className="workspace">
        <aside className="documents-panel panel">
          <div className="panel-heading">
            <div><p className="eyebrow">VAKA BELGELERİ</p><h2>Yükleme</h2></div>
            {caseState && <code>{caseState.case_id.slice(0, 8)}</code>}
          </div>
          <label className="upload-zone">
            <input type="file" accept="application/pdf,image/png,image/jpeg" multiple onChange={uploadFiles} disabled={busy !== null} />
            <span>PDF, PNG veya JPEG bırakın</span>
            <small>Dosya imzası, 20 MB ve 25 sayfa sınırı sunucuda doğrulanır.</small>
          </label>
          {!caseState?.documents.length && (
            <div className="empty-state">Yüklediğiniz dosya yalnızca bu bilgisayarda işlenir. Depodaki otomatik testler ve örnek fixture’lar ise yalnızca sentetik belge kullanır.</div>
          )}
          <div className="document-list">
            {caseState?.documents.map((document) => (
              <article className={`document-card ${selectedDocument?.document_id === document.document_id ? "active" : ""}`} key={document.document_id}>
                <button className="document-select" onClick={() => setSelectedDocumentId(document.document_id)}>
                  <strong>{document.file_name}</strong>
                  <span>{document.pages.length} sayfa · {document.is_synthetic ? "sentetik" : "yerel dosya"}</span>
                </button>
                <label className="type-select">
                  <span>Belge türü</span>
                  <select value={document.type} onChange={(event) => updateType(document.document_id, event.target.value as CaseDocument["type"])} disabled={busy !== null}>
                    {Object.entries(TYPE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                  </select>
                </label>
                <div className="document-meta">
                  <span className={`status ${document.ocr_status}`}>{document.ocr_status === "completed" ? "OCR tamamlandı" : document.ocr_status === "error" ? "OCR hatası" : "OCR bekliyor"}</span>
                  {document.classification_confidence !== null && <span>%{Math.round(document.classification_confidence * 100)} tür güveni</span>}
                </div>
                {document.ocr_error && <small className="error-text">{document.ocr_error}</small>}
                <div className="document-actions">
                  <button className="small danger" onClick={() => deleteDocument(document.document_id, document.file_name)} disabled={busy !== null}>Belgeyi sil</button>
                </div>
              </article>
            ))}
          </div>
          <button className="primary process-button" onClick={processCase} disabled={!caseState?.documents.length || busy !== null}>
            {busy === "process" ? "Yerel OCR çalışıyor…" : "OCR ve alan çıkarımını çalıştır"}
          </button>
          <small className="local-note">Yerel OCR kullanıma hazır değilse işlem durur; sentetik dışı belgelerde otomatik alternatif kullanılmaz.</small>
        </aside>

        <section className="viewer-panel panel">
          <div className="panel-heading viewer-heading">
            <div><p className="eyebrow">KAYNAK SAYFA</p><h2>{selectedDocument?.file_name ?? "Sayfa seçilmedi"}</h2></div>
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
              <label className="toggle"><input type="checkbox" checked={showOcr} onChange={(event) => setShowOcr(event.target.checked)} /> OCR poligonları</label>
            </div>
          </div>
          {selectedPage && selectedDocument ? (
            <div className="page-frame">
              <svg className={`page-svg ${cropMode ? "cropping" : ""}`} viewBox={`0 0 ${selectedPage.width ?? 1000} ${selectedPage.height ?? 1400}`} role="img" aria-label={`${selectedDocument.file_name}, sayfa ${selectedPage.page}`} onPointerDown={startCrop} onPointerMove={updateCrop} onPointerUp={finishCrop} onPointerCancel={finishCrop} onLostPointerCapture={finishCrop}>
                <image href={assetUrl(`${selectedPage.image_endpoint}?revision=${selectedPage.transform?.revision ?? 0}`)} width="100%" height="100%" preserveAspectRatio="none" />
                {showOcr && selectedDocument.ocr_lines.filter((line) => line.page === selectedPage.page).map((line) => {
                  const selected = samePolygon(selectedSource?.provenance.polygon, line.polygon);
                  return <polygon key={`${line.reading_order}-${line.text}`} points={line.polygon.map((point) => point.join(",")).join(" ")} className={selected ? "selected" : ""} />;
                })}
                {normalisedCrop && <rect className="crop-selection" x={normalisedCrop.left * (selectedPage.width ?? 1000)} y={normalisedCrop.top * (selectedPage.height ?? 1400)} width={(normalisedCrop.right - normalisedCrop.left) * (selectedPage.width ?? 1000)} height={(normalisedCrop.bottom - normalisedCrop.top) * (selectedPage.height ?? 1400)} />}
              </svg>
              {!selectedDocument.ocr_lines.length && <div className="viewer-message">OCR tamamlandığında kaynak metin poligonları burada gösterilir.</div>}
              {cropMode && <div className="crop-instruction">Kırpılacak alanı sayfa üzerinde sürükleyin (en az {MINIMUM_CROP_PIXELS} × {MINIMUM_CROP_PIXELS} piksel). Uygulandığında eski OCR ve çıkarım geçersizleşir.</div>}
            </div>
          ) : <div className="viewer-empty">Bir belge yüklediğinizde sayfa görüntüsü burada açılır.</div>}
          {selectedSource?.provenance.evidence_text && <div className="evidence-bar">Seçili kanıt: “{selectedSource.provenance.evidence_text}”</div>}
        </section>

        <aside className="review-panel panel">
          <div className="panel-heading">
            <div><p className="eyebrow">DOĞRULAMA</p><h2>Alanlar ve onay</h2></div>
            {caseState?.extraction && <span className="schema-chip">Şema {caseState.extraction.schema_version}</span>}
          </div>
          {!caseState?.extraction && <div className="empty-state">OCR tamamlandığında alanlar kaynakları ve güven değerleriyle burada görünür.</div>}
          {caseState?.extraction && (
            <>
              <div className="warnings">
                {caseState.extraction.warnings.map((warning, index) => (
                  <button className={`warning ${warning.severity}`} key={`${warning.code}-${index}`} onClick={() => warning.field_path && focusField(warning.field_path, caseState, selectSource)}>
                    <b>{warning.severity === "blocking" ? "Engel" : warning.severity === "warning" ? "Uyarı" : "Bilgi"}</b>{warning.message}
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
                  <section className="field-group" key={group.key}>
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
                  <div><p className="eyebrow">YEREL QWEN TASLAĞI</p><h3>Önizleme ve kayıt</h3></div>
                  <span className={`model-status ${llmStatus?.loaded ? "ready" : ""}`}>
                    {llmStatus?.loaded ? "model yüklü" : llmStatus?.model_files_ready && llmStatus.runtime_ready ? "model hazır" : "model hazır değil"}
                  </span>
                </div>
                <p className="report-draft-note">Qwen yalnızca onaylı alanların bölüm planını üretir. Taslak metni, kaynakta olmayan bilgi eklenmemesi için sunucuda sabit cümlelerle kurulur ve bu bilgisayara kaydedilir.</p>
                {!caseState.report_draft_eligibility.ready && <p className="report-draft-warning">Taslak için {caseState.report_draft_eligibility.missing_approvals.length} kritik alanın onayı eksik veya alan çelişkili.</p>}
                <button className="primary process-button" onClick={createReportDraft} disabled={!caseState.report_draft_eligibility.ready || busy !== null} title={!caseState.report_draft_eligibility.ready ? "Eksik veya onaylanmamış kritik alanları tamamlayın." : "Yerel Qwen ile plan oluşturup taslağı yerel depoya kaydet."}>
                  {busy === "draft" ? "Yerel Qwen taslak planlıyor…" : "Taslağı üret ve yerelde kaydet"}
                </button>
                {reportDraft && (
                  <article className="draft-preview">
                    <div className="draft-saved"><b>Kaydedildi</b><span>{reportDraft.generation.model_name} · {reportDraft.generation.prompt_version}</span></div>
                    {reportDraft.sections.map((section) => (
                      <section key={section.id} className="draft-section">
                        <h4>{section.title}</h4>
                        <p>{section.text}</p>
                        <div className="draft-sources">{section.source_field_paths.map((path) => <button key={path} onClick={() => focusField(path, caseState, selectSource)}>{LABELS[path.split(".")[1]] ?? path}</button>)}</div>
                      </section>
                    ))}
                    <p className="report-draft-warning">Bu kayıt kullanıcı incelemesi gerektiren yerel taslaktır. Word üretimi ayrıca manuel SAYI ve şablona özgü muayene alanlarının onayını gerektirir.</p>
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

  return (
    <section className={`docx-gate ${status?.available ? "ready" : ""}`} aria-label="Word üretimi">
      <div><p className="eyebrow">WORD TASLAĞI</p><h3>{status?.available ? "Kurumsal şablonla üret" : "Word üretimi kullanıma hazır değil"}</h3></div>
      <p>Asıl kurum şablonunun sayfa düzeni korunur. OCR alanları yalnızca kaynaklı ve kullanıcı onaylıysa aktarılır; SAYI uygulama tarafından üretilmez.</p>
      {!status && <p className="docx-blocker">Yerel Word üretim durumu okunamadı.</p>}
      {status?.blockers.map((blocker) => <p className="docx-blocker" key={blocker.code}>{blocker.message}</p>)}
      {status?.available && (
        <>
          <p className="docx-contract">Şablon: {status.template?.file_name} · {status.template?.mapped_field_count} alan. Uygulama SAYI numarası üretmez.</p>
          {!approvalsReady && <p className="report-draft-warning">Word için önce tüm kritik OCR alanlarını düzeltip onaylayın.</p>}
          <div className="docx-form">
            <label>SAYI (manuel) *
              <input value={input.document_number} placeholder="Kurumdaki SAYI değerini aynen girin" onChange={(event) => onInputChange("document_number", event.target.value)} disabled={busy} />
              <small>Bu alanı siz doldurursunuz; uygulama numara üretmez veya önermez.</small>
            </label>
            <label>Rapor düzenleme tarihi *
              <input value={input.document_date} placeholder="GG.AA.YYYY" onChange={(event) => onInputChange("document_date", event.target.value)} disabled={busy} />
            </label>
            <label>Muayene tarihi ve saati *
              <input value={input.examination_date} placeholder="GG.AA.YYYY SS:DD" onChange={(event) => onInputChange("examination_date", event.target.value)} disabled={busy} />
            </label>
            <label className="docx-history">Anamnez ve olay öyküsü *
              <textarea value={input.history} rows={4} onChange={(event) => onInputChange("history", event.target.value)} disabled={busy} />
            </label>
            <label className="docx-history">Güncel muayene bulguları *
              <textarea value={input.current_exam_findings} rows={4} onChange={(event) => onInputChange("current_exam_findings", event.target.value)} disabled={busy} />
            </label>
          </div>
          <div className="docx-actions">
            <button className="secondary" onClick={onSave} disabled={busy}>Word bilgilerini yerelde kaydet</button>
            <label className="docx-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => onConfirmedChange(event.target.checked)} disabled={busy} /> Şablona aktarılacak alanları kontrol ettim ve onaylıyorum.</label>
            <button className="primary" onClick={onCreate} disabled={busy || !approvalsReady || !confirmed} title={!approvalsReady ? "Önce kritik OCR alanlarını onaylayın." : !confirmed ? "Aktarılacak alanlar için açık onay gereklidir." : "Kurumsal Word taslağını oluştur."}>{busy ? "Word taslağı oluşturuluyor…" : "Word taslağını oluştur"}</button>
          </div>
        </>
      )}
      {newest && newest.status === "review_required" && (
        <div className="docx-result" role="status">
          <b>Word taslağı yerelde kaydedildi: {newest.file_name}</b>
          <a className="primary download-link" href={assetUrl(newest.download_endpoint)}>Word taslağını indir</a>
        </div>
      )}
      {reports.some((report) => report.status === "superseded") && <p className="docx-blocker">Kaynak alanı veya Word girdisi değişen eski taslaklar indirilemez; güncel verilerle yeniden üretin.</p>}
    </section>
  );
}

function FieldCard({ fieldPath, label, field, onShow, onSave, onApprove, busy }: { fieldPath: string; label: string; field: EvidenceField; onShow: (fieldPath: string, provenance: Provenance) => void; onSave: (fieldPath: string, value: FieldValue) => void; onApprove: (fieldPath: string) => void; busy: boolean }) {
  const [editing, setEditing] = useState(false);
  const [showTckn, setShowTckn] = useState(false);
  const [draft, setDraft] = useState(displayValue(field.value));
  const canApprove = field.status !== "missing" && field.status !== "conflict" && field.value !== null;
  const arrayValue = Array.isArray(field.value) || fieldPath === "request.requested_questions";
  const displayedValue = fieldPath === "patient.tckn" && showTckn ? displayValue(field.value) : maskTckn(field.value, fieldPath);

  function startEditing() {
    setDraft(displayValue(field.value));
    setEditing(true);
  }

  return (
    <article className={`field-card ${field.status} ${field.approved ? "approved" : ""}`}>
      <div className="field-topline"><h4>{label}</h4><span className={`status ${field.status}`}>{field.status === "user_corrected" ? "düzeltildi" : field.status}</span></div>
      {editing ? (
        <>
          <textarea aria-label={`${label} değeri`} value={draft} onChange={(event) => setDraft(event.target.value)} rows={arrayValue ? 3 : 2} />
          <div className="card-actions"><button className="small primary" onClick={() => { onSave(fieldPath, inputToFieldValue(draft, arrayValue)); setEditing(false); }} disabled={busy}>Kaydet</button><button className="small ghost" onClick={() => setEditing(false)}>Vazgeç</button></div>
        </>
      ) : (
        <p className="field-value">{displayedValue}</p>
      )}
      {fieldPath === "patient.tckn" && !editing && <button className="small ghost" onClick={() => setShowTckn((visible) => !visible)}>{showTckn ? "Maskle" : "Açık göster"}</button>}
      <button className="source" onClick={() => onShow(fieldPath, field.provenance)} disabled={!field.provenance.source_document_id}>Kaynak: {field.provenance.page ? `sayfa ${field.provenance.page}` : "yok"} · {field.provenance.ocr_confidence === null ? "—" : `%${Math.round(field.provenance.ocr_confidence * 100)} OCR`}</button>
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
