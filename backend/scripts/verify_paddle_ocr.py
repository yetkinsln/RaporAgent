"""Gercek PaddleOCR motorunun sentetik Turkce sayfada poligon uretebildigini denetler."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from rapor_agent.ocr import PaddleOcrConfig, PaddleOcrProvider
from rapor_agent.service import CaseService
from rapor_agent.synthetic import demo_documents, render_page_png


def main() -> None:
    fixtures = demo_documents()
    fixture = fixtures[0]
    with tempfile.TemporaryDirectory(prefix="rapor-agent-ocr-") as directory:
        page_path = Path(directory) / "synthetic-cover-letter.png"
        page_bytes = render_page_png(fixture["lines"], fixture["file_name"])
        page_path.write_bytes(page_bytes)
        provider = _provider()
        lines = provider.read(page_path, page_number=1)

        # Gerçek upload -> sayfalaştırma -> OCR -> alan çıkarımı yolunu da
        # aynı motor ve yalnızca sentetik içerikle çalıştırır.
        service = CaseService(Path(directory) / "cases", ocr_provider=provider)
        case = service.create_case()
        service.upload_document(case["case_id"], "synthetic-upload.png", page_bytes)
        processed = service.process(case["case_id"])
        processed_document = processed["documents"][0]

    if not lines or not all(len(line.polygon) == 4 for line in lines):
        raise RuntimeError("PaddleOCR sentetik sayfada kanit poligonlari uretemedi.")
    # Tanimlayici metin sadece bellek icinde kontrol edilir; hata ciktilarina belge metni yazilmaz.
    if not any("TCKN" in line.text.upper() for line in lines):
        raise RuntimeError("PaddleOCR sentetik Turkce etiketini tanimadi.")
    uploaded_lines = processed_document["ocr_lines"]
    if processed_document["ocr_status"] != "completed" or not uploaded_lines:
        raise RuntimeError("Gercek yukleme yolu PaddleOCR ile tamamlanamadi.")
    if not all(len(line["polygon"]) == 4 for line in uploaded_lines):
        raise RuntimeError("Gercek yukleme yolunda kaynak poligonlari korunamadi.")
    print(
        "PADDLE_OCR_INTEGRATION_OK "
        f"direct_lines={len(lines)} uploaded_lines={len(uploaded_lines)} polygons={len(uploaded_lines)}"
    )


def _provider() -> PaddleOcrProvider:
    return PaddleOcrProvider(
        PaddleOcrConfig(
            text_detection_model_dir=Path(
                os.environ.get(
                    "RAPOR_AGENT_PADDLE_DET_MODEL_DIR",
                    "/opt/paddle-models/official_models/PP-OCRv5_server_det",
                )
            ),
            text_recognition_model_dir=Path(
                os.environ.get(
                    "RAPOR_AGENT_PADDLE_REC_MODEL_DIR",
                    "/opt/paddle-models/official_models/latin_PP-OCRv5_mobile_rec",
                )
            ),
        )
    )


if __name__ == "__main__":
    main()
