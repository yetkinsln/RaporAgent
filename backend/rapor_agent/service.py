"""Yukleme, sayfalastirma, OCR, cikarma ve kullanici onayi uygulama servisi."""

from __future__ import annotations

import copy
import os
import uuid
from pathlib import Path
from typing import Any

from .docx_generation import DocxGenerationError, InstitutionalDocxGenerator, validate_word_input
from .extraction import extract_case, get_field, refresh_warnings, set_field_value, tckn_is_valid
from .ocr import OCRProvider, OcrProviderError, OcrProviderUnavailable, PaddleOcrProvider
from .reporting import (
    LocalLLMOutputInvalid,
    LocalLLMUnavailable,
    Qwen3LocalReportProvider,
    ReportEligibilityError,
    ReportError,
    ReportPlanProvider,
    build_approved_context,
    draft_eligibility,
    render_saved_draft,
)
from .schema import CanonicalSchemaError, validate_extraction
from .storage import CaseStore, StorageError
from .synthetic import demo_documents, render_page_png


class ServiceError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400, code: str = "invalid_request") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


DOCUMENT_TYPES = {
    "cover_letter",
    "general_forensic_exam",
    "epicrisis",
    "department_exam_note",
    "other",
    "unknown",
}


class CaseService:
    def __init__(
        self,
        data_dir: Path,
        ocr_provider: OCRProvider | None = None,
        report_provider: ReportPlanProvider | None = None,
        docx_generator: InstitutionalDocxGenerator | None = None,
    ) -> None:
        self.store = CaseStore(data_dir)
        self.ocr_provider = ocr_provider or PaddleOcrProvider()
        self.report_provider = report_provider or Qwen3LocalReportProvider()
        self.docx_generator = docx_generator or InstitutionalDocxGenerator.from_configured_directory(
            os.environ.get("RAPOR_AGENT_TEMPLATE_DIR")
        )

    def create_case(self) -> dict[str, Any]:
        return self._public_case(self.store.create_case())

    def create_demo_case(self) -> dict[str, Any]:
        case = self.store.create_case()
        for fixture in demo_documents():
            document_id = uuid.uuid4().hex
            page_path = self.store.store_demo_page(
                case["case_id"],
                document_id,
                render_page_png(fixture["lines"], fixture["file_name"]),
            )
            case["documents"].append(
                {
                    "document_id": document_id,
                    "file_name": fixture["file_name"],
                    "mime_type": "image/png",
                    "type": fixture["type"],
                    "classification_confidence": None,
                    "user_confirmed_type": False,
                    "pages": [
                        self.store.page_record(document_id, 1, page_path, 1000, 900)
                    ],
                    "ocr_status": "not_started",
                    "ocr_error": None,
                    "ocr_lines": [],
                    "ocr_history": [],
                    "synthetic_ocr_lines": fixture["lines"],
                    "is_synthetic": True,
                }
            )
        case["audit"].append({"event": "synthetic_demo_created"})
        self.store.save_case(case)
        return self._public_case(case)

    def get_case(self, case_id: str) -> dict[str, Any]:
        try:
            return self._public_case(self.store.load_case(case_id))
        except StorageError as error:
            raise ServiceError(str(error), status_code=404, code="case_not_found") from error

    def upload_document(self, case_id: str, file_name: str, payload: bytes) -> dict[str, Any]:
        try:
            case = self.store.load_case(case_id)
            stored = self.store.store_upload(case_id, file_name, payload)
            extension = Path(stored["file_path"]).suffix.lstrip(".")
            if stored["mime_type"] == "application/pdf":
                pages = self.store.render_pdf_pages(case_id, stored["document_id"], stored["file_path"])
            else:
                pages = self.store.create_image_page(case_id, stored["document_id"], stored["file_path"], extension)
        except StorageError as error:
            raise ServiceError(str(error), status_code=400, code="upload_rejected") from error

        case["documents"].append(
            {
                **stored,
                "type": "unknown",
                "classification_confidence": None,
                "user_confirmed_type": False,
                "pages": pages,
                "ocr_status": "not_started",
                "ocr_error": None,
                "ocr_lines": [],
                "ocr_history": [],
                "is_synthetic": False,
            }
        )
        self._invalidate_report_drafts(case, reason="document_uploaded")
        self._invalidate_docx_reports(case, reason="document_uploaded")
        case["stage"] = "documents"
        case["audit"].append({"event": "document_uploaded", "document_id": stored["document_id"]})
        self.store.save_case(case)
        return self._public_case(case)

    def confirm_document_type(self, case_id: str, document_id: str, document_type: str) -> dict[str, Any]:
        if document_type not in DOCUMENT_TYPES:
            raise ServiceError("Bilinmeyen belge türü seçildi.", code="invalid_document_type")
        case = self._load_case(case_id)
        document = self._document(case, document_id)
        document["type"] = document_type
        document["user_confirmed_type"] = True
        if case.get("extraction") and all(item["ocr_status"] == "completed" for item in case["documents"]):
            self._extract(case)
        self._invalidate_report_drafts(case, reason="document_type_changed")
        self._invalidate_docx_reports(case, reason="document_type_changed")
        case["audit"].append({"event": "document_type_confirmed", "document_id": document_id})
        self.store.save_case(case)
        return self._public_case(case)

    def delete_document(self, case_id: str, document_id: str) -> dict[str, Any]:
        case = self._load_case(case_id)
        self._document(case, document_id)
        try:
            self.store.delete_document_files(case_id, document_id)
        except StorageError as error:
            raise ServiceError(str(error), status_code=500, code="document_delete_failed") from error

        case["documents"] = [item for item in case["documents"] if item["document_id"] != document_id]
        # Kalan belgeler OCR'dan geçmiş olsa dahi alan çıkarımı silinen belgenin
        # kanıtlarını taşıyabilir; kullanıcı yeniden işleyene kadar gösterilmez.
        case["extraction"] = None
        self._invalidate_report_drafts(case, reason="document_deleted")
        self._invalidate_docx_reports(case, reason="document_deleted")
        case["stage"] = "documents"
        case["audit"].append({"event": "document_deleted", "document_id": document_id})
        self.store.save_case(case)
        return self._public_case(case)

    def process(self, case_id: str) -> dict[str, Any]:
        case = self._load_case(case_id)
        if not case["documents"]:
            raise ServiceError("İşlenecek belge yok.", code="no_documents")
        for document in case["documents"]:
            if document["ocr_status"] == "completed":
                continue
            try:
                document["ocr_lines"] = self._read_document(case, document)
                document["ocr_status"] = "completed"
                document["ocr_error"] = None
            except OcrProviderUnavailable as error:
                document["ocr_status"] = "error"
                document["ocr_error"] = "Yerel OCR kullanıma hazır değil. Kurulumu kontrol edip yeniden deneyin."
                self.store.save_case(case)
                raise ServiceError(str(error), status_code=503, code="ocr_unavailable") from error
            except (OcrProviderError, StorageError) as error:
                document["ocr_status"] = "error"
                document["ocr_error"] = "OCR tamamlanamadı. Sayfayı ve yerel OCR kurulumunu kontrol edin."
                self.store.save_case(case)
                raise ServiceError(str(error), status_code=422, code="ocr_failed") from error

        self._extract(case)
        self._invalidate_report_drafts(case, reason="ocr_reprocessed")
        self._invalidate_docx_reports(case, reason="ocr_reprocessed")
        case["stage"] = "review"
        case["audit"].append({"event": "ocr_and_rule_extraction_completed"})
        self.store.save_case(case)
        return self._public_case(case)

    def change_field(self, case_id: str, field_path: str, value: str | list[str] | None) -> dict[str, Any]:
        case = self._load_case(case_id)
        extraction = self._extraction(case)
        try:
            set_field_value(extraction, field_path, value)
        except KeyError as error:
            raise ServiceError("Alan yolu kanonik şemada tanımlı değil.", code="unknown_field") from error
        refresh_warnings(extraction)
        self._validate(extraction)
        self._invalidate_report_drafts(case, reason="field_corrected")
        self._invalidate_docx_reports(case, reason="field_corrected")
        case["audit"].append({"event": "field_corrected", "field_path": field_path})
        self.store.save_case(case)
        return self._public_case(case)

    def approve_field(self, case_id: str, field_path: str) -> dict[str, Any]:
        case = self._load_case(case_id)
        extraction = self._extraction(case)
        try:
            field = get_field(extraction, field_path)
        except KeyError as error:
            raise ServiceError("Alan yolu kanonik şemada tanımlı değil.", code="unknown_field") from error
        if field["status"] in {"missing", "conflict"} or field["value"] in (None, "", []):
            raise ServiceError("Eksik veya çelişkili alan onaylanamaz; önce kullanıcı düzeltmesi gerekir.", code="field_not_approvable")
        if field_path == "patient.tckn" and not tckn_is_valid(str(field["value"])):
            raise ServiceError("TCKN checksum doğrulamasından geçmedi; otomatik veya kullanıcı onayı kaydedilmedi.", code="invalid_tckn")
        field["approved"] = True
        self._validate(extraction)
        case["audit"].append({"event": "field_approved", "field_path": field_path})
        self.store.save_case(case)
        return self._public_case(case)

    def approve_all_fields(self, case_id: str) -> dict[str, Any]:
        """Kullanıcının açık toplu onay isteğini, onaylanamayacak alanları atlayarak işler."""
        case = self._load_case(case_id)
        extraction = self._extraction(case)
        approved_paths: list[str] = []
        skipped: list[dict[str, str]] = []

        for group in ("patient", "request", "medical"):
            for name, field in extraction[group].items():
                field_path = f"{group}.{name}"
                if field["approved"]:
                    continue
                if field["status"] == "missing" or field["value"] in (None, "", []):
                    skipped.append({"field_path": field_path, "reason": "missing"})
                    continue
                if field["status"] == "conflict":
                    skipped.append({"field_path": field_path, "reason": "conflict"})
                    continue
                if field_path == "patient.tckn" and not tckn_is_valid(str(field["value"])):
                    skipped.append({"field_path": field_path, "reason": "invalid_tckn"})
                    continue
                field["approved"] = True
                approved_paths.append(field_path)

        self._validate(extraction)
        case["audit"].append(
            {
                "event": "fields_bulk_approved",
                "approved_count": len(approved_paths),
                "skipped": [item["field_path"] for item in skipped],
            }
        )
        self.store.save_case(case)
        return {"case": self._public_case(case), "approved_field_paths": approved_paths, "skipped": skipped}

    def docx_status(self) -> dict[str, Any]:
        """Kurumsal şablon sözleşmesinin yerel kullanım durumunu döndürür."""
        return self.docx_generator.status()

    def save_docx_input(self, case_id: str, values: dict[str, str]) -> dict[str, Any]:
        case = self._load_case(case_id)
        try:
            self.docx_generator.load_contract()
            normalised = validate_word_input(values)
        except DocxGenerationError as error:
            raise ServiceError(str(error), status_code=422, code=error.code) from error
        case["docx_input"] = {"values": normalised, "status": "review_required"}
        self._invalidate_docx_reports(case, reason="docx_input_changed")
        case["audit"].append({"event": "docx_input_saved", "field_names": sorted(normalised)})
        self.store.save_case(case)
        return self._public_case(case)

    def create_docx(self, case_id: str, *, confirmed: bool) -> dict[str, Any]:
        case = self._load_case(case_id)
        if not confirmed:
            raise ServiceError(
                "Word üretiminden önce şablona aktarılacak bilgileri açıkça onaylayın.",
                status_code=409,
                code="docx_confirmation_required",
            )
        status = self.docx_status()
        if not status["available"]:
            blocker = status["blockers"][0]
            raise ServiceError(blocker["message"], status_code=409, code=blocker["code"])
        extraction = self._extraction(case)
        eligibility = draft_eligibility(extraction)
        if not eligibility["ready"]:
            raise ServiceError(
                "Word üretmeden önce eksik, çelişkili veya onaylanmamış kritik alanları tamamlayın.",
                status_code=409,
                code="docx_approval_required",
            )
        input_record = case.get("docx_input")
        if not isinstance(input_record, dict) or not isinstance(input_record.get("values"), dict):
            raise ServiceError(
                "Word üretimi için manuel SAYI ve güncel muayene bilgilerini önce kaydedin.",
                status_code=409,
                code="docx_input_incomplete",
            )
        temporary: Path | None = None
        try:
            temporary, contract, source_paths = self.docx_generator.render(
                extraction=extraction,
                word_input=input_record["values"],
                output_dir=self.store.case_dir(case_id) / "derived",
            )
            saved = self.store.save_docx_report(
                case_id,
                str(get_field(extraction, "patient.full_name")["value"]),
                temporary,
            )
        except DocxGenerationError as error:
            raise ServiceError(
                str(error),
                status_code=409 if error.code in {"docx_approval_required", "docx_input_incomplete"} else 422,
                code=error.code,
            ) from error
        except StorageError as error:
            raise ServiceError(str(error), status_code=500, code="docx_storage_failed") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

        report = {
            "report_id": uuid.uuid4().hex,
            "file_name": saved["file_name"],
            "relative_path": saved["relative_path"],
            "status": "review_required",
            "template_sha256": contract.template_hash,
            "mapping_sha256": contract.mapping_hash,
            "source_field_paths": source_paths,
        }
        case.setdefault("docx_reports", []).append(report)
        input_record["status"] = "approved"
        case["audit"].append(
            {
                "event": "docx_generated_after_user_confirmation",
                "report_id": report["report_id"],
                "source_field_paths": source_paths,
            }
        )
        self.store.save_case(case)
        return {"case": self._public_case(case), "report": self._public_docx_report(case_id, report)}

    def docx_report_path(self, case_id: str, report_id: str) -> tuple[Path, str]:
        case = self._load_case(case_id)
        report = next((item for item in case.get("docx_reports", []) if item.get("report_id") == report_id), None)
        if report is None:
            raise ServiceError("Word raporu bulunamadı.", status_code=404, code="docx_report_not_found")
        if report.get("status") != "review_required":
            raise ServiceError(
                "Bu Word taslağının kaynak alanları değişti; indirmek yerine yeniden üretin.",
                status_code=409,
                code="docx_report_superseded",
            )
        try:
            return self.store.docx_report_path(case_id, str(report["relative_path"])), str(report["file_name"])
        except StorageError as error:
            raise ServiceError(str(error), status_code=404, code="docx_report_not_found") from error

    def llm_status(self) -> dict[str, Any]:
        return self.report_provider.status()

    def create_report_draft(self, case_id: str) -> dict[str, Any]:
        case = self._load_case(case_id)
        extraction = self._extraction(case)
        try:
            context = build_approved_context(extraction)
        except ReportEligibilityError as error:
            raise ServiceError(
                "Taslak üretmeden önce eksik, çelişkili veya onaylanmamış kritik alanları tamamlayın.",
                status_code=409,
                code="report_approval_required",
            ) from error

        try:
            plan, model_metadata = self.report_provider.generate_plan(context)
            # Plan yalnızca model sınırını doğrular; taslak metni aşağıda doğrudan
            # onaylı alanlardan kurulur ve model serbest metni taşınmaz.
            draft = render_saved_draft(
                case_id=case_id,
                extraction=extraction,
                approved_context=context,
                model_metadata=model_metadata,
            )
            saved = self.store.save_report_draft(case_id, draft)
        except LocalLLMUnavailable as error:
            raise ServiceError(str(error), status_code=503, code="llm_unavailable") from error
        except LocalLLMOutputInvalid as error:
            raise ServiceError(str(error), status_code=422, code="llm_invalid_structured_output") from error
        except (ReportError, StorageError) as error:
            raise ServiceError(str(error), status_code=422, code="report_draft_not_saved") from error

        case.setdefault("report_drafts", []).append(
            {
                "draft_id": saved["draft_id"],
                "created_at": draft["created_at"],
                "status": draft["status"],
                "model_name": draft["generation"]["model_name"],
                "prompt_version": draft["generation"]["prompt_version"],
            }
        )
        case["audit"].append(
            {
                "event": "report_draft_generated",
                "draft_id": draft["draft_id"],
                "model_name": draft["generation"]["model_name"],
                "prompt_version": draft["generation"]["prompt_version"],
            }
        )
        self.store.save_case(case)
        return {"case": self._public_case(case), "draft": draft}

    def get_report_draft(self, case_id: str, draft_id: str) -> dict[str, Any]:
        case = self._load_case(case_id)
        metadata = next((item for item in case.get("report_drafts", []) if item["draft_id"] == draft_id), None)
        if metadata is None or metadata.get("status") != "review_required":
            raise ServiceError("Bu taslak kaynak verisi değiştiği için artık kullanılamaz; yeniden oluşturun.", status_code=409, code="report_draft_invalidated")
        try:
            return self.store.load_report_draft(case_id, draft_id)
        except StorageError as error:
            raise ServiceError(str(error), status_code=404, code="report_draft_not_found") from error

    def page_path(self, case_id: str, document_id: str, page_number: int) -> Path:
        case = self._load_case(case_id)
        try:
            return self.store.page_path(case_id, self._document(case, document_id), page_number)
        except StorageError as error:
            raise ServiceError(str(error), status_code=404, code="page_not_found") from error

    def transform_page(
        self,
        case_id: str,
        document_id: str,
        page_number: int,
        operation: str,
        crop: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        case = self._load_case(case_id)
        document = self._document(case, document_id)
        page = next((item for item in document.get("pages", []) if item["page"] == page_number), None)
        if page is None:
            raise ServiceError("Belge sayfası bulunamadı.", status_code=404, code="page_not_found")
        try:
            self.store.transform_page(case_id, document_id, page, operation, crop)
        except StorageError as error:
            raise ServiceError(str(error), code="page_transform_failed") from error

        if document.get("ocr_lines"):
            document.setdefault("ocr_history", []).append(
                {
                    "transform_revision": page.get("transform", {}).get("revision", 0) - 1,
                    "lines": document["ocr_lines"],
                }
            )
        document["ocr_lines"] = []
        document["ocr_status"] = "not_started"
        document["ocr_error"] = None
        case["extraction"] = None
        self._invalidate_report_drafts(case, reason="page_transformed")
        self._invalidate_docx_reports(case, reason="page_transformed")
        case["stage"] = "documents"
        case["audit"].append(
            {"event": "page_transformed", "document_id": document_id, "page": page_number, "operation": operation}
        )
        self.store.save_case(case)
        return self._public_case(case)

    def _read_document(self, case: dict[str, Any], document: dict[str, Any]) -> list[dict[str, Any]]:
        if document.get("is_synthetic"):
            return _transformed_synthetic_lines(document)
        lines: list[dict[str, Any]] = []
        for page in document["pages"]:
            page_path = self.store.page_path(case["case_id"], document, page["page"])
            lines.extend(line.as_dict() for line in self.ocr_provider.read(page_path, page["page"]))
        return lines

    def _extract(self, case: dict[str, Any]) -> None:
        extraction = extract_case(case["case_id"], case["documents"])
        self._validate(extraction)
        case["extraction"] = extraction

    @staticmethod
    def _document(case: dict[str, Any], document_id: str) -> dict[str, Any]:
        document = next((item for item in case["documents"] if item["document_id"] == document_id), None)
        if document is None:
            raise ServiceError("Belge bulunamadı.", status_code=404, code="document_not_found")
        return document

    def _load_case(self, case_id: str) -> dict[str, Any]:
        try:
            case = self.store.load_case(case_id)
        except StorageError as error:
            raise ServiceError(str(error), status_code=404, code="case_not_found") from error
        self._upgrade_extraction(case)
        case.setdefault("report_drafts", [])
        case.setdefault("docx_input", None)
        case.setdefault("docx_reports", [])
        return case

    @staticmethod
    def _upgrade_extraction(case: dict[str, Any]) -> None:
        """Önceki yerel vakaları, yeni kanonik alanlar eklenince düzenlenebilir tutar."""
        extraction = case.get("extraction")
        if not extraction or extraction.get("schema_version") != "1.1.0":
            return
        extraction["schema_version"] = "1.2.0"
        extraction.setdefault("patient", {}).setdefault("birth_place", _missing_evidence_field())
        extraction.setdefault("medical", {}).setdefault("protocol_number", _missing_evidence_field())

    @staticmethod
    def _extraction(case: dict[str, Any]) -> dict[str, Any]:
        extraction = case.get("extraction")
        if not extraction:
            raise ServiceError("Önce OCR ve alan çıkarımı tamamlanmalıdır.", code="processing_required")
        return extraction

    @staticmethod
    def _validate(extraction: dict[str, Any]) -> None:
        try:
            validate_extraction(extraction)
        except CanonicalSchemaError as error:
            raise ServiceError("Kanonik veri sözleşmesi doğrulanamadı; işlem kaydedilmedi.", status_code=500, code="schema_validation_failed") from error

    @staticmethod
    def _invalidate_report_drafts(case: dict[str, Any], *, reason: str) -> None:
        active = [item for item in case.get("report_drafts", []) if item.get("status") == "review_required"]
        if not active:
            return
        for item in active:
            item["status"] = "invalidated"
        case["audit"].append({"event": "report_drafts_invalidated", "reason": reason})

    @staticmethod
    def _invalidate_docx_reports(case: dict[str, Any], *, reason: str) -> None:
        active = [item for item in case.get("docx_reports", []) if item.get("status") == "review_required"]
        if not active:
            return
        for item in active:
            item["status"] = "superseded"
        case["audit"].append({"event": "docx_reports_superseded", "reason": reason, "report_count": len(active)})

    @staticmethod
    def _public_docx_report(case_id: str, report: dict[str, Any]) -> dict[str, Any]:
        public = copy.deepcopy(report)
        public.pop("relative_path", None)
        public["download_endpoint"] = f"/api/cases/{case_id}/docx-reports/{public['report_id']}/download"
        return public

    @staticmethod
    def _public_case(case: dict[str, Any]) -> dict[str, Any]:
        public_case = copy.deepcopy(case)
        for document in public_case.get("documents", []):
            document.pop("file_path", None)
            document.pop("synthetic_ocr_lines", None)
            document.pop("ocr_history", None)
            for page in document.get("pages", []):
                page.pop("path", None)
                page.pop("original_path", None)
                page.pop("original_width", None)
                page.pop("original_height", None)
                page["image_endpoint"] = (
                    f"/api/cases/{public_case['case_id']}/documents/{document['document_id']}"
                    f"/pages/{page['page']}/image"
                )
        public_case["report_draft_eligibility"] = draft_eligibility(public_case.get("extraction"))
        public_case["docx_reports"] = [
            CaseService._public_docx_report(public_case["case_id"], report)
            for report in public_case.get("docx_reports", [])
        ]
        return public_case


def _missing_evidence_field() -> dict[str, Any]:
    return {
        "value": None,
        "original_value": None,
        "status": "missing",
        "approved": False,
        "provenance": {
            "source_document_id": None,
            "page": None,
            "evidence_text": None,
            "ocr_confidence": None,
            "polygon": None,
        },
        "candidates": [],
    }


def _transformed_synthetic_lines(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Demo OCR satırlarını, özgün fixture'ı değiştirmeden sayfa dönüşümlerine uyarlar."""
    page_by_number = {page["page"]: page for page in document.get("pages", [])}
    transformed: list[dict[str, Any]] = []
    for source_line in document.get("synthetic_ocr_lines", []):
        line = copy.deepcopy(source_line)
        page = page_by_number.get(line["page"])
        if page is None:
            continue
        polygon = line["polygon"]
        for operation in page.get("transform", {}).get("operations", []):
            polygon = _transform_polygon(polygon, operation)
            if polygon is None:
                break
        if polygon is not None:
            line["polygon"] = polygon
            transformed.append(line)
    return transformed


def _transform_polygon(polygon: list[list[float]], operation: dict[str, Any]) -> list[list[float]] | None:
    if operation["operation"] == "rotate":
        width = float(operation["input_width"])
        height = float(operation["input_height"])
        degrees = operation["degrees"]
        if degrees == 90:
            return [[height - point[1], point[0]] for point in polygon]
        if degrees == -90:
            return [[point[1], width - point[0]] for point in polygon]
        if degrees == 180:
            return [[width - point[0], height - point[1]] for point in polygon]
    if operation["operation"] == "crop":
        left, top, right, bottom = (float(operation[name]) for name in ("left", "top", "right", "bottom"))
        center_x = sum(point[0] for point in polygon) / len(polygon)
        center_y = sum(point[1] for point in polygon) / len(polygon)
        if not (left <= center_x <= right and top <= center_y <= bottom):
            return None
        output_width = float(operation["output_width"])
        output_height = float(operation["output_height"])
        return [
            [min(max(point[0] - left, 0), output_width), min(max(point[1] - top, 0), output_height)]
            for point in polygon
        ]
    return polygon
