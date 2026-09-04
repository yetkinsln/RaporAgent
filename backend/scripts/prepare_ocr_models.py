"""PaddleOCR Turkce modellerini sadece imaj olusturulurken yerel cache'e alir."""

from __future__ import annotations

import os
from pathlib import Path


MODEL_ROOT = Path(os.environ.get("PADDLE_PDX_CACHE_HOME", "/opt/paddle-models"))
MODEL_SOURCES = {
    "PP-OCRv5_server_det": "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv5_server_det_infer.tar",
    "latin_PP-OCRv5_mobile_rec": "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/latin_PP-OCRv5_mobile_rec_infer.tar",
}


def main() -> None:
    # Derleme agi, imaj katmanina model almak icin bilincli olarak kullanilir.
    # Uygulama calisma aninda sadece asagidaki dosya yollarini kullanir.
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")
    os.environ.pop("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", None)

    # PaddleX 3.1.2'nin resmi model kaynağındaki sabit inference arşivlerini
    # ilerleme çubuğu olmadan indirmek CI/Docker loglarını ve çalışma anını ayırır.
    from paddlex.utils.download import download_and_extract

    model_dir = MODEL_ROOT / "official_models"
    for name, url in MODEL_SOURCES.items():
        download_and_extract(url, str(model_dir), name, print_progress=False)

    missing = [name for name in MODEL_SOURCES if not (model_dir / name).is_dir()]
    if missing:
        raise RuntimeError("PaddleOCR modelleri indirilemedi veya dogrulanamadi.")
    print(f"PADDLE_OCR_MODELS_READY count={len(MODEL_SOURCES)}")


if __name__ == "__main__":
    main()
