from __future__ import annotations

from io import BytesIO
import json
import zipfile

from fastapi.testclient import TestClient
from PIL import Image

from rapor_agent.extraction import extract_case
from rapor_agent.main import create_app
from rapor_agent.ocr import OcrProviderUnavailable, PaddleOcrProvider
from rapor_agent.reporting import LocalLLMUnavailable, ReportPlan
from rapor_agent.schema import validate_extraction
from rapor_agent.service import CaseService
from rapor_agent.synthetic import demo_documents


class SyntheticReportProvider:
    """Gerçek modele ihtiyaç duymayan, şemalı yerel LLM sözleşmesi testi."""

    def status(self):
        return {"provider": "synthetic-test", "local_only": True}

    def generate_plan(self, _):
        return (
            ReportPlan.model_validate(
                {
                    "schema_version": "1.0.0",
                    "sections": [
                        {
                            "id": "introduction",
                            "source_field_paths": [
                                "patient.full_name", "request.sender_authority", "request.letter_date",
                                "request.letter_number", "request.incident", "request.requested_questions",
                            ],
                        },
                        {
                            "id": "general_forensic_exam",
                            "source_field_paths": [
                                "medical.issuing_institution", "medical.report_date", "medical.report_number",
                                "medical.incident_date_time", "medical.incident_type", "medical.clinical_findings",
                            ],
                        },
                        {
                            "id": "conclusion",
                            "source_field_paths": ["medical.life_threat", "medical.simple_medical_intervention"],
                        },
                    ],
                }
            ),
            {
                "provider": "synthetic-test",
                "model_name": "SENTETIK-QWEN",
                "model_revision": "synthetic",
                "prompt_version": "report-plan-v1",
            },
        )


def _approve_all_critical_fields(client, case_id):
    processed = client.post(f"/api/cases/{case_id}/process")
    assert processed.status_code == 200
    extraction = processed.json()["extraction"]
    for group in ("patient", "request", "medical"):
        for name, field in extraction[group].items():
            if field["status"] != "missing" and field["value"] not in (None, "", []):
                approved = client.post(f"/api/cases/{case_id}/fields/{group}.{name}/approve")
                assert approved.status_code == 200


def _synthetic_docx_input(**overrides):
    values = {
        "document_number": "MANUEL-SENTETIK-001",
        "document_date": "03.09.2026",
        "examination_date": "03.09.2026 14:30",
        "history": "Sentetik olay öyküsü ve kullanıcı beyanı.",
        "current_exam_findings": "Genel durumu iyi, bilinci açık ve sentetik muayene bulguları olağan.",
    }
    values.update(overrides)
    return values


def test_synthetic_demo_runs_from_page_to_source_backed_confirmation(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))

    created = client.post("/api/demo-case")
    assert created.status_code == 201
    case = created.json()
    assert len(case["documents"]) == 2
    assert all(document["ocr_status"] == "not_started" for document in case["documents"])

    processed = client.post(f"/api/cases/{case['case_id']}/process")
    assert processed.status_code == 200
    result = processed.json()
    extraction = result["extraction"]

    assert extraction["schema_version"] == "1.2.0"
    assert extraction["patient"]["full_name"]["value"] == "DENİZ ÖRNEK"
    assert extraction["patient"]["tckn"]["value"] == "10000000146"
    assert extraction["patient"]["birth_place"]["value"] == "SENTETİK İL"
    assert extraction["patient"]["birth_date"]["value"] == "02.05.1991"
    assert extraction["patient"]["tckn"]["approved"] is False
    assert extraction["medical"]["protocol_number"]["value"] == "PR-2026-0001"
    assert extraction["medical"]["report_number"]["value"] == "GARM-2026-0001"
    assert extraction["medical"]["life_threat"]["value"] == "no"
    assert extraction["medical"]["simple_medical_intervention"]["value"] == "yes"
    assert len(result["documents"][0]["ocr_lines"][0]["polygon"]) == 4
    assert not any(item["code"] == "institutional_word_template_missing" for item in extraction["warnings"])
    assert extraction["ready_to_generate"] is False

    image = client.get(result["documents"][0]["pages"][0]["image_endpoint"])
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")

    approved = client.post(f"/api/cases/{case['case_id']}/fields/patient.tckn/approve")
    assert approved.status_code == 200
    assert approved.json()["extraction"]["patient"]["tckn"]["approved"] is True

    corrected = client.patch(
        f"/api/cases/{case['case_id']}/fields/patient.full_name",
        json={"value": "DENİZ SENTETİK"},
    )
    assert corrected.status_code == 200
    full_name = corrected.json()["extraction"]["patient"]["full_name"]
    assert full_name["status"] == "user_corrected"
    assert full_name["approved"] is False


