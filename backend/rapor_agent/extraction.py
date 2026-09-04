"""LLM kullanmadan, OCR satirlarindan kaynakli alan cikaran kurallar."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Iterable


CRITICAL_PATHS = {
    "patient.full_name",
    "patient.tckn",
    "patient.birth_date",
    "request.sender_authority",
    "request.letter_date",
    "request.letter_number",
    "request.incident",
    "request.requested_questions",
    "medical.issuing_institution",
    "medical.report_date",
    "medical.report_number",
    "medical.incident_date_time",
    "medical.incident_type",
    "medical.clinical_findings",
    "medical.life_threat",
    "medical.simple_medical_intervention",
}

PATIENT_NAME_LABELS = (
    "Adı Soyadı",
    "Ad Soyad",
    "Adı ve Soyadı",
    "Hasta Adı Soyadı",
    "Muayene Edilen Adı Soyadı",
)
EXAMINER_CONTEXT = re.compile(r"\b(?:muayene\s+eden|muayeneyi\s+yapan|hekim|doktor|tabip|düzenleyen|raporu\s+düzenleyen|imza)\b", re.IGNORECASE)
PATIENT_CONTEXT = re.compile(r"\b(?:hasta|muayene\s+edilen|müracaat\s+eden|başvuran)\b", re.IGNORECASE)
EXAMINER_NAME_PREFIX = re.compile(r"^\s*(?:(?:op\.?\s*)?dr\.?|uzm\.?|prof\.?|doç\.?|hekim|doktor|tabip)\b", re.IGNORECASE)


def extract_case(case_id: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Kurallarla cikartir; coklu adayda sessizce bir deger secmez."""
    classified = [_classify_document(document) for document in documents]
    candidates = _collect_candidates(classified)

    extraction = {
        "schema_version": "1.2.0",
        "case_id": case_id,
        "patient": {
            "full_name": _merge(candidates["patient.full_name"]),
            "tckn": _merge(candidates["patient.tckn"]),
            "birth_place": _merge(candidates["patient.birth_place"]),
            "birth_date": _merge(candidates["patient.birth_date"]),
        },
        "request": {
            "sender_authority": _merge(candidates["request.sender_authority"]),
            "letter_date": _merge(candidates["request.letter_date"]),
            "letter_number": _merge(candidates["request.letter_number"]),
            "incident": _merge(candidates["request.incident"]),
            "requested_questions": _merge(candidates["request.requested_questions"], array_value=True),
        },
        "documents": [
            {
                "document_id": document["document_id"],
                "type": document["type"],
                "file_name": document["file_name"],
                "page_count": len(document.get("pages", [])),
                "classification_confidence": document.get("classification_confidence"),
                "user_confirmed_type": document.get("user_confirmed_type", False),
            }
            for document in classified
        ],
        "medical": {
            "issuing_institution": _merge(candidates["medical.issuing_institution"]),
            "protocol_number": _merge(candidates["medical.protocol_number"]),
            "report_date": _merge(candidates["medical.report_date"]),
            "report_number": _merge(candidates["medical.report_number"]),
            "incident_date_time": _merge(candidates["medical.incident_date_time"]),
            "incident_type": _merge(candidates["medical.incident_type"]),
            "clinical_findings": _merge(candidates["medical.clinical_findings"]),
            "general_forensic_exam_summary": _merge(candidates["medical.general_forensic_exam_summary"]),
            "epicrisis_summary": _missing(),
            "department_exam_summary": _missing(),
            "life_threat": _merge(candidates["medical.life_threat"], opinion=True),
            "simple_medical_intervention": _merge(candidates["medical.simple_medical_intervention"], opinion=True),
        },
        "warnings": [],
        "ready_to_generate": False,
    }
    extraction["warnings"] = _warnings_for(extraction)
    return extraction


