"""Yerel Qwen planı ve yalnızca onaylı alanlarla rapor taslağı oluşturma."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .extraction import CRITICAL_PATHS, get_field
from .report_schema import ReportDraftSchemaError, validate_report_draft


PROMPT_VERSION = "report-plan-v1"
REPORT_DRAFT_SCHEMA_VERSION = "1.0.0"
MODEL_NAME = "Qwen3-8B"

SECTION_SOURCE_PATHS: dict[str, tuple[str, ...]] = {
    "introduction": (
        "patient.full_name",
        "request.sender_authority",
        "request.letter_date",
        "request.letter_number",
        "request.incident",
        "request.requested_questions",
    ),
    "general_forensic_exam": (
        "medical.issuing_institution",
        "medical.report_date",
        "medical.report_number",
        "medical.incident_date_time",
        "medical.incident_type",
        "medical.clinical_findings",
    ),
    "conclusion": (
        "medical.life_threat",
        "medical.simple_medical_intervention",
    ),
}


class ReportError(RuntimeError):
    """Taslak üretim katmanının kullanıcıya çevrilecek hatası."""


class ReportEligibilityError(ReportError):
    def __init__(self, missing_approvals: list[str]) -> None:
        self.missing_approvals = missing_approvals
        super().__init__("Taslak üretmek için tüm kritik alanlar kullanıcı tarafından onaylanmalıdır.")


class LocalLLMUnavailable(ReportError):
    pass


class LocalLLMOutputInvalid(ReportError):
    pass


class ReportPlanSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["introduction", "general_forensic_exam", "conclusion"]
    source_field_paths: list[str] = Field(min_length=1, max_length=8)


class ReportPlan(BaseModel):
    """LLM'nin yalnızca alan kullanımı bildirdiği dar ve denetlenebilir çıktı."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"]
    sections: list[ReportPlanSection] = Field(min_length=3, max_length=3)


class ReportPlanProvider(Protocol):
    def generate_plan(self, approved_context: dict[str, Any]) -> tuple[ReportPlan, dict[str, str]]:
        """Yerel model planını ve denetim için içeriksiz model meta verisini döndürür."""

    def status(self) -> dict[str, Any]:
        """Model yüklemeden kullanılabilirlik durumunu bildirir."""