def test_identity_and_reference_label_variants_keep_their_source_evidence():
    lines = [
        {"text": "T.C. Kimlik No: 10000000146", "confidence": 0.98, "polygon": [[10, 10], [90, 10], [90, 30], [10, 30]], "reading_order": 0, "page": 1},
        {"text": "Doğum Yeri ve Tarihi: SENTETİK İL / 02.05.1991", "confidence": 0.97, "polygon": [[10, 40], [200, 40], [200, 60], [10, 60]], "reading_order": 1, "page": 1},
        {"text": "Protokol Numarası: PRO-SENTETİK-01", "confidence": 0.96, "polygon": [[10, 70], [200, 70], [200, 90], [10, 90]], "reading_order": 2, "page": 1},
        {"text": "Rapor No: RAP-SENTETİK-01", "confidence": 0.95, "polygon": [[10, 100], [200, 100], [200, 120], [10, 120]], "reading_order": 3, "page": 1},
    ]
    extraction = extract_case(
        "c" * 32,
        [{
            "document_id": "synthetic-epicrisis",
            "file_name": "SENTETIK_epikriz.png",
            "type": "epicrisis",
            "classification_confidence": 1.0,
            "user_confirmed_type": True,
            "pages": [{"page": 1}],
            "ocr_lines": lines,
        }],
    )

    validate_extraction(extraction)
    assert extraction["patient"]["tckn"]["value"] == "10000000146"
    assert extraction["patient"]["birth_place"]["value"] == "SENTETİK İL"
    assert extraction["patient"]["birth_date"]["value"] == "02.05.1991"
    assert extraction["medical"]["protocol_number"]["value"] == "PRO-SENTETİK-01"
    assert extraction["medical"]["report_number"]["value"] == "RAP-SENTETİK-01"
    assert extraction["medical"]["protocol_number"]["provenance"]["evidence_text"] == lines[2]["text"]


def test_invalid_tckn_checksum_is_blocking_without_changing_the_extracted_value():
    extraction = extract_case(
        "d" * 32,
        [{
            "document_id": "synthetic-document",
            "file_name": "SENTETIK.png",
            "type": "other",
            "classification_confidence": 1.0,
            "user_confirmed_type": True,
            "pages": [{"page": 1}],
            "ocr_lines": [
                {"text": "T.C. Kimlik No: 10000000145", "confidence": 0.99, "polygon": [[10, 10], [90, 10], [90, 30], [10, 30]], "reading_order": 0, "page": 1},
            ],
        }],
    )

    assert extraction["patient"]["tckn"]["value"] == "10000000145"
    assert extraction["patient"]["tckn"]["status"] == "extracted"
    assert ("invalid_tckn_checksum", "patient.tckn", "blocking") in {
        (warning["code"], warning["field_path"], warning["severity"])
        for warning in extraction["warnings"]
    }


def test_form_row_values_are_extracted_from_separate_ocr_boxes():
    def line(text, left, top, right, bottom, order):
        return {
            "text": text,
            "confidence": 0.98,
            "polygon": [[left, top], [right, top], [right, bottom], [left, bottom]],
            "reading_order": order,
            "page": 1,
        }

    lines = [
        line("GENEL ADLİ", 20, 20, 150, 40, 0),
        line("MUAYENE", 160, 20, 280, 40, 1),
        line("T.C. Kimlik No", 20, 80, 150, 100, 2),
        line("10000000146", 240, 80, 350, 100, 3),
        line("Adı Soyadı", 20, 120, 120, 140, 4),
        line("DENİZ ÖRNEK", 240, 120, 360, 140, 5),
        line("Doğum Yeri ve Tarihi", 20, 160, 220, 180, 6),
        line("SENTETİK İL / 02.05.1991", 240, 160, 460, 180, 7),
        line("Protokol No: PRO-SENTETİK-01", 20, 200, 300, 220, 8),
        line("Rapor No: RAP-SENTETİK-01", 20, 240, 300, 260, 9),
    ]
    extraction = extract_case(
        "e" * 32,
        [{
            "document_id": "synthetic-form",
            "file_name": "SENTETIK_form.png",
            "type": "unknown",
            "classification_confidence": None,
            "user_confirmed_type": False,
            "pages": [{"page": 1}],
            "ocr_lines": lines,
        }],
    )

    validate_extraction(extraction)
    assert extraction["documents"][0]["type"] == "general_forensic_exam"
    assert extraction["patient"]["tckn"]["value"] == "10000000146"
    assert extraction["patient"]["full_name"]["value"] == "DENİZ ÖRNEK"
    assert extraction["patient"]["birth_place"]["value"] == "SENTETİK İL"
    assert extraction["patient"]["birth_date"]["value"] == "02.05.1991"
    assert extraction["medical"]["protocol_number"]["value"] == "PRO-SENTETİK-01"
    assert extraction["medical"]["report_number"]["value"] == "RAP-SENTETİK-01"
    assert extraction["patient"]["tckn"]["provenance"]["polygon"] == lines[3]["polygon"]


