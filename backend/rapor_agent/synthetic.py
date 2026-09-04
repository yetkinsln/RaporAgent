"""Acilikla sahte olarak etiketlenmis, gercek kisi icermeyen demo belgeleri."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any


SYNTHETIC_TCKN = "10000000146"


def _lines(items: list[str]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for index, text in enumerate(items):
        y = 150 + (index * 64)
        lines.append(
            {
                "text": text,
                "confidence": 0.99,
                "polygon": [[82, y - 38], [918, y - 38], [918, y + 10], [82, y + 10]],
                "reading_order": index,
                "page": 1,
            }
        )
    return lines


def demo_documents() -> list[dict[str, Any]]:
    """Dogrulama ekraninin tum alanlarini gosteren iki sentetik belge."""
    return [
        {
            "file_name": "SENTETIK_ust_yazi.png",
            "type": "cover_letter",
            "lines": _lines(
                [
                    "SENTETİK İLÇE EMNİYET MÜDÜRLÜĞÜ",
                    "Sayı: 2026/DEMO-001",
                    "Tarih: 14.08.2026",
                    "Konu: Sentetik vaka hakkında adli rapor talebi",
                    "Adı Soyadı: DENİZ ÖRNEK",
                    f"TCKN: {SYNTHETIC_TCKN}",
                    "Doğum Yeri: SENTETİK İL",
                    "Doğum Tarihi: 02.05.1991",
                    "Olay: Sentetik iş kazası bildirimi",
                    "İstenen Hususlar: Yaralanmanın basit tıbbi müdahale ile giderilebilirliği ve hayati tehlike durumu.",
                ]
            ),
        },
        {
            "file_name": "SENTETIK_genel_adli_muayene.png",
            "type": "general_forensic_exam",
            "lines": _lines(
                [
                    "GENEL ADLİ MUAYENE RAPORU — SENTETİK ÖRNEK",
                    "Kurum: SENTETİK EĞİTİM VE ARAŞTIRMA HASTANESİ",
                    "Rapor Tarihi: 15.08.2026",
                    "Rapor Sayısı: GARM-2026-0001",
                    "Protokol No: PR-2026-0001",
                    "Başvuru/Olay Tarihi: 14.08.2026 16:30",
                    "Başvuru Nedeni: Sentetik iş kazası",
                    "Adı Soyadı: DENİZ ÖRNEK",
                    f"TCKN: {SYNTHETIC_TCKN}",
                    "Doğum Yeri ve Tarihi: SENTETİK İL / 02.05.1991",
                    "Klinik Bulgular: Sol ön kolda 2 cm yüzeysel abrazyon gözlendi.",
                    "Hayati Tehlike: Yoktur.",
                    "BTM: Basit tıbbi müdahale ile giderilebilir niteliktedir.",
                ]
            ),
        },
    ]


def render_page_png(lines: list[dict[str, Any]], title: str) -> bytes:
    """Sentetik fixture'ı gerçek yüklemeyle aynı raster yoldan sunar."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as error:
        raise RuntimeError("Sentetik sayfa için yerel Pillow bileşeni gerekli.") from error

    image = Image.new("RGB", (1000, 900), "#fffdf7")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((20, 20, 980, 880), radius=4, outline="#b7aa90", width=2)
    regular = _font(ImageFont, 20)
    heading = _font(ImageFont, 25, bold=True)
    watermark = _font(ImageFont, 14, bold=True)
    draw.text((82, 68), "YALNIZCA SENTETİK TEST BELGESİ — GERÇEK KİŞİSEL VERİ İÇERMEZ", font=watermark, fill="#6b5c42")
    draw.text((82, 106), title, font=heading, fill="#202020")
    for line in lines:
        y = int(line["polygon"][3][1] - 10)
        draw.text((82, y), line["text"], font=regular, fill="#202020")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _font(image_font: Any, size: int, *, bold: bool = False) -> Any:
    """Windows gelistirme ve Linux Docker imajinda ayni sentetik sayfayi cizer."""
    candidates = (
        ["C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold
        else ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return image_font.truetype(candidate, size)
    return image_font.load_default(size=size)
