"""Kurumsal Word şablonunu yalnızca onaylı yerel verilerle doldurma katmanı."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import warnings
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .extraction import get_field, tckn_is_valid


TEMPLATE_FILE_NAME = "adli-rapor-sablonu-v2.docx"
MAPPING_FILE_NAME = "kurumsal-girdiler_mapping_alan-esleme-v2.json"
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-z_]+(?:\.[a-z_]+)+)\s*\}\}")
DATE_PATTERN = re.compile(r"^\d{2}[./]\d{2}[./]\d{4}$")
DATE_TIME_PATTERN = re.compile(r"^\d{2}[./]\d{2}[./]\d{4}\s(?:[01]\d|2[0-3]):[0-5]\d$")
UNRESOLVED_PATTERN = re.compile(r"\{\{|\}\}|\b(?:None|null)\b|(?:\.\.\.|…{2,})", re.IGNORECASE)


class DocxGenerationError(RuntimeError):
    """Word üretimi için kullanıcıya açık hata."""

    def __init__(self, message: str, *, code: str = "docx_generation_failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TemplateContract:
    template_path: Path
    mapping_path: Path
    field_paths: frozenset[str]
    source_paths: tuple[str, ...]
    template_hash: str
    mapping_hash: str


class InstitutionalDocxGenerator:
    """JSON eşlemesini doğrulayan ve gerçek DOCX şablonunu dolduran adaptör."""

    def __init__(self, template_dir: Path) -> None:
        self.template_dir = template_dir

    @classmethod
    def from_configured_directory(cls, configured_directory: str | None) -> "InstitutionalDocxGenerator":
        fallback = Path(__file__).resolve().parents[2] / "Templates"
        return cls(Path(configured_directory) if configured_directory else fallback)

    @property
    def template_path(self) -> Path:
        return self.template_dir / TEMPLATE_FILE_NAME

    @property
    def mapping_path(self) -> Path:
        return self.template_dir / MAPPING_FILE_NAME

    def status(self) -> dict[str, Any]:
        try:
            contract = self.load_contract()
            self._ensure_runtime()
        except DocxGenerationError as error:
            return {
                "available": False,
                "blockers": [{"code": error.code, "message": str(error)}],
                "template": None,
                "sayi_mode": "manual",
                "sayi_auto_generate": False,
            }
        return {
            "available": True,
            "blockers": [],
            "template": {
                "file_name": contract.template_path.name,
                "sha256": contract.template_hash,
                "mapped_field_count": len(contract.field_paths),
            },
            "sayi_mode": "manual",
            "sayi_auto_generate": False,
        }

    def load_contract(self) -> TemplateContract:
        missing = [
            path.name
            for path in (self.template_path, self.mapping_path)
            if not path.is_file()
        ]
        if missing:
            raise DocxGenerationError(
                "Kurumsal Word üretim girdileri bulunamadı: " + ", ".join(missing),
                code="docx_contract_files_missing",
            )

        try:
            mapping_paths, source_paths = _read_mapping(self.mapping_path, self.template_path.name)
            template_paths = _read_template_paths(self.template_path)
        except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
            raise DocxGenerationError(
                "Kurumsal Word şablonu veya alan eşlemesi okunamadı.",
                code="docx_contract_unreadable",
            ) from error

        if mapping_paths != template_paths:
            raise DocxGenerationError(
                "JSON alan eşlemesi ile Word şablonundaki yer tutucular bire bir uyuşmuyor.",
                code="docx_mapping_template_mismatch",
            )

        return TemplateContract(
            template_path=self.template_path,
            mapping_path=self.mapping_path,
            field_paths=frozenset(mapping_paths),
            source_paths=source_paths,
            template_hash=_sha256(self.template_path),
            mapping_hash=_sha256(self.mapping_path),
        )

    def render(
        self,
        *,
        extraction: dict[str, Any],
        word_input: dict[str, str],
        output_dir: Path,
    ) -> tuple[Path, TemplateContract, list[str]]:
        contract = self.load_contract()
        self._ensure_runtime()
        context = _build_context(extraction, word_input, contract.field_paths)
        output_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix="word-", suffix=".docx", dir=output_dir)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            from docxtpl import DocxTemplate

            document = DocxTemplate(str(contract.template_path))
            document.render(context, autoescape=True)
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Duplicate name: 'docProps/core.xml'", category=UserWarning)
                document.save(str(temporary))
            _deduplicate_package_members(temporary)
            _assert_rendered_document_is_resolved(temporary)
        except DocxGenerationError:
            temporary.unlink(missing_ok=True)
            raise
        except Exception as error:
            temporary.unlink(missing_ok=True)
            raise DocxGenerationError(
                "Kurumsal Word şablonu doldurulamadı; şablon bütünlüğünü kontrol edin.",
                code="docx_render_failed",
            ) from error
        return temporary, contract, list(contract.source_paths)

    @staticmethod
    def _ensure_runtime() -> None:
        try:
            import docxtpl  # noqa: F401
        except ImportError as error:
            raise DocxGenerationError(
                "Yerel Word üretim çalışma zamanı kurulu değil; Docker imajını yeniden oluşturun.",
                code="docx_runtime_unavailable",
            ) from error


def validate_word_input(values: dict[str, str]) -> dict[str, str]:
    required = {
        "document_number": "Manuel SAYI",
        "document_date": "Rapor düzenleme tarihi",
        "examination_date": "Muayene tarih ve saati",
        "history": "Anamnez ve olay öyküsü",
        "current_exam_findings": "Güncel muayene bulguları",
    }
    normalised = {key: str(values.get(key, "")).strip() for key in required}
    missing = [label for key, label in required.items() if not normalised[key]]
    if missing:
        raise DocxGenerationError(
            "Word üretimi için şu kullanıcı girdileri zorunludur: " + ", ".join(missing),
            code="docx_input_incomplete",
        )
    if not normalised["document_number"].isprintable() or "\n" in normalised["document_number"] or "\r" in normalised["document_number"]:
        raise DocxGenerationError(
            "SAYI tek satırlık, yazdırılabilir bir değer olmalıdır.",
            code="invalid_document_number",
        )
    document_date = _parse_date(normalised["document_date"], "Rapor düzenleme tarihi")
    examination_date = _parse_date_time(normalised["examination_date"])
    if len(normalised["history"]) > 4_000 or len(normalised["current_exam_findings"]) > 4_000:
        raise DocxGenerationError("Word kullanıcı girdilerinden biri izin verilen uzunluğu aşıyor.", code="docx_input_too_long")
    for value in normalised.values():
        if UNRESOLVED_PATTERN.search(value):
            raise DocxGenerationError(
                "Word kullanıcı girdilerinde çözülmemiş yer tutucu veya geçersiz sabit değer bulunuyor.",
                code="docx_input_unresolved",
            )
    normalised["document_date"] = document_date.strftime("%d/%m/%Y")
    normalised["examination_date"] = examination_date.strftime("%d.%m.%Y %H:%M")
    return normalised


def _build_context(
    extraction: dict[str, Any], word_input: dict[str, str], mapped_paths: frozenset[str]
) -> dict[str, dict[str, str]]:
    values = validate_word_input(word_input)

    def approved(path: str) -> str:
        field = get_field(extraction, path)
        value = field["value"]
        if not field["approved"] or field["status"] in {"missing", "conflict"} or not isinstance(value, str) or not value.strip():
            raise DocxGenerationError(
                f"{path} alanı kaynaklı ve kullanıcı onaylı olmadan Word'e aktarılamaz.",
                code="docx_approval_required",
            )
        return value.strip()

    def approved_list(path: str) -> str:
        field = get_field(extraction, path)
        value = field["value"]
        if (
            not field["approved"]
            or field["status"] in {"missing", "conflict"}
            or not isinstance(value, list)
            or not value
            or not all(isinstance(item, str) and item.strip() for item in value)
        ):
            raise DocxGenerationError(
                f"{path} alanı kaynaklı ve kullanıcı onaylı olmadan Word'e aktarılamaz.",
                code="docx_approval_required",
            )
        return "; ".join(item.strip().rstrip(".") for item in value)

    tckn = approved("patient.tckn")
    if not tckn_is_valid(tckn):
        raise DocxGenerationError(
            "TCKN checksum doğrulamasından geçmeden Word'e aktarılamaz.",
            code="invalid_tckn",
        )
    birth_info = _approved_birth_info(extraction)
    life_threat = approved("medical.life_threat")
    simple_intervention = approved("medical.simple_medical_intervention")
    if life_threat not in {"yes", "no"} or simple_intervention not in {"yes", "no"}:
        raise DocxGenerationError(
            "Hayati tehlike ve BTM sonucu yalnızca kullanıcı onaylı evet/hayır değeriyle Word'e aktarılabilir.",
            code="docx_conclusion_incomplete",
        )

    examination = _parse_date_time(values["examination_date"])
    resolved = {
        "document.number": values["document_number"],
        "document.date": values["document_date"],
        "request.sender_authority": approved("request.sender_authority"),
        "request.letter_date": _display_date(approved("request.letter_date")),
        "request.letter_number": approved("request.letter_number"),
        "request.incident": approved("request.incident").rstrip(" .;"),
        "request.requested_questions": approved_list("request.requested_questions"),
        "patient.tckn": tckn,
        "medical.protocol_number": approved("medical.protocol_number"),
        "patient.full_name": approved("patient.full_name"),
        "patient.birth_info": birth_info,
        "medical.issuing_institution": approved("medical.issuing_institution"),
        "medical.report_date": _display_date(approved("medical.report_date")),
        "medical.report_number": approved("medical.report_number"),
        "medical.incident_type": approved("medical.incident_type").rstrip(" .;"),
        "medical.clinical_findings": approved("medical.clinical_findings").rstrip(" .;"),
        "medical.general_forensic_exam_summary": approved("medical.general_forensic_exam_summary").rstrip(" .;"),
        "medical.btm_record_phrase": {
            "yes": "giderilebilecek derecede hafif nitelikte olduğu",
            "no": "giderilemeyecek derecede olduğu",
        }[simple_intervention],
        "medical.life_threat_record_phrase": {"yes": "bulunduğu", "no": "bulunmadığı"}[life_threat],
        "medical.life_threat_conclusion": {"yes": "SOKTUĞU", "no": "SOKMADIĞI"}[life_threat],
        "medical.btm_conclusion": {"yes": "OLDUĞU", "no": "OLMADIĞI"}[simple_intervention],
        "manual.examination_date": examination.strftime("%d/%m/%Y"),
        "manual.examination_time": examination.strftime("%H:%M"),
        "manual.history": values["history"].rstrip("."),
        "manual.current_exam_findings": values["current_exam_findings"].rstrip("."),
    }
    if set(resolved) != mapped_paths:
        raise DocxGenerationError(
            "Kurumsal alan eşlemesinde uygulamanın desteklemediği veya eksik bir alan yolu var.",
            code="docx_mapping_not_supported",
        )
    context: dict[str, dict[str, str]] = {"document": {}, "request": {}, "patient": {}, "medical": {}, "manual": {}}
    for path, value in resolved.items():
        group, name = path.split(".", 1)
        context[group][name] = value
    return context


def _approved_birth_info(extraction: dict[str, Any]) -> str:
    parts: list[str] = []
    for path in ("patient.birth_place", "patient.birth_date"):
        field = get_field(extraction, path)
        if field["approved"] and field["status"] not in {"missing", "conflict"} and isinstance(field["value"], str) and field["value"].strip():
            parts.append(field["value"].strip())
    return " / ".join(parts)


def _read_mapping(path: Path, expected_template: str) -> tuple[set[str], tuple[str, ...]]:
    mapping = json.loads(path.read_text(encoding="utf-8"))
    if mapping.get("schema_version") != "2.0.0" or mapping.get("template_file") != expected_template:
        raise ValueError("Alan eşlemesi sürümü veya şablon adı geçersiz.")
    policy = mapping.get("document_number_policy")
    if not isinstance(policy, dict) or policy.get("mode") != "manual" or policy.get("auto_generate") is not False:
        raise ValueError("SAYI alanı yalnızca manuel olacak biçimde tanımlanmalıdır.")
    fields = mapping.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("Alan eşlemesinde alan bulunamadı.")
    paths: set[str] = set()
    sources: list[str] = []
    for item in fields:
        if not isinstance(item, dict):
            raise ValueError("Alan eşleme satırı nesne olmalıdır.")
        context_path = str(item.get("context_path", "")).strip()
        source_paths = item.get("source_paths")
        if not PLACEHOLDER_PATTERN.fullmatch("{{ " + context_path + " }}") or not isinstance(source_paths, list) or not source_paths:
            raise ValueError("Alan eşleme satırında bağlam veya kaynak yolu geçersiz.")
        if context_path in paths:
            raise ValueError("Alan eşlemesinde yinelenen kanonik yol var.")
        paths.add(context_path)
        for source in source_paths:
            if not isinstance(source, str) or "." not in source:
                raise ValueError("Alan eşlemesinde geçersiz kaynak yolu var.")
            if source not in sources:
                sources.append(source)
    return paths, tuple(sources)


def _read_template_paths(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        fragments = [archive.read(name).decode("utf-8", errors="replace") for name in archive.namelist() if name.startswith("word/") and name.endswith(".xml")]
    return set(PLACEHOLDER_PATTERN.findall("\n".join(fragments)))


def _assert_rendered_document_is_resolved(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        text_parts: list[str] = []
        for name in archive.namelist():
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            try:
                root = ElementTree.fromstring(archive.read(name))
            except ElementTree.ParseError as error:
                raise DocxGenerationError("Üretilen Word paketi okunamadı.", code="docx_output_invalid") from error
            text_parts.extend(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
    if UNRESOLVED_PATTERN.search("\n".join(text_parts)):
        raise DocxGenerationError(
            "Üretilen Word belgesinde çözülmemiş yer tutucu bulundu; dosya kaydedilmedi.",
            code="docx_output_unresolved",
        )


def _deduplicate_package_members(path: Path) -> None:
    """Bazı LibreOffice kökenli şablonlarda docxtpl'in çoğalttığı ZIP parçasını temizler."""

    with zipfile.ZipFile(path, "r") as source:
        members = source.infolist()
        if len(members) == len({member.filename for member in members}):
            return
        last_member = {member.filename: member for member in members}
        descriptor, replacement_name = tempfile.mkstemp(prefix="docx-package-", suffix=".docx", dir=path.parent)
        os.close(descriptor)
        replacement = Path(replacement_name)
        try:
            with zipfile.ZipFile(replacement, "w") as target:
                for member in members:
                    if last_member[member.filename] is member:
                        target.writestr(member, source.read(member))
        except Exception:
            replacement.unlink(missing_ok=True)
            raise
    os.replace(replacement, path)


def _parse_date(value: str, label: str) -> datetime:
    if not DATE_PATTERN.fullmatch(value):
        raise DocxGenerationError(f"{label} `GG.AA.YYYY` veya `GG/AA/YYYY` biçiminde olmalıdır.", code="invalid_document_date")
    try:
        return datetime.strptime(value.replace("/", "."), "%d.%m.%Y")
    except ValueError as error:
        raise DocxGenerationError(f"{label} geçerli bir tarih değil.", code="invalid_document_date") from error


def _parse_date_time(value: str) -> datetime:
    if not DATE_TIME_PATTERN.fullmatch(value):
        raise DocxGenerationError(
            "Muayene tarih ve saati `GG.AA.YYYY SS:DD` veya `GG/AA/YYYY SS:DD` biçiminde olmalıdır.",
            code="invalid_examination_date",
        )
    try:
        return datetime.strptime(value.replace("/", "."), "%d.%m.%Y %H:%M")
    except ValueError as error:
        raise DocxGenerationError("Muayene tarih ve saati geçerli değil.", code="invalid_examination_date") from error


def _display_date(value: str) -> str:
    return _parse_date(value, "Kaynak belge tarihi").strftime("%d/%m/%Y")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