def test_examiner_name_is_not_collected_as_patient_name():
    def line(text, left, top, right, bottom, order):
        return {
            "text": text,
            "confidence": 0.98,
            "polygon": [[left, top], [right, top], [right, bottom], [left, bottom]],
            "reading_order": order,
            "page": 1,
        }

    lines = [
        line("MUAYENE EDEN", 20, 20, 180, 40, 0),
        line("Adı Soyadı: DR. SENTETİK HEKİM", 20, 50, 340, 70, 1),
        line("MUAYENE EDİLEN", 20, 110, 200, 130, 2),
        line("Adı Soyadı", 20, 150, 130, 170, 3),
        line("DENİZ ÖRNEK", 220, 150, 350, 170, 4),
    ]
    extraction = extract_case(
        "f" * 32,
        [{
            "document_id": "synthetic-examiner-and-patient",
            "file_name": "SENTETIK_muayene.png",
            "type": "general_forensic_exam",
            "classification_confidence": 1.0,
            "user_confirmed_type": True,
            "pages": [{"page": 1}],
            "ocr_lines": lines,
        }],
    )

    validate_extraction(extraction)
    patient_name = extraction["patient"]["full_name"]
    assert patient_name["value"] == "DENİZ ÖRNEK"
    assert len(patient_name["candidates"]) == 1
    assert patient_name["provenance"]["polygon"] == lines[4]["polygon"]


def test_conflicting_sources_remain_visible_and_need_user_choice():
    fixtures = demo_documents()
    conflicting_line = next(line for line in fixtures[1]["lines"] if line["text"].startswith("Adı Soyadı"))
    conflicting_line["text"] = "Adı Soyadı: FARKLI SENTETİK KİŞİ"
    documents = [
        {
            "document_id": f"doc_{index}",
            "file_name": fixture["file_name"],
            "type": fixture["type"],
            "classification_confidence": None,
            "user_confirmed_type": False,
            "pages": [{"page": 1}],
            "ocr_lines": fixture["lines"],
        }
        for index, fixture in enumerate(fixtures)
    ]

    extraction = extract_case("a" * 32, documents)
    validate_extraction(extraction)
    full_name = extraction["patient"]["full_name"]
    assert full_name["status"] == "conflict"
    assert full_name["value"] is None
    assert len(full_name["candidates"]) == 2
    assert {candidate["value"] for candidate in full_name["candidates"]} == {"DENİZ ÖRNEK", "FARKLI SENTETİK KİŞİ"}


def test_missing_and_low_confidence_critical_fields_are_explicitly_flagged():
    fixtures = demo_documents()
    for fixture in fixtures:
        fixture["lines"] = [
            line
            for line in fixture["lines"]
            if not line["text"].startswith("Doğum Tarihi") and not line["text"].startswith("Doğum Yeri ve Tarihi")
        ]
    full_name_line = next(line for line in fixtures[0]["lines"] if line["text"].startswith("Adı Soyadı"))
    full_name_line["confidence"] = 0.42
    documents = [
        {
            "document_id": f"doc_{index}",
            "file_name": fixture["file_name"],
            "type": fixture["type"],
            "classification_confidence": None,
            "user_confirmed_type": False,
            "pages": [{"page": 1}],
            "ocr_lines": fixture["lines"],
        }
        for index, fixture in enumerate(fixtures)
    ]

    extraction = extract_case("b" * 32, documents)
    validate_extraction(extraction)
    assert extraction["patient"]["birth_date"]["status"] == "missing"
    warnings = {(warning["code"], warning["field_path"], warning["severity"]) for warning in extraction["warnings"]}
    assert ("field_missing", "patient.birth_date", "blocking") in warnings
    assert ("critical_field_low_ocr_confidence", "patient.full_name", "blocking") in warnings