class Qwen3LocalReportProvider:
    """Yerel Qwen3 klasörünü 4-bit GPU ile tembel olarak yükleyen adaptör.

    Model klasörü yalnızca Docker bind mount'u üzerinden okunur. Bağlantı hatasında
    CPU veya uzak servis geri dönüşü yapılmaz; taslak üretimi açık hatayla durur.
    """

    def __init__(self, model_dir: Path | None = None) -> None:
        configured = model_dir or Path(os.environ.get("RAPOR_AGENT_LLM_MODEL_DIR", "/models/qwen3-8b"))
        self.model_dir = configured
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._load_lock = threading.Lock()
        self._model_revision: str | None = None

    def status(self) -> dict[str, Any]:
        required = ("config.json", "tokenizer.json", "model.safetensors.index.json")
        missing = [name for name in required if not (self.model_dir / name).is_file()]
        runtime_available, runtime_error = _qwen_runtime_status()
        return {
            "provider": "qwen3_transformers_4bit",
            "model_name": MODEL_NAME,
            "model_path_configured": str(self.model_dir),
            "model_files_ready": not missing,
            "runtime_ready": runtime_available,
            "runtime_error": runtime_error,
            "loaded": self._model is not None,
            "missing_files": missing,
            "local_only": True,
        }

    def generate_plan(self, approved_context: dict[str, Any]) -> tuple[ReportPlan, dict[str, str]]:
        self._ensure_loaded()
        assert self._model is not None
        assert self._tokenizer is not None

        messages = [
            {"role": "system", "content": _load_prompt()},
            {"role": "user", "content": _plan_request(approved_context)},
        ]
        try:
            import torch

            prompt = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            model_inputs = self._tokenizer([prompt], return_tensors="pt").to(self._model.device)
            with torch.inference_mode():
                generated = self._model.generate(
                    **model_inputs,
                    do_sample=True,
                    temperature=0.1,
                    top_p=0.9,
                    max_new_tokens=280,
                    pad_token_id=self._tokenizer.eos_token_id,
                )
            output_ids = generated[0][len(model_inputs.input_ids[0]) :]
            raw_output = self._tokenizer.decode(output_ids, skip_special_tokens=True).strip()
        except Exception as error:
            raise LocalLLMUnavailable("Yerel Qwen plan üretimi tamamlanamadı; GPU ve model çalışma zamanını kontrol edin.") from error

        plan = _parse_report_plan(raw_output)
        _validate_plan_against_context(plan, approved_context)
        return plan, {
            "provider": "qwen3_transformers_4bit",
            "model_name": MODEL_NAME,
            "model_revision": self._model_revision or "yerel-model",
            "prompt_version": PROMPT_VERSION,
        }

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            state = self.status()
            if not state["model_files_ready"]:
                raise LocalLLMUnavailable("Yerel Qwen3 model dosyaları bağlanamadı; Docker model klasörü ayarını kontrol edin.")
            try:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
            except ImportError as error:
                raise LocalLLMUnavailable("Yerel Qwen çalışma zamanı kurulu değil; Docker imajını LLM bağımlılıklarıyla yeniden oluşturun.") from error

            if not torch.cuda.is_available():
                raise LocalLLMUnavailable("Yerel Qwen3 için NVIDIA GPU erişilemedi. Uzak veya CPU alternatifi kullanılmadı.")
            try:
                quantization = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                )
                tokenizer = AutoTokenizer.from_pretrained(self.model_dir, local_files_only=True)
                model = AutoModelForCausalLM.from_pretrained(
                    self.model_dir,
                    local_files_only=True,
                    torch_dtype=torch.bfloat16,
                    quantization_config=quantization,
                    device_map="auto",
                    low_cpu_mem_usage=True,
                )
            except Exception as error:
                raise LocalLLMUnavailable("Yerel Qwen3 modeli 4-bit GPU belleğine yüklenemedi. GPU belleğini ve model dosyalarını kontrol edin.") from error

            placements = set(getattr(model, "hf_device_map", {}).values())
            if any(str(place).startswith(("cpu", "disk")) for place in placements):
                del model
                torch.cuda.empty_cache()
                raise LocalLLMUnavailable("Yerel Qwen3 modeli GPU belleğine bütünüyle sığmadı; CPU'ya sessizce taşınmadı.")
            self._tokenizer = tokenizer
            self._model = model
            self._model_revision = _model_revision(self.model_dir)


def draft_eligibility(extraction: dict[str, Any] | None) -> dict[str, Any]:
    if not extraction:
        return {"ready": False, "missing_approvals": ["processing_required"]}
    missing: list[str] = []
    for path in sorted(CRITICAL_PATHS):
        field = get_field(extraction, path)
        if field["status"] in {"missing", "conflict"} or field["value"] in (None, "", []) or not field["approved"]:
            missing.append(path)
    return {"ready": not missing, "missing_approvals": missing}


def build_approved_context(extraction: dict[str, Any]) -> dict[str, Any]:
    eligibility = draft_eligibility(extraction)
    if not eligibility["ready"]:
        raise ReportEligibilityError(eligibility["missing_approvals"])

    fields: dict[str, str | list[str]] = {}
    for paths in SECTION_SOURCE_PATHS.values():
        for path in paths:
            field = get_field(extraction, path)
            fields[path] = field["value"]
    return {"schema_version": REPORT_DRAFT_SCHEMA_VERSION, "fields": fields}