def _classify_document(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("user_confirmed_type"):
        return document
    text = " ".join(line["text"] for line in document.get("ocr_lines", []))
    normalized = text.upper()
    if re.search(r"GENEL\s+ADL[İI]\s+MUAYENE", normalized):
        document["type"] = "general_forensic_exam"
        document["classification_confidence"] = 0.99
    elif re.search(r"EP[İI]KR[İI]Z|ACİL\s+SERVİS", normalized):
        document["type"] = "epicrisis"
        document["classification_confidence"] = 0.90
    elif re.search(r"ADL[İI]\s+TIP", normalized):
        document["type"] = "department_exam_note"
        document["classification_confidence"] = 0.85
    elif "EMNİYET" in normalized or "ÜST YAZI" in normalized or "İSTENEN HUSUSLAR" in normalized:
        document["type"] = "cover_letter"
        document["classification_confidence"] = 0.93
    else:
        document["type"] = "unknown"
        document["classification_confidence"] = None
    return document


def _collect_candidates(documents: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    fields: dict[str, list[dict[str, Any]]] = {
        "patient.full_name": [],
        "patient.tckn": [],
        "patient.birth_place": [],
        "patient.birth_date": [],
        "request.sender_authority": [],
        "request.letter_date": [],
        "request.letter_number": [],
        "request.incident": [],
        "request.requested_questions": [],
        "medical.issuing_institution": [],
        "medical.protocol_number": [],
        "medical.report_date": [],
        "medical.report_number": [],
        "medical.incident_date_time": [],
        "medical.incident_type": [],
        "medical.clinical_findings": [],
        "medical.general_forensic_exam_summary": [],
        "medical.life_threat": [],
        "medical.simple_medical_intervention": [],
    }
    for document in documents:
        document_type = document["type"]
        lines = document.get("ocr_lines", [])

        # Kimlik alanları belge türünden bağımsız olarak kanıtlanabilir; birden
        # fazla belgede farklı değer bulunursa _merge alanı conflict yapar.
        _append_label(
            fields["patient.full_name"],
            document,
            lines,
            PATIENT_NAME_LABELS,
            _patient_name_value,
            skip_label=_is_examiner_name_label,
            collect_all=True,
        )
        _append_label(
            fields["patient.tckn"],
            document,
            lines,
            ("TCKN", "T.C. Kimlik No", "T.C Kimlik No", "TC Kimlik No", "T.C. Kimlik Numarası", "TC Kimlik Numarası"),
            _digits_only,
        )
        _append_label(fields["patient.birth_place"], document, lines, ("Doğum Yeri", "Doğum Yeri (İl)"))
        _append_label(fields["patient.birth_date"], document, lines, ("Doğum Tarihi", "Doğum Tarihi (Gün/Ay/Yıl)"), _canonical_date)
        _append_birth_place_and_date(fields["patient.birth_place"], fields["patient.birth_date"], document, lines)
        _append_spatial_label(
            fields["patient.full_name"],
            document,
            lines,
            PATIENT_NAME_LABELS,
            _patient_name_value,
            skip_label=_is_examiner_name_label,
            collect_all=True,
        )
        _append_spatial_label(
            fields["patient.tckn"],
            document,
            lines,
            ("TCKN", "T.C. Kimlik No", "T.C Kimlik No", "TC Kimlik No", "T.C. Kimlik Numarası", "TC Kimlik Numarası"),
            _tckn_digits,
        )
        _append_spatial_label(fields["patient.birth_place"], document, lines, ("Doğum Yeri", "Doğum Yeri (İl)"), _name_value)
        _append_spatial_label(fields["patient.birth_date"], document, lines, ("Doğum Tarihi", "Doğum Tarihi (Gün/Ay/Yıl)"), _canonical_date)
        _append_spatial_birth_place_and_date(fields["patient.birth_place"], fields["patient.birth_date"], document, lines)

        if document_type == "cover_letter":
            if lines:
                _append_candidate(fields["request.sender_authority"], document, lines[0], lines[0]["text"].strip())
            _append_label(fields["request.letter_date"], document, lines, ("Tarih",), _canonical_date)
            _append_label(fields["request.letter_number"], document, lines, ("Sayı",))
            _append_label(fields["request.incident"], document, lines, ("Olay",))
            _append_label(fields["request.requested_questions"], document, lines, ("İstenen Hususlar",), lambda value: [value])
        elif document_type in {"general_forensic_exam", "epicrisis", "department_exam_note"}:
            _append_label(
                fields["medical.protocol_number"],
                document,
                lines,
                ("Protokol No", "Protokol No.", "Protokol Numarası", "Protokol Numarasi"),
            )
            _append_label(
                fields["medical.report_number"],
                document,
                lines,
                ("Rapor Sayısı", "Rapor No", "Rapor No.", "Rapor Numarası", "Rapor Numarasi"),
            )

        if document_type == "general_forensic_exam":
            _append_label(fields["medical.issuing_institution"], document, lines, ("Kurum",))
            _append_label(fields["medical.report_date"], document, lines, ("Rapor Tarihi",), _canonical_date)
            _append_label(fields["medical.incident_date_time"], document, lines, ("Başvuru/Olay Tarihi",), _canonical_date_time)
            _append_label(fields["medical.incident_type"], document, lines, ("Başvuru Nedeni",))
            _append_label(fields["medical.clinical_findings"], document, lines, ("Klinik Bulgular",))
            _append_label(fields["medical.general_forensic_exam_summary"], document, lines, ("Klinik Bulgular",))
            _append_label(fields["medical.life_threat"], document, lines, ("Hayati Tehlike",), _opinion_value)
            _append_label(fields["medical.simple_medical_intervention"], document, lines, ("BTM",), _opinion_value)
    return fields


def _append_birth_place_and_date(
    place_destination: list[dict[str, Any]],
    date_destination: list[dict[str, Any]],
    document: dict[str, Any],
    lines: list[dict[str, Any]],
) -> None:
    """Tek satırdaki “Doğum Yeri ve Tarihi” bilgisini iki alan olarak kanıtlar."""
    label = re.compile(
        r"^\s*Doğum\s+Yeri\s*(?:/|ve)?\s*Tarihi\s*[:\-]\s*(.+?)\s*$",
        re.IGNORECASE,
    )
    date_expression = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}")
    for line in lines:
        matched = label.match(line["text"])
        if not matched:
            continue
        combined_value = matched.group(1).strip()
        date_match = date_expression.search(combined_value)
        if not date_match:
            return
        original_date = date_match.group(0)
        canonical_date = _canonical_date(original_date)
        if canonical_date is not None:
            _append_candidate(date_destination, document, line, canonical_date, original_date)
        if date_match.start() == 0:
            place = combined_value[date_match.end() :]
        else:
            place = combined_value[: date_match.start()]
        place = place.strip(" /,;-")
        if place:
            _append_candidate(place_destination, document, line, place)
        return


def _append_spatial_label(
    destination: list[dict[str, Any]],
    document: dict[str, Any],
    lines: list[dict[str, Any]],
    labels: tuple[str, ...],
    transform: Callable[[str], str | list[str] | None] | None = None,
    *,
    skip_label: Callable[[dict[str, Any], list[dict[str, Any]]], bool] | None = None,
    collect_all: bool = False,
) -> None:
    """Ayrı OCR kutularındaki etiket ve aynı form satırındaki değeri eşleştirir."""
    label_expression = "|".join(re.escape(label) for label in labels)
    expression = re.compile(rf"^\s*(?:{label_expression})\s*[:\-]?\s*$", re.IGNORECASE)
    for line in lines:
        if not expression.match(line["text"]) or (skip_label and skip_label(line, lines)):
            continue
        value_line = _same_row_value_line(line, lines)
        if value_line is None:
            continue
        original_value = value_line["text"].strip()
        value = transform(original_value) if transform else original_value
        if value is not None:
            stored_original = [original_value] if isinstance(value, list) else original_value
            _append_candidate(destination, document, value_line, value, stored_original)
            if not collect_all:
                return


def _append_spatial_birth_place_and_date(
    place_destination: list[dict[str, Any]],
    date_destination: list[dict[str, Any]],
    document: dict[str, Any],
    lines: list[dict[str, Any]],
) -> None:
    label = re.compile(r"^\s*Doğum\s+Yeri\s*(?:/|ve)\s*Tarihi\s*[:\-]?\s*$", re.IGNORECASE)
    date_expression = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}")
    for line in lines:
        if not label.match(line["text"]):
            continue
        value_line = _same_row_value_line(line, lines)
        if value_line is None:
            continue
        combined_value = value_line["text"].strip()
        date_match = date_expression.search(combined_value)
        if date_match is None:
            return
        original_date = date_match.group(0)
        canonical_date = _canonical_date(original_date)
        if canonical_date is not None:
            _append_candidate(date_destination, document, value_line, canonical_date, original_date)
        place = (combined_value[date_match.end() :] if date_match.start() == 0 else combined_value[: date_match.start()]).strip(" /,;-")
        if place:
            _append_candidate(place_destination, document, value_line, place)
        return