def test_ocr_unavailability_does_not_silently_use_another_service(tmp_path):
    class UnavailableProvider:
        def read(self, _, __):
            raise OcrProviderUnavailable("Yerel OCR bilinçli olarak kullanılamıyor.")

    service = CaseService(tmp_path, ocr_provider=UnavailableProvider())
    client = TestClient(create_app(service=service))
    case_id = client.post("/api/cases").json()["case_id"]
    image = Image.new("RGB", (20, 20), "white")
    payload = BytesIO()
    image.save(payload, format="PNG")
    uploaded = client.post(
        f"/api/cases/{case_id}/documents",
        files={"file": ("synthetic-test.png", payload.getvalue(), "image/png")},
    )
    assert uploaded.status_code == 201

    response = client.post(f"/api/cases/{case_id}/process")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ocr_unavailable"
    state = client.get(f"/api/cases/{case_id}").json()
    assert state["documents"][0]["ocr_status"] == "error"


def test_manual_page_rotation_preserves_original_and_requires_reprocessing(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    case = client.post("/api/demo-case").json()
    processed = client.post(f"/api/cases/{case['case_id']}/process").json()
    document = processed["documents"][0]
    page = document["pages"][0]
    assert (page["width"], page["height"]) == (1000, 900)
    assert processed["extraction"] is not None

    rotated = client.post(
        f"/api/cases/{case['case_id']}/documents/{document['document_id']}/pages/1/transform",
        json={"operation": "rotate_clockwise"},
    )
    assert rotated.status_code == 200
    transformed = rotated.json()
    transformed_document = transformed["documents"][0]
    transformed_page = transformed_document["pages"][0]
    assert (transformed_page["width"], transformed_page["height"]) == (900, 1000)
    assert transformed_page["transform"]["operations"][-1]["operation"] == "rotate"
    assert transformed_document["ocr_status"] == "not_started"
    assert transformed_document["ocr_lines"] == []
    assert transformed["extraction"] is None
    image = client.get(transformed_page["image_endpoint"])
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")

    reprocessed = client.post(f"/api/cases/{case['case_id']}/process")
    assert reprocessed.status_code == 200
    refreshed = reprocessed.json()
    first_polygon = refreshed["documents"][0]["ocr_lines"][0]["polygon"]
    assert all(0 <= point[0] <= 900 and 0 <= point[1] <= 1000 for point in first_polygon)
    assert refreshed["extraction"]["patient"]["full_name"]["value"] == "DENİZ ÖRNEK"

    reset = client.post(
        f"/api/cases/{case['case_id']}/documents/{document['document_id']}/pages/1/transform",
        json={"operation": "reset"},
    )
    assert reset.status_code == 200
    reset_page = reset.json()["documents"][0]["pages"][0]
    assert (reset_page["width"], reset_page["height"]) == (1000, 900)
    assert reset_page["transform"]["operations"] == []

    cropped = client.post(
        f"/api/cases/{case['case_id']}/documents/{document['document_id']}/pages/1/transform",
        json={"operation": "crop", "crop": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.9}},
    )
    assert cropped.status_code == 200
    cropped_page = cropped.json()["documents"][0]["pages"][0]
    assert (cropped_page["width"], cropped_page["height"]) == (800, 720)
    assert cropped_page["transform"]["operations"][-1]["operation"] == "crop"