def render_saved_draft(
    *,
    case_id: str,
    extraction: dict[str, Any],
    approved_context: dict[str, Any],
    model_metadata: dict[str, str],
) -> dict[str, Any]:
    """Model planı doğrulandıktan sonra, olgusal metni sabit cümlelerle üretir."""
    fields = approved_context["fields"]
    name = _field_text(fields, "patient.full_name")
    questions = _field_list(fields, "request.requested_questions")
    sections = [
        {
            "id": "introduction",
            "title": "Giriş",
            "text": (
                f"{name} hakkında, {_field_text(fields, 'request.sender_authority')} tarafından "
                f"{_field_text(fields, 'request.letter_date')} tarihli ve "
                f"{_field_text(fields, 'request.letter_number')} sayılı yazı ile bildirilen "
                f"{_field_text(fields, 'request.incident')} kapsamında, "
                f"{'; '.join(questions)} hususunda değerlendirme talep edilmiştir."
            ),
            "source_field_paths": list(SECTION_SOURCE_PATHS["introduction"]),
        },
        {
            "id": "general_forensic_exam",
            "title": "Genel adli muayene kaydı",
            "text": (
                f"{_field_text(fields, 'medical.issuing_institution')} tarafından düzenlenen "
                f"{_field_text(fields, 'medical.report_date')} tarihli ve "
                f"{_field_text(fields, 'medical.report_number')} sayılı genel adli muayene raporunda; "
                f"{_field_text(fields, 'medical.incident_date_time')} tarihli başvuruya ilişkin "
                f"{_field_text(fields, 'medical.incident_type')} bilgisi ile "
                f"{_field_text(fields, 'medical.clinical_findings')} kaydı yer almaktadır."
            ),
            "source_field_paths": list(SECTION_SOURCE_PATHS["general_forensic_exam"]),
        },
        {
            "id": "conclusion",
            "title": "Kullanıcı onaylı sonuç kaydı",
            "text": _conclusion_text(
                _field_text(fields, "medical.life_threat"),
                _field_text(fields, "medical.simple_medical_intervention"),
            ),
            "source_field_paths": list(SECTION_SOURCE_PATHS["conclusion"]),
        },
    ]
    draft = {
        "schema_version": REPORT_DRAFT_SCHEMA_VERSION,
        "draft_id": uuid.uuid4().hex,
        "case_id": case_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "review_required",
        "generation": {**model_metadata, "local_only": True},
        "source_extraction_version": extraction["schema_version"],
        "sections": sections,
        "blockers": [],
    }
    _reject_unresolved_placeholders(draft)
    try:
        validate_report_draft(draft)
    except ReportDraftSchemaError as error:
        raise ReportError("Kaydedilecek rapor taslağı kanonik sözleşmeyi karşılamıyor.") from error
    return draft


def _field_text(fields: dict[str, Any], path: str) -> str:
    value = fields[path]
    if not isinstance(value, str) or not value.strip():
        raise ReportError("Onaylı rapor bağlamında metin alanı boş bırakılamaz.")
    return value.strip()


def _field_list(fields: dict[str, Any], path: str) -> list[str]:
    value = fields[path]
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ReportError("Onaylı rapor bağlamında istenen hususlar boş bırakılamaz.")
    return [item.strip() for item in value]


def _conclusion_text(life_threat: str, simple_intervention: str) -> str:
    life_map = {"yes": "TEHLİKEYE SOKTUĞU", "no": "TEHLİKEYE SOKMADIĞI"}
    btm_map = {"yes": "OLDUĞU", "no": "OLMADIĞI"}
    if life_threat not in life_map or simple_intervention not in btm_map:
        raise ReportError("Hayati tehlike ve BTM için yalnızca kullanıcı onaylı evet/hayır değeriyle taslak üretilebilir.")
    return (
        "Kaynakta yer alan ve kullanıcı tarafından onaylanan değerlendirmeye göre; şahsın yaşamını "
        f"{life_map[life_threat]}, basit tıbbi müdahale ile giderilebilecek derecede hafif nitelikte "
        f"{btm_map[simple_intervention]} kanaatlerimizi bildirir taslaktır."
    )


