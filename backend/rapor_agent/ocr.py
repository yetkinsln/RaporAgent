"""PaddleOCR 3.x ciktilarini kanonik OCRLine sozlesmesine uyarlar."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Protocol


class OcrProviderUnavailable(RuntimeError):
    pass


class OcrProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class OCRLine:
    text: str
    confidence: float
    polygon: list[list[float]]
    reading_order: int
    page: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "polygon": self.polygon,
            "reading_order": self.reading_order,
            "page": self.page,
        }


class OCRProvider(Protocol):
    def read(self, page_path: Path, page_number: int) -> list[OCRLine]: ...


@dataclass(frozen=True)
class PaddleOcrConfig:
    language: str = "tr"
    text_detection_model_name: str = "PP-OCRv5_server_det"
    text_recognition_model_name: str = "latin_PP-OCRv5_mobile_rec"
    text_detection_model_dir: Path | None = None
    text_recognition_model_dir: Path | None = None
    use_document_orientation: bool = False
    use_document_unwarping: bool = False
    use_textline_orientation: bool = False


class PaddleOcrProvider:
    """PaddleOCR API farklarini bu sinifta sinirli tutar.

    Paket ilk kez buradan cagrildiginda yuklenir. Uygulama hicbir bulut OCR
    servisine baglanmaz; yerel model kurulu degilse eyleme donuk hata verir.
    """

    def __init__(self, config: PaddleOcrConfig | None = None) -> None:
        self.config = config or PaddleOcrConfig(
            text_detection_model_dir=_model_dir_from_environment("RAPOR_AGENT_PADDLE_DET_MODEL_DIR"),
            text_recognition_model_dir=_model_dir_from_environment("RAPOR_AGENT_PADDLE_REC_MODEL_DIR"),
        )
        self._engine: Any | None = None

    def _get_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        try:
            from paddleocr import PaddleOCR
        except ImportError as error:
            raise OcrProviderUnavailable(
                "Yerel PaddleOCR paketi veya modeli kullanıma hazır değil. "
                "Uygulama ayarlarından yerel OCR kurulumunu tamamlayın."
            ) from error

        if not self.config.text_detection_model_dir or not self.config.text_recognition_model_dir:
            raise OcrProviderUnavailable(
                "Yerel PaddleOCR model klasörleri yapılandırılmadı. "
                "RAPOR_AGENT_PADDLE_DET_MODEL_DIR ve RAPOR_AGENT_PADDLE_REC_MODEL_DIR değerlerini yalnızca yerel modellere ayarlayın."
            )
        if not self.config.text_detection_model_dir.is_dir() or not self.config.text_recognition_model_dir.is_dir():
            raise OcrProviderUnavailable("Yapılandırılan yerel PaddleOCR model klasörü bulunamadı.")

        # Paddle'ın çalışma anında uzaktan model kaynağı aramasını engeller. Model
        # sağlanmamışsa açık hata verilir; hasta belgesiyle ağ erişimi denenmez.
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        try:
            self._engine = PaddleOCR(
                text_detection_model_name=self.config.text_detection_model_name,
                text_detection_model_dir=str(self.config.text_detection_model_dir),
                text_recognition_model_name=self.config.text_recognition_model_name,
                text_recognition_model_dir=str(self.config.text_recognition_model_dir),
                use_doc_orientation_classify=self.config.use_document_orientation,
                use_doc_unwarping=self.config.use_document_unwarping,
                use_textline_orientation=self.config.use_textline_orientation,
            )
        except Exception as error:  # Paddle hatasi hasta icerigi olmadan ele alinir.
            raise OcrProviderUnavailable(
                "Yerel PaddleOCR başlatılamadı. Model ve çalışma zamanı kurulumunu kontrol edin."
            ) from error
        return self._engine

    def read(self, page_path: Path, page_number: int) -> list[OCRLine]:
        engine = self._get_engine()
        try:
            if hasattr(engine, "predict"):
                prediction = engine.predict(str(page_path))
                return self._adapt_predict_output(prediction, page_number)
            return self._adapt_legacy_output(engine.ocr(str(page_path), cls=True), page_number)
        except OcrProviderUnavailable:
            raise
        except Exception as error:
            raise OcrProviderError("Yerel OCR sayfayı okuyamadı; görüntüyü ve OCR kurulumunu kontrol edin.") from error

    def _adapt_predict_output(self, prediction: Any, page_number: int) -> list[OCRLine]:
        rows: list[OCRLine] = []
        for result in prediction:
            payload = self._result_to_dict(result)
            texts = payload.get("rec_texts") or payload.get("texts") or []
            scores = payload.get("rec_scores") or payload.get("scores") or []
            polygons = payload.get("rec_polys") or payload.get("dt_polys") or payload.get("polygons") or []
            for index, text in enumerate(texts):
                if index >= len(polygons):
                    continue
                rows.append(
                    OCRLine(
                        text=str(text),
                        confidence=float(scores[index]) if index < len(scores) else 0.0,
                        polygon=_canonical_polygon(polygons[index]),
                        reading_order=len(rows),
                        page=page_number,
                    )
                )
        return rows

    @staticmethod
    def _result_to_dict(result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            return _prediction_payload(result)
        if hasattr(result, "json"):
            json_value = result.json
            json_value = json_value() if callable(json_value) else json_value
            if isinstance(json_value, dict):
                return _prediction_payload(json_value)
            if isinstance(json_value, str):
                try:
                    decoded = json.loads(json_value)
                except json.JSONDecodeError:
                    decoded = None
                if isinstance(decoded, dict):
                    return _prediction_payload(decoded)
        if hasattr(result, "to_dict"):
            value = result.to_dict()
            if isinstance(value, dict):
                return _prediction_payload(value)
        return {}

    @staticmethod
    def _adapt_legacy_output(prediction: Any, page_number: int) -> list[OCRLine]:
        rows: list[OCRLine] = []
        for page in prediction or []:
            for item in page or []:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                text_and_score = item[1]
                if not isinstance(text_and_score, (list, tuple)) or len(text_and_score) < 2:
                    continue
                rows.append(
                    OCRLine(
                        text=str(text_and_score[0]),
                        confidence=float(text_and_score[1]),
                        polygon=_canonical_polygon(item[0]),
                        reading_order=len(rows),
                        page=page_number,
                    )
                )
        return rows


def _canonical_polygon(value: Any) -> list[list[float]]:
    """Dort koseli geometriyi korur; eksen hizali kutuya indirgemez."""
    points: list[list[float]] = []
    for point in value:
        if len(point) < 2:
            continue
        points.append([float(point[0]), float(point[1])])
    if len(points) < 4:
        raise OcrProviderError("OCR satır geometrisi geçersiz; kaynak vurgusu güvenle gösterilemez.")
    return points[:4]


def _model_dir_from_environment(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def _prediction_payload(value: dict[str, Any]) -> dict[str, Any]:
    """PaddleOCR 3.x sonucunun surume gore degisen dis zarfindan arindirir."""
    nested = value.get("res")
    return nested if isinstance(nested, dict) else value
