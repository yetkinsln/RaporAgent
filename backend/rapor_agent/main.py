"""Yerel HTTP API; kullanıcı onaylı alanlarla kurumsal DOCX taslağı üretir."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, model_validator

from .service import CaseService, ServiceError


DocumentType = Literal[
    "cover_letter",
    "general_forensic_exam",
    "epicrisis",
    "department_exam_note",
    "other",
    "unknown",
]


class DocumentTypeUpdate(BaseModel):
    document_type: DocumentType


class FieldValueUpdate(BaseModel):
    value: str | list[str] | None = Field(default=None, max_length=4_000)


class DocxInputUpdate(BaseModel):
    # Boş alanların tamamını tek seferde, alan adıyla birlikte servis katmanı
    # bildirir. Pydantic'in varsayılan 422 gövdesi istemcide genel bir hataya
    # dönüşüyordu ve kullanıcı hangi Word bilgisinin eksik olduğunu göremiyordu.
    document_number: str = Field(max_length=80)
    document_date: str = Field(max_length=20)
    examination_date: str = Field(max_length=30)
    history: str = Field(max_length=4_000)
    current_exam_findings: str = Field(max_length=4_000)


class DocxGenerationConfirmation(BaseModel):
    confirmed: Literal[True]


class CropSelection(BaseModel):
    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("Kırpma alanı pozitif genişlik ve yüksekliğe sahip olmalı.")
        return self


class PageTransformUpdate(BaseModel):
    operation: Literal["rotate_clockwise", "rotate_counterclockwise", "crop", "reset"]
    crop: CropSelection | None = None

    @model_validator(mode="after")
    def validate_operation(self):
        if self.operation == "crop" and self.crop is None:
            raise ValueError("Kırpma işlemi için alan seçimi gerekli.")
        if self.operation != "crop" and self.crop is not None:
            raise ValueError("Kırpma alanı yalnızca kırpma işleminde gönderilebilir.")
        return self


def create_app(*, data_dir: Path | None = None, service: CaseService | None = None) -> FastAPI:
    root = data_dir or Path(os.environ.get("RAPOR_AGENT_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
    case_service = service or CaseService(root)
    app = FastAPI(title="Rapor Agent", version="0.1.0")
    app.state.case_service = case_service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(ServiceError)
    async def service_error_handler(_, error: ServiceError) -> JSONResponse:
        return _error(error)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, error: RequestValidationError) -> JSONResponse:
        """İstemcinin her zaman kullanıcıya gösterilebilir bir hata almasını sağlar."""
        errors = error.errors()
        body_fields = [
            str(item["loc"][-1])
            for item in errors
            if item.get("loc") and item["loc"][0] == "body"
        ]
        labels = {
            "document_number": "Manuel SAYI",
            "document_date": "Rapor düzenleme tarihi",
            "examination_date": "Muayene tarihi ve saati",
            "history": "Anamnez ve olay öyküsü",
            "current_exam_findings": "Güncel muayene bulguları",
        }
        named_fields = [labels.get(field, field) for field in body_fields]
        message = (
            "Word üretim formunda geçersiz veya eksik alan var: " + ", ".join(named_fields) + "."
            if named_fields
            else "Gönderilen bilgi biçimi geçersiz; alanları kontrol edip yeniden deneyin."
        )
        return JSONResponse(
            status_code=422,
            content={"detail": {"code": "request_validation_error", "message": message}},
        )

    @app.post("/api/cases", status_code=201)
    def create_case() -> dict:
        return case_service.create_case()

    @app.post("/api/demo-case", status_code=201)
    def create_demo_case() -> dict:
        return case_service.create_demo_case()

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str) -> dict:
        return case_service.get_case(case_id)

    @app.post("/api/cases/{case_id}/documents", status_code=201)
    async def upload_document(case_id: str, file: Annotated[UploadFile, File(...)]) -> dict:
        payload = await file.read()
        return case_service.upload_document(case_id, file.filename or "belge", payload)

    @app.patch("/api/documents/{document_id}/type")
    def update_document_type(document_id: str, update: DocumentTypeUpdate, case_id: str) -> dict:
        return case_service.confirm_document_type(case_id, document_id, update.document_type)

    @app.delete("/api/cases/{case_id}/documents/{document_id}")
    def delete_document(case_id: str, document_id: str) -> dict:
        return case_service.delete_document(case_id, document_id)

    @app.post("/api/cases/{case_id}/process")
    def process_case(case_id: str) -> dict:
        return case_service.process(case_id)

    @app.post("/api/cases/{case_id}/documents/{document_id}/pages/{page_number}/transform")
    def transform_page(case_id: str, document_id: str, page_number: int, update: PageTransformUpdate) -> dict:
        return case_service.transform_page(
            case_id,
            document_id,
            page_number,
            update.operation,
            update.crop.model_dump() if update.crop else None,
        )

    @app.patch("/api/cases/{case_id}/fields/{field_path:path}")
    def update_field(case_id: str, field_path: str, update: FieldValueUpdate) -> dict:
        return case_service.change_field(case_id, field_path, update.value)

    @app.post("/api/cases/{case_id}/fields/{field_path:path}/approve")
    def approve_field(case_id: str, field_path: str) -> dict:
        return case_service.approve_field(case_id, field_path)

    @app.post("/api/cases/{case_id}/fields/approve-all")
    def approve_all_fields(case_id: str) -> dict:
        return case_service.approve_all_fields(case_id)

    @app.get("/api/llm/status")
    def llm_status() -> dict:
        return case_service.llm_status()

    @app.get("/api/docx/status")
    def docx_status() -> dict:
        return case_service.docx_status()

    @app.put("/api/cases/{case_id}/docx-input")
    def save_docx_input(case_id: str, update: DocxInputUpdate) -> dict:
        return case_service.save_docx_input(case_id, update.model_dump())

    @app.post("/api/cases/{case_id}/docx", status_code=201)
    def create_docx(case_id: str, confirmation: DocxGenerationConfirmation) -> dict:
        return case_service.create_docx(case_id, confirmed=confirmation.confirmed)

    @app.get("/api/cases/{case_id}/docx-reports/{report_id}/download")
    def download_docx(case_id: str, report_id: str) -> FileResponse:
        path, file_name = case_service.docx_report_path(case_id, report_id)
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=file_name,
        )

    @app.post("/api/cases/{case_id}/report-drafts", status_code=201)
    def create_report_draft(case_id: str) -> dict:
        return case_service.create_report_draft(case_id)

    @app.get("/api/cases/{case_id}/report-drafts/{draft_id}")
    def get_report_draft(case_id: str, draft_id: str) -> dict:
        return case_service.get_report_draft(case_id, draft_id)

    @app.get("/api/cases/{case_id}/documents/{document_id}/pages/{page_number}/image")
    def page_image(case_id: str, document_id: str, page_number: int) -> FileResponse:
        path = case_service.page_path(case_id, document_id, page_number)
        media_type = "image/svg+xml" if path.suffix == ".svg" else None
        return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})

    return app


def _error(error: ServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": {"code": error.code, "message": str(error)}},
    )


app = create_app()