def _load_prompt() -> str:
    path = Path(__file__).resolve().parents[2] / "prompts" / "draft-report-system.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise LocalLLMUnavailable("Yerel rapor planı sistem istemi okunamadı.") from error


def _plan_request(approved_context: dict[str, Any]) -> str:
    schema = ReportPlan.model_json_schema()
    return (
        "Yalnızca aşağıdaki onaylı alan yollarını kullanarak JSON rapor planı döndür. "
        "Alan değeri dışında olgu üretme, metin paragrafı yazma, Markdown ekleme. "
        "Her bölüm için sağlanan alan yollarının tamamını ve yalnızca onları listele.\n\n"
        f"ONAYLI_BAĞLAM={json.dumps(approved_context, ensure_ascii=False)}\n\n"
        f"JSON_ŞEMA={json.dumps(schema, ensure_ascii=False)}"
    )


def _parse_report_plan(raw_output: str) -> ReportPlan:
    start, end = raw_output.find("{"), raw_output.rfind("}")
    if start < 0 or end <= start:
        raise LocalLLMOutputInvalid("Yerel Qwen yapılandırılmış rapor planı döndürmedi; taslak kaydedilmedi.")
    try:
        return ReportPlan.model_validate_json(raw_output[start : end + 1])
    except (ValidationError, ValueError) as error:
        raise LocalLLMOutputInvalid("Yerel Qwen rapor planı şemasını karşılamadı; taslak kaydedilmedi.") from error


def _validate_plan_against_context(plan: ReportPlan, approved_context: dict[str, Any]) -> None:
    expected_ids = set(SECTION_SOURCE_PATHS)
    received = {section.id for section in plan.sections}
    if received != expected_ids or len(plan.sections) != len(expected_ids):
        raise LocalLLMOutputInvalid("Yerel Qwen rapor planında zorunlu bölümler eksik veya yinelenmiş; taslak kaydedilmedi.")
    context_paths = set(approved_context["fields"])
    for section in plan.sections:
        expected_paths = set(SECTION_SOURCE_PATHS[section.id])
        if not expected_paths <= context_paths:
            raise LocalLLMOutputInvalid("Onaylı alan bağlamı raporun zorunlu kaynaklarını içermiyor; taslak kaydedilmedi.")
        # Modelin kaynak alanı seçmesi veya serbest metinden alan yolu üretmesi
        # kabul edilmez. Bölüm yapısı Qwen tarafından üretilir, fakat her bölümün
        # kaynak kümesi kanonik sözleşmeden sunucu tarafından bağlanır.
        section.source_field_paths = sorted(expected_paths)


def _reject_unresolved_placeholders(draft: dict[str, Any]) -> None:
    for section in draft["sections"]:
        text = section["text"]
        if re.search(r"\{\{|\}\}|\b(?:None|null)\b|…{2,}|\.\.\.", text, re.IGNORECASE):
            raise ReportError("Taslakta çözülmemiş yer tutucu bulundu; taslak kaydedilmedi.")


def _qwen_runtime_status() -> tuple[bool, str | None]:
    try:
        import bitsandbytes  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False, "Yerel Qwen çalışma zamanı paketi eksik. Docker imajını yeniden oluşturun."
    except Exception:
        # Triton/bitsandbytes ilk içe aktarmada CUDA çekirdeği derleyebilir. Bu
        # denetim yolu 500 dönmemeli; üretim isteği de açık bir yerel hata verir.
        return False, "Yerel GPU nicemleme çalışma zamanı başlatılamadı; Docker GPU araçlarını kontrol edin."
    return True, None


def _model_revision(model_dir: Path) -> str:
    index = model_dir / "model.safetensors.index.json"
    try:
        digest = hashlib.sha256(index.read_bytes()).hexdigest()
    except OSError:
        return "yerel-model"
    return f"sha256:{digest[:16]}"
