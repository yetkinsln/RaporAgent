"""Vaka dosyalarini tahmin edilemeyen kimliklerle yalnizca yerelde saklar."""

from __future__ import annotations

import json
import os
import shutil
import unicodedata
import uuid
from pathlib import Path
from typing import Any


class StorageError(RuntimeError):
    pass


ALLOWED_TYPES: dict[bytes, tuple[str, str]] = {
    b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
    b"\xff\xd8\xff": ("jpg", "image/jpeg"),
    b"%PDF-": ("pdf", "application/pdf"),
}


class CaseStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create_case(self) -> dict[str, Any]:
        case_id = uuid.uuid4().hex
        case_dir = self.case_dir(case_id)
        for folder in ("originals", "pages", "derived", "reports"):
            (case_dir / folder).mkdir(parents=True, exist_ok=False)
        case = {
            "case_id": case_id,
            "documents": [],
            "extraction": None,
            "report_drafts": [],
            "docx_input": None,
            "docx_reports": [],
            "audit": [],
            "stage": "documents",
        }
        self.save_case(case)
        return case

    def case_dir(self, case_id: str) -> Path:
        if not case_id or any(character not in "0123456789abcdef" for character in case_id) or len(case_id) != 32:
            raise StorageError("Geçersiz vaka kimliği.")
        return self.root / "cases" / case_id

    def load_case(self, case_id: str) -> dict[str, Any]:
        record_path = self.case_dir(case_id) / "case.json"
        try:
            return json.loads(record_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise StorageError("Vaka bulunamadı.") from error
        except json.JSONDecodeError as error:
            raise StorageError("Vaka kaydı okunamadı; işlem güvenle sürdürülemedi.") from error

    def save_case(self, case: dict[str, Any]) -> None:
        destination = self.case_dir(case["case_id"]) / "case.json"
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, destination)

    def store_upload(self, case_id: str, file_name: str, content: bytes) -> dict[str, str]:
        extension, mime_type = inspect_upload(content)
        document_id = uuid.uuid4().hex
        # Kullanici dosya adi disk yoluna hic katilmaz.
        destination = self.case_dir(case_id) / "originals" / f"{document_id}.{extension}"
        destination.write_bytes(content)
        return {
            "document_id": document_id,
            "file_name": sanitized_display_name(file_name, extension),
            "file_path": str(destination.relative_to(self.case_dir(case_id))),
            "mime_type": mime_type,
        }

    def store_demo_page(self, case_id: str, document_id: str, payload: bytes) -> Path:
        destination = self.case_dir(case_id) / "pages" / f"{document_id}-001.png"
        destination.write_bytes(payload)
        return destination

    def create_image_page(self, case_id: str, document_id: str, original_relative_path: str, extension: str) -> list[dict[str, Any]]:
        source = self.case_dir(case_id) / original_relative_path
        destination = self.case_dir(case_id) / "pages" / f"{document_id}-001.{extension}"
        shutil.copyfile(source, destination)
        width, height = image_dimensions(destination)
        return [self.page_record(document_id, 1, destination, width, height)]

    def render_pdf_pages(self, case_id: str, document_id: str, original_relative_path: str) -> list[dict[str, Any]]:
        try:
            import fitz
        except ImportError as error:
            raise StorageError("Yerel PDF sayfalaştırma bileşeni kurulu değil.") from error

        source = self.case_dir(case_id) / original_relative_path
        try:
            pdf = fitz.open(source)
        except Exception as error:
            raise StorageError("PDF güvenli biçimde açılamadı.") from error
        pages: list[dict[str, Any]] = []
        try:
            if pdf.page_count == 0:
                raise StorageError("PDF sayfa içermiyor.")
            if pdf.page_count > 25:
                raise StorageError("PDF 25 sayfalık ilk iterasyon sınırını aşıyor.")
            for index, page in enumerate(pdf, start=1):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                destination = self.case_dir(case_id) / "pages" / f"{document_id}-{index:03d}.png"
                pixmap.save(destination)
                pages.append(self.page_record(document_id, index, destination, pixmap.width, pixmap.height))
        finally:
            pdf.close()
        return pages

    def page_record(self, document_id: str, page_number: int, path: Path, width: int | None, height: int | None) -> dict[str, Any]:
        return {
            "page": page_number,
            "path": str(path),
            "original_path": str(path),
            "original_width": width,
            "original_height": height,
            "width": width,
            "height": height,
            "transform": {"revision": 0, "operations": []},
            "image_endpoint": f"/api/documents/{document_id}/pages/{page_number}/image",
        }

    def page_path(self, case_id: str, document: dict[str, Any], page_number: int) -> Path:
        pages = document.get("pages", [])
        selected = next((page for page in pages if page["page"] == page_number), None)
        if selected is None:
            raise StorageError("Belge sayfası bulunamadı.")
        path = Path(selected["path"])
        resolved_root = self.case_dir(case_id).resolve()
        if resolved_root not in path.resolve().parents:
            raise StorageError("Belge sayfa yolu güvenli değil.")
        return path

    def delete_document_files(self, case_id: str, document_id: str) -> None:
        """Belgeye ait özgün, sayfa ve türetilmiş dosyaları vaka sınırında siler."""
        case_dir = self.case_dir(case_id).resolve()
        prefixes = (f"{document_id}.", f"{document_id}-")
        targets: list[Path] = []
        for folder in ("originals", "pages", "derived"):
            directory = case_dir / folder
            for candidate in directory.iterdir():
                if candidate.is_file() and candidate.name.startswith(prefixes):
                    resolved = candidate.resolve()
                    if case_dir not in resolved.parents:
                        raise StorageError("Belge dosya yolu güvenli değil; silme durduruldu.")
                    targets.append(resolved)

        try:
            for target in targets:
                target.unlink()
        except OSError as error:
            raise StorageError("Belgenin yerel dosyaları silinemedi; vaka kaydı değiştirilmedi.") from error

    def save_report_draft(self, case_id: str, draft: dict[str, Any]) -> dict[str, str]:
        """Taslağı kullanıcı adından bağımsız, vaka içindeki sabit kimlikle kaydeder."""
        draft_id = str(draft.get("draft_id", ""))
        if len(draft_id) != 32 or any(character not in "0123456789abcdef" for character in draft_id):
            raise StorageError("Rapor taslak kimliği güvenli değil.")
        if draft.get("case_id") != case_id:
            raise StorageError("Rapor taslağı farklı bir vakaya kaydedilemez.")

        reports = self.case_dir(case_id) / "reports"
        json_path = reports / f"draft-{draft_id}.json"
        text_path = reports / f"draft-{draft_id}.txt"
        if json_path.exists() or text_path.exists():
            raise StorageError("Rapor taslak kimliği zaten kullanılıyor; dosya ezilmedi.")
        text = "\n\n".join(section["text"] for section in draft.get("sections", []))
        self._write_new_text(json_path, json.dumps(draft, ensure_ascii=False, indent=2))
        try:
            self._write_new_text(text_path, text)
        except OSError as error:
            json_path.unlink(missing_ok=True)
            raise StorageError("Rapor taslağının metin kopyası kaydedilemedi; taslak geri alındı.") from error
        return {"draft_id": draft_id, "json_file": json_path.name, "text_file": text_path.name}

    def load_report_draft(self, case_id: str, draft_id: str) -> dict[str, Any]:
        if len(draft_id) != 32 or any(character not in "0123456789abcdef" for character in draft_id):
            raise StorageError("Rapor taslak kimliği güvenli değil.")
        path = self.case_dir(case_id) / "reports" / f"draft-{draft_id}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise StorageError("Rapor taslağı bulunamadı.") from error
        except json.JSONDecodeError as error:
            raise StorageError("Rapor taslağı okunamadı; işlem güvenle sürdürülemedi.") from error

    def save_docx_report(self, case_id: str, patient_name: str, rendered_path: Path) -> dict[str, str]:
        """Yeni DOCX'i güvenli dosya adıyla kaydeder; var olan raporu asla ezmez."""
        reports = self.case_dir(case_id) / "reports"
        stem = _report_name_stem(patient_name)
        for sequence in range(1, 10_000):
            file_name = f"{stem}-rapor{sequence:02d}.docx"
            destination = reports / file_name
            try:
                with rendered_path.open("rb") as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target)
            except FileExistsError:
                continue
            except OSError as error:
                raise StorageError("Word taslağı yerel depoya kaydedilemedi; mevcut dosya ezilmedi.") from error
            return {"file_name": file_name, "relative_path": str(destination.relative_to(self.case_dir(case_id)))}
        raise StorageError("Rapor dosya sıra numarası sınırına ulaştı; Word taslağı kaydedilmedi.")

    def docx_report_path(self, case_id: str, relative_path: str) -> Path:
        candidate = (self.case_dir(case_id) / relative_path).resolve()
        reports = (self.case_dir(case_id) / "reports").resolve()
        if reports not in candidate.parents or candidate.suffix.lower() != ".docx":
            raise StorageError("Word rapor dosya yolu güvenli değil.")
        if not candidate.is_file():
            raise StorageError("Word rapor dosyası bulunamadı.")
        return candidate

    @staticmethod
    def _write_new_text(destination: Path, content: str) -> None:
        """Yeni dosyayı yalnızca benzersiz hedefe yazar; mevcut dosyayı ezmez."""
        try:
            # ``x`` işletim sistemi seviyesinde yalnızca yeni dosya açar; önceden
            # yapılan ``exists`` kontrolündeki yarış koşuluyla bir taslağın üzerine
            # yazılmasını önler.
            with destination.open("x", encoding="utf-8") as file:
                file.write(content)
        except FileExistsError as error:
            raise StorageError("Rapor taslak dosyası zaten var; dosya ezilmedi.") from error
        except OSError:
            raise

    def transform_page(
        self,
        case_id: str,
        document_id: str,
        page: dict[str, Any],
        operation: str,
        crop: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Yeni bir türetilmiş görüntü üretir; özgün sayfayı asla değiştirmez."""
        transform = page.setdefault("transform", {"revision": 0, "operations": []})
        if operation == "reset":
            original_path = Path(page.get("original_path") or page["path"])
            page["path"] = str(original_path)
            page["width"] = page.get("original_width")
            page["height"] = page.get("original_height")
            transform["revision"] = int(transform.get("revision", 0)) + 1
            transform["operations"] = []
            return page

        source = self.page_path(case_id, {"pages": [page]}, page["page"])
        image = _load_page_image(source)
        input_width, input_height = image.size
        operation_record: dict[str, Any]
        if operation == "rotate_clockwise":
            image = image.rotate(-90, expand=True)
            operation_record = {"operation": "rotate", "degrees": 90}
        elif operation == "rotate_counterclockwise":
            image = image.rotate(90, expand=True)
            operation_record = {"operation": "rotate", "degrees": -90}
        elif operation == "crop":
            if crop is None:
                raise StorageError("Kırpma alanı belirtilmedi.")
            bounds = _normalised_crop_bounds(crop, input_width, input_height)
            image = image.crop(bounds)
            operation_record = {
                "operation": "crop",
                "left": bounds[0],
                "top": bounds[1],
                "right": bounds[2],
                "bottom": bounds[3],
            }
        else:
            raise StorageError("Bilinmeyen sayfa dönüşümü.")

        destination = self.case_dir(case_id) / "derived" / f"{document_id}-{page['page']:03d}-{uuid.uuid4().hex}.png"
        image.save(destination, format="PNG")
        output_width, output_height = image.size
        operation_record.update(
            {
                "input_width": input_width,
                "input_height": input_height,
                "output_width": output_width,
                "output_height": output_height,
            }
        )
        page["path"] = str(destination)
        page["width"] = output_width
        page["height"] = output_height
        transform["revision"] = int(transform.get("revision", 0)) + 1
        transform.setdefault("operations", []).append(operation_record)
        return page


def _report_name_stem(patient_name: str) -> str:
    normalised = unicodedata.normalize("NFKD", patient_name).encode("ascii", "ignore").decode("ascii")
    cleaned = "_".join(part for part in normalised.upper().split() if part.isalnum())
    return cleaned or "RAPOR"


def inspect_upload(content: bytes) -> tuple[str, str]:
    if not content:
        raise StorageError("Boş dosya yüklenemez.")
    if len(content) > 20 * 1024 * 1024:
        raise StorageError("Dosya 20 MB ilk iterasyon sınırını aşıyor.")
    for signature, details in ALLOWED_TYPES.items():
        if content.startswith(signature):
            return details
    raise StorageError("Yalnızca imzası doğrulanmış PNG, JPEG veya PDF dosyası yüklenebilir.")


def sanitized_display_name(file_name: str, extension: str) -> str:
    plain = Path(file_name or "belge").name
    stem = "".join(character for character in Path(plain).stem if character.isalnum() or character in "-_ ").strip()
    return f"{stem[:80] or 'belge'}.{extension}"


def image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except ImportError as error:
        raise StorageError("Yerel görüntü bileşeni kurulu değil.") from error
    except Exception as error:
        raise StorageError("Yüklenen görüntü okunamadı.") from error


def _load_page_image(path: Path):
    try:
        from PIL import Image
    except ImportError as error:
        raise StorageError("Yerel görüntü bileşeni kurulu değil.") from error

    try:
        with Image.open(path) as source:
            return source.convert("RGB")
    except Exception:
        # Demo SVG gibi raster olmayan sayfalar yalnızca yerel PyMuPDF ile rasterize edilir.
        try:
            import fitz

            document = fitz.open(path)
            try:
                if document.page_count != 1:
                    raise StorageError("Dönüştürülecek sayfa tekil görüntü olmalı.")
                pixmap = document[0].get_pixmap(alpha=False)
                return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            finally:
                document.close()
        except StorageError:
            raise
        except Exception as error:
            raise StorageError("Sayfa döndürme/kırpma için yerel görüntüye dönüştürülemedi.") from error


def _normalised_crop_bounds(crop: dict[str, float], width: int, height: int) -> tuple[int, int, int, int]:
    left = round(crop["left"] * width)
    top = round(crop["top"] * height)
    right = round(crop["right"] * width)
    bottom = round(crop["bottom"] * height)
    if left < 0 or top < 0 or right > width or bottom > height or right - left < 20 or bottom - top < 20:
        raise StorageError("Kırpma alanı sayfa sınırları içinde ve en az 20 piksel olmalı.")
    return left, top, right, bottom