def _same_row_value_line(label_line: dict[str, Any], lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Etiketin sağına hizalanmış, başka bir etiket olmayan en yakın OCR kutusunu döndürür."""
    label_left, label_top, label_right, label_bottom = _polygon_bounds(label_line["polygon"])
    label_height = max(1.0, label_bottom - label_top)
    candidates: list[tuple[float, dict[str, Any]]] = []
    for candidate in lines:
        if candidate is label_line or not candidate["text"].strip():
            continue
        left, top, right, bottom = _polygon_bounds(candidate["polygon"])
        overlap = max(0.0, min(label_bottom, bottom) - max(label_top, top))
        candidate_height = max(1.0, bottom - top)
        gap = left - label_right
        if gap < 0 or gap > max(180.0, label_height * 8):
            continue
        if overlap < min(label_height, candidate_height) * 0.4:
            continue
        if _looks_like_form_label(candidate["text"]):
            continue
        candidates.append((gap, candidate))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _polygon_bounds(polygon: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [float(point[0]) for point in polygon]
    ys = [float(point[1]) for point in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _looks_like_form_label(value: str) -> bool:
    return bool(
        re.match(
            r"^\s*(?:Adı\s+Soyadı|Ad\s+Soyad|T\.?C\.?\s+Kimlik(?:\s+No(?:marası)?)?|TCKN|Doğum\s+Yeri(?:\s*(?:/|ve)\s*Tarihi)?|Protokol\s+(?:No|Numarası)|Rapor\s+(?:No|Numarası|Sayısı))\s*[:\-]?\s*$",
            value,
            re.IGNORECASE,
        )
    )


def _is_examiner_name_label(label_line: dict[str, Any], lines: list[dict[str, Any]]) -> bool:
    """Genel “Adı Soyadı” etiketinin hastaya mı, muayene edene mi ait olduğunu ayırır."""
    label_text = label_line["text"]
    if PATIENT_CONTEXT.search(label_text):
        return False
    if EXAMINER_CONTEXT.search(label_text):
        return True

    left, top, right, bottom = _polygon_bounds(label_line["polygon"])
    height = max(1.0, bottom - top)
    contexts: list[tuple[float, str]] = []
    for context_line in lines:
        if context_line is label_line or context_line.get("page") != label_line.get("page"):
            continue
        text = context_line["text"]
        role = "patient" if PATIENT_CONTEXT.search(text) else "examiner" if EXAMINER_CONTEXT.search(text) else None
        if role is None:
            continue
        context_left, context_top, context_right, context_bottom = _polygon_bounds(context_line["polygon"])
        horizontal_overlap = max(0.0, min(right, context_right) - max(left, context_left))
        is_stacked_context = (
            0 <= top - context_bottom <= max(120.0, height * 5)
            and (horizontal_overlap > 0 or abs(context_left - left) <= max(180.0, height * 8))
        )
        same_row_gap = left - context_right
        is_left_context = abs(((context_top + context_bottom) / 2) - ((top + bottom) / 2)) <= height and 0 <= same_row_gap <= 240
        if is_stacked_context or is_left_context:
            distance = abs(top - context_bottom) + abs(context_left - left)
            contexts.append((distance, role))
    return bool(contexts) and min(contexts, key=lambda item: item[0])[1] == "examiner"


def _append_label(
    destination: list[dict[str, Any]],
    document: dict[str, Any],
    lines: list[dict[str, Any]],
    labels: tuple[str, ...],
    transform: Callable[[str], str | list[str] | None] | None = None,
    *,
    skip_label: Callable[[dict[str, Any], list[dict[str, Any]]], bool] | None = None,
    collect_all: bool = False,
) -> None:
    label_expression = "|".join(re.escape(label) for label in labels)
    expression = re.compile(rf"^\s*(?:{label_expression})\s*[:\-]\s*(.+?)\s*$", re.IGNORECASE)
    for line in lines:
        match = expression.match(line["text"])
        if not match or (skip_label and skip_label(line, lines)):
            continue
        original_value = match.group(1).strip()
        value = transform(original_value) if transform else original_value
        if value is not None:
            stored_original = [original_value] if isinstance(value, list) else original_value
            _append_candidate(destination, document, line, value, stored_original)
            if not collect_all:
                return


def _append_candidate(
    destination: list[dict[str, Any]],
    document: dict[str, Any],
    line: dict[str, Any],
    value: str | list[str],
    original_value: str | list[str] | None = None,
) -> None:
    destination.append(
        {
            "value": value,
            "original_value": original_value if original_value is not None else value,
            "provenance": {
                "source_document_id": document["document_id"],
                "page": line["page"],
                "evidence_text": line["text"],
                "ocr_confidence": line["confidence"],
                "polygon": line["polygon"],
            },
        }
    )


def _merge(candidates: list[dict[str, Any]], *, array_value: bool = False, opinion: bool = False) -> dict[str, Any]:
    if not candidates:
        return _missing(array_value=array_value, opinion=opinion)
    unique = {_comparable(candidate["value"]) for candidate in candidates}
    provenance = candidates[0]["provenance"]
    if len(unique) > 1:
        return {
            "value": None,
            "original_value": None,
            "status": "conflict",
            "approved": False,
            "provenance": provenance,
            "candidates": candidates,
        }
    return {
        "value": candidates[0]["value"],
        "original_value": candidates[0]["original_value"],
        "status": "extracted",
        "approved": False,
        "provenance": provenance,
        "candidates": candidates,
    }


def _missing(*, array_value: bool = False, opinion: bool = False) -> dict[str, Any]:
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


def _warnings_for(extraction: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for document in extraction["documents"]:
        if document["type"] == "unknown":
            warnings.append(
                {
                    "code": "document_type_unknown",
                    "message": "Belge türü belirlenemedi; belge kartından türü seçip alan çıkarımını yeniden çalıştırın.",
                    "severity": "blocking",
                    "field_path": None,
                }
            )
    for path, field in _iter_fields(extraction):
        if field["status"] in {"missing", "conflict"}:
            warnings.append(
                {
                    "code": f"field_{field['status']}",
                    "message": "Alan için kaynak bulunamadı." if field["status"] == "missing" else "Birden çok kaynak farklı değer içeriyor; kullanıcı seçimi gerekli.",
                    "severity": "blocking" if path in CRITICAL_PATHS else "warning",
                    "field_path": path,
                }
            )
        elif path in CRITICAL_PATHS and field["provenance"]["ocr_confidence"] is not None and field["provenance"]["ocr_confidence"] < 0.85:
            warnings.append(
                {
                    "code": "critical_field_low_ocr_confidence",
                    "message": "Kritik alanın OCR güveni düşük; kullanıcı düzeltmesi veya onayı gerekli.",
                    "severity": "blocking",
                    "field_path": path,
                }
            )
    tckn = extraction["patient"]["tckn"]
    if tckn["status"] not in {"missing", "conflict"} and not tckn_is_valid(tckn["value"]):
        warnings.append(
            {
                "code": "invalid_tckn_checksum",
                "message": "TCKN checksum doğrulamasından geçmedi; kaynak görüntüden düzeltip yeniden onaylayın.",
                "severity": "blocking",
                "field_path": "patient.tckn",
            }
        )
    return warnings


def refresh_warnings(extraction: dict[str, Any]) -> None:
    extraction["warnings"] = _warnings_for(extraction)


def _iter_fields(extraction: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for group in ("patient", "request", "medical"):
        for name, field in extraction[group].items():
            yield f"{group}.{name}", field


def get_field(extraction: dict[str, Any], field_path: str) -> dict[str, Any]:
    if field_path not in {path for path, _ in _iter_fields(extraction)}:
        raise KeyError("Bilinmeyen alan yolu.")
    group, name = field_path.split(".", 1)
    return extraction[group][name]


def set_field_value(extraction: dict[str, Any], field_path: str, value: str | list[str] | None) -> None:
    field = get_field(extraction, field_path)
    field["value"] = value
    field["original_value"] = value
    field["status"] = "user_corrected" if value not in (None, "", []) else "missing"
    field["approved"] = False
    field["candidates"] = []


def tckn_is_valid(value: str | None) -> bool:
    if value is None or not re.fullmatch(r"[1-9]\d{10}", value):
        return False
    digits = [int(character) for character in value]
    tenth = ((sum(digits[0:9:2]) * 7) - sum(digits[1:8:2])) % 10
    return digits[9] == tenth and digits[10] == sum(digits[:10]) % 10


def _canonical_date(value: str) -> str | None:
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", value)
    if not match:
        return None
    try:
        return datetime(int(match.group(3)), int(match.group(2)), int(match.group(1))).strftime("%d.%m.%Y")
    except ValueError:
        return None


def _canonical_date_time(value: str) -> str | None:
    date = _canonical_date(value)
    if date is None:
        return None
    time = re.search(r"\b([01]?\d|2[0-3]):[0-5]\d\b", value)
    return f"{date} {time.group(0)}" if time else date


def _digits_only(value: str) -> str | None:
    digits = "".join(character for character in value if character.isdigit())
    return digits or None


def _tckn_digits(value: str) -> str | None:
    digits = _digits_only(value)
    return digits if digits is not None and len(digits) == 11 else None


def _name_value(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned if cleaned and not any(character.isdigit() for character in cleaned) else None


def _patient_name_value(value: str) -> str | None:
    cleaned = _name_value(value)
    return None if cleaned is None or EXAMINER_NAME_PREFIX.search(cleaned) else cleaned


def _opinion_value(value: str) -> str | None:
    normalized = value.casefold()
    if "yoktur" in normalized or "yok" in normalized:
        return "no"
    if "giderilebilir" in normalized:
        return "yes"
    if "vardır" in normalized or "vardir" in normalized:
        return "yes"
    if "belirtilmemiş" in normalized or "belirtilmemis" in normalized:
        return "not_stated"
    return None


def _comparable(value: str | list[str]) -> tuple[str, ...] | str:
    return tuple(value) if isinstance(value, list) else value