def test_invalid_manual_crop_is_rejected_before_processing(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    case = client.post("/api/demo-case").json()
    document_id = case["documents"][0]["document_id"]

    response = client.post(
        f"/api/cases/{case['case_id']}/documents/{document_id}/pages/1/transform",
        json={"operation": "crop", "crop": {"left": 0.8, "top": 0.2, "right": 0.2, "bottom": 0.7}},
    )
    assert response.status_code == 422


def test_delete_document_removes_its_local_files_and_invalidates_extraction(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    case = client.post("/api/demo-case").json()
    first, second = case["documents"]

    # Türetilmiş sayfa da belge silindiğinde sahipsiz kalmamalıdır.
    transformed = client.post(
        f"/api/cases/{case['case_id']}/documents/{first['document_id']}/pages/1/transform",
        json={"operation": "rotate_clockwise"},
    )
    assert transformed.status_code == 200
    processed = client.post(f"/api/cases/{case['case_id']}/process")
    assert processed.status_code == 200
    assert processed.json()["extraction"] is not None

    case_dir = tmp_path / "cases" / case["case_id"]
    first_files = [*case_dir.joinpath("pages").glob(f"{first['document_id']}-*"), *case_dir.joinpath("derived").glob(f"{first['document_id']}-*")]
    second_files = list(case_dir.joinpath("pages").glob(f"{second['document_id']}-*"))
    assert first_files and second_files

    deleted = client.delete(f"/api/cases/{case['case_id']}/documents/{first['document_id']}")
    assert deleted.status_code == 200
    state = deleted.json()
    assert [document["document_id"] for document in state["documents"]] == [second["document_id"]]
    assert state["extraction"] is None
    assert state["stage"] == "documents"
    assert not any(path.exists() for path in first_files)
    assert all(path.exists() for path in second_files)
    assert client.get(first["pages"][0]["image_endpoint"]).status_code == 404


def test_delete_uploaded_document_removes_original_page_and_derived_files(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    case = client.post("/api/cases").json()
    image = Image.new("RGB", (100, 100), "white")
    payload = BytesIO()
    image.save(payload, format="PNG")
    uploaded = client.post(
        f"/api/cases/{case['case_id']}/documents",
        files={"file": ("synthetic-upload.png", payload.getvalue(), "image/png")},
    )
    assert uploaded.status_code == 201
    document = uploaded.json()["documents"][0]

    transformed = client.post(
        f"/api/cases/{case['case_id']}/documents/{document['document_id']}/pages/1/transform",
        json={"operation": "rotate_clockwise"},
    )
    assert transformed.status_code == 200
    case_dir = tmp_path / "cases" / case["case_id"]
    document_id = document["document_id"]
    assert list(case_dir.joinpath("originals").glob(f"{document_id}.*"))
    assert list(case_dir.joinpath("pages").glob(f"{document_id}-*"))
    assert list(case_dir.joinpath("derived").glob(f"{document_id}-*"))

    deleted = client.delete(f"/api/cases/{case['case_id']}/documents/{document_id}")
    assert deleted.status_code == 200
    assert deleted.json()["documents"] == []
    assert not list(case_dir.joinpath("originals").glob(f"{document_id}.*"))
    assert not list(case_dir.joinpath("pages").glob(f"{document_id}-*"))
    assert not list(case_dir.joinpath("derived").glob(f"{document_id}-*"))


def test_local_llm_draft_is_saved_from_only_approved_synthetic_fields(tmp_path):
    service = CaseService(tmp_path, report_provider=SyntheticReportProvider())
    client = TestClient(create_app(service=service))
    case = client.post("/api/demo-case").json()
    _approve_all_critical_fields(client, case["case_id"])

    created = client.post(f"/api/cases/{case['case_id']}/report-drafts")
    assert created.status_code == 201
    result = created.json()
    draft = result["draft"]
    assert draft["status"] == "review_required"
    assert draft["generation"]["local_only"] is True
    assert draft["generation"]["model_name"] == "SENTETIK-QWEN"
    assert [section["id"] for section in draft["sections"]] == ["introduction", "general_forensic_exam", "conclusion"]
    assert draft["blockers"] == []
    assert "10000000146" not in "\n".join(section["text"] for section in draft["sections"])
    assert result["case"]["report_drafts"][0]["draft_id"] == draft["draft_id"]

    reports_dir = tmp_path / "cases" / case["case_id"] / "reports"
    assert reports_dir.joinpath(f"draft-{draft['draft_id']}.json").is_file()
    assert reports_dir.joinpath(f"draft-{draft['draft_id']}.txt").is_file()
    loaded = client.get(f"/api/cases/{case['case_id']}/report-drafts/{draft['draft_id']}")
    assert loaded.status_code == 200
    assert loaded.json()["draft_id"] == draft["draft_id"]

    # Kaynak alan değişirse eski taslak tekrar açılıp kullanılamaz; yeni onay
    # ve yeni taslak üretimi gerekir.
    corrected = client.patch(
        f"/api/cases/{case['case_id']}/fields/patient.full_name",
        json={"value": "DENİZ GÜNCEL SENTETİK"},
    )
    assert corrected.status_code == 200
    assert corrected.json()["report_drafts"][0]["status"] == "invalidated"
    invalidated = client.get(f"/api/cases/{case['case_id']}/report-drafts/{draft['draft_id']}")
    assert invalidated.status_code == 409
    assert invalidated.json()["detail"]["code"] == "report_draft_invalidated"


def test_model_cannot_choose_or_remove_canonical_report_sources(tmp_path):
    class NonCanonicalSourceProvider(SyntheticReportProvider):
        def generate_plan(self, approved_context):
            plan, metadata = super().generate_plan(approved_context)
            plan.sections[0].source_field_paths = ["model.invented_path"]
            return plan, metadata

    service = CaseService(tmp_path, report_provider=NonCanonicalSourceProvider())
    client = TestClient(create_app(service=service))
    case = client.post("/api/demo-case").json()
    _approve_all_critical_fields(client, case["case_id"])

    response = client.post(f"/api/cases/{case['case_id']}/report-drafts")
    assert response.status_code == 201
    introduction = response.json()["draft"]["sections"][0]
    assert set(introduction["source_field_paths"]) == {
        "patient.full_name",
        "request.sender_authority",
        "request.letter_date",
        "request.letter_number",
        "request.incident",
        "request.requested_questions",
    }


def test_report_draft_requires_critical_user_approvals(tmp_path):
    service = CaseService(tmp_path, report_provider=SyntheticReportProvider())
    client = TestClient(create_app(service=service))
    case = client.post("/api/demo-case").json()
    processed = client.post(f"/api/cases/{case['case_id']}/process")
    assert processed.status_code == 200

    response = client.post(f"/api/cases/{case['case_id']}/report-drafts")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "report_approval_required"


def test_user_initiated_bulk_approval_approves_only_eligible_fields(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    case = client.post("/api/demo-case").json()
    processed = client.post(f"/api/cases/{case['case_id']}/process")
    assert processed.status_code == 200

    approved = client.post(f"/api/cases/{case['case_id']}/fields/approve-all")
    assert approved.status_code == 200
    result = approved.json()
    assert len(result["approved_field_paths"]) == 19
    assert {item["field_path"]: item["reason"] for item in result["skipped"]} == {
        "medical.epicrisis_summary": "missing",
        "medical.department_exam_summary": "missing",
    }
    assert result["case"]["extraction"]["patient"]["tckn"]["approved"] is True
    assert result["case"]["report_draft_eligibility"]["ready"] is True


def test_bulk_approval_skips_invalid_tckn_instead_of_overriding_the_check(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    case = client.post("/api/demo-case").json()
    assert client.post(f"/api/cases/{case['case_id']}/process").status_code == 200
    assert client.patch(
        f"/api/cases/{case['case_id']}/fields/patient.tckn",
        json={"value": "10000000145"},
    ).status_code == 200

    approved = client.post(f"/api/cases/{case['case_id']}/fields/approve-all")
    assert approved.status_code == 200
    result = approved.json()
    assert {item["field_path"]: item["reason"] for item in result["skipped"]} == {
        "patient.tckn": "invalid_tckn",
        "medical.epicrisis_summary": "missing",
        "medical.department_exam_summary": "missing",
    }
    assert result["case"]["extraction"]["patient"]["tckn"]["approved"] is False


def test_docx_generation_uses_the_institutional_template_after_explicit_confirmation(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    status = client.get("/api/docx/status")
    assert status.status_code == 200
    assert status.json()["available"] is True
    assert status.json()["template"]["file_name"] == "adli-rapor-sablonu-v2.docx"
    assert status.json()["template"]["mapped_field_count"] == 25
    assert status.json()["sayi_mode"] == "manual"
    assert status.json()["sayi_auto_generate"] is False

    case = client.post("/api/demo-case").json()
    _approve_all_critical_fields(client, case["case_id"])
    incomplete = client.post(f"/api/cases/{case['case_id']}/docx", json={"confirmed": True})
    assert incomplete.status_code == 409
    assert incomplete.json()["detail"]["code"] == "docx_input_incomplete"

    saved = client.put(f"/api/cases/{case['case_id']}/docx-input", json=_synthetic_docx_input())
    assert saved.status_code == 200
    assert saved.json()["docx_input"]["status"] == "review_required"

    created = client.post(f"/api/cases/{case['case_id']}/docx", json={"confirmed": True})
    assert created.status_code == 201
    report = created.json()["report"]
    assert report["file_name"] == "DENIZ_ORNEK-rapor01.docx"
    assert report["status"] == "review_required"
    assert "patient.tckn" in report["source_field_paths"]
    assert report["download_endpoint"].endswith("/download")

    output = tmp_path / "cases" / case["case_id"] / "reports" / report["file_name"]
    assert output.is_file()
    with zipfile.ZipFile(output) as document:
        rendered_text = "\n".join(
            document.read(name).decode("utf-8")
            for name in document.namelist()
            if name.startswith("word/") and name.endswith(".xml")
        )
        assert len(document.namelist()) == len(set(document.namelist()))
    assert "{{" not in rendered_text
    assert "None" not in rendered_text
    assert "null" not in rendered_text
    assert "MANUEL-SENTETIK-001" in rendered_text
    assert "PAMUKKALE ÜNİVERSİTESİ TIP FAKÜLTESİ" in rendered_text
    assert "sentetik muayene bulguları olağan" in rendered_text

    downloaded = client.get(report["download_endpoint"])
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert downloaded.content.startswith(b"PK")

    second = client.post(f"/api/cases/{case['case_id']}/docx", json={"confirmed": True})
    assert second.status_code == 201
    assert second.json()["report"]["file_name"] == "DENIZ_ORNEK-rapor02.docx"

    changed = client.patch(f"/api/cases/{case['case_id']}/fields/medical.clinical_findings", json={"value": "Güncel sentetik bulgu"})
    assert changed.status_code == 200
    assert {item["status"] for item in changed.json()["docx_reports"]} == {"superseded"}
    outdated_download = client.get(report["download_endpoint"])
    assert outdated_download.status_code == 409
    assert outdated_download.json()["detail"]["code"] == "docx_report_superseded"


def test_docx_rejects_a_multiline_manual_sayi_value(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    case = client.post("/api/demo-case").json()
    _approve_all_critical_fields(client, case["case_id"])

    response = client.put(
        f"/api/cases/{case['case_id']}/docx-input",
        json=_synthetic_docx_input(document_number="SATIR-1\nSATIR-2"),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_document_number"


def test_docx_blank_manual_fields_return_a_single_actionable_error(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    case = client.post("/api/demo-case").json()

    response = client.put(
        f"/api/cases/{case['case_id']}/docx-input",
        json={
            "document_number": "",
            "document_date": "",
            "examination_date": "",
            "history": "",
            "current_exam_findings": "",
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "docx_input_incomplete"
    assert "Manuel SAYI" in detail["message"]
    assert "Anamnez ve olay öyküsü" in detail["message"]
    assert "Güncel muayene bulguları" in detail["message"]
    assert not list((tmp_path / "cases" / case["case_id"] / "reports").iterdir())


def test_unavailable_local_llm_does_not_use_fallback_or_save_a_draft(tmp_path):
    class UnavailableReportProvider(SyntheticReportProvider):
        def generate_plan(self, _):
            raise LocalLLMUnavailable("Yerel model bilinçli olarak kapalı.")

    service = CaseService(tmp_path, report_provider=UnavailableReportProvider())
    client = TestClient(create_app(service=service))
    case = client.post("/api/demo-case").json()
    _approve_all_critical_fields(client, case["case_id"])

    response = client.post(f"/api/cases/{case['case_id']}/report-drafts")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "llm_unavailable"
    assert not list((tmp_path / "cases" / case["case_id"] / "reports").iterdir())


def test_paddle_3x_json_envelope_keeps_text_confidence_and_polygon():
    class PaddleResult:
        json = json.dumps(
            {
                "res": {
                    "rec_texts": ["SENTETİK"],
                    "rec_scores": [0.91],
                    "dt_polys": [[[10, 12], [80, 12], [80, 30], [10, 30]]],
                }
            }
        )

    lines = PaddleOcrProvider()._adapt_predict_output([PaddleResult()], page_number=1)

    assert len(lines) == 1
    assert lines[0].text == "SENTETİK"
    assert lines[0].confidence == 0.91
    assert lines[0].polygon == [[10.0, 12.0], [80.0, 12.0], [80.0, 30.0], [10.0, 30.0]]
