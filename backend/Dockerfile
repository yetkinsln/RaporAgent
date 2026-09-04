# Python CPU tabanı: yalnızca sabitlenmiş Paddle/PaddleX OCR bağımlılıkları kurulur.
FROM python:3.10-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLE_PDX_CACHE_HOME=/opt/paddle-models \
    RAPOR_AGENT_DATA_DIR=/app/data \
    RAPOR_AGENT_LLM_MODEL_DIR=/models/qwen3-8b \
    RAPOR_AGENT_TEMPLATE_DIR=/templates \
    RAPOR_AGENT_PADDLE_DET_MODEL_DIR=/opt/paddle-models/official_models/PP-OCRv5_server_det \
    RAPOR_AGENT_PADDLE_REC_MODEL_DIR=/opt/paddle-models/official_models/latin_PP-OCRv5_mobile_rec \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-ocr.txt backend/requirements-llm.txt ./
# PaddleOCR tekerlegi genis PaddleX ekstra gruplarini (LLM istemcileri dahil)
# metadata bagimliligi olarak bildirir. Uygulama bunlari kullanmaz; yalnızca
# sabit OCR tabani kurulup PaddleOCR tekerlegi bagimliliksiz eklenir.
RUN python -m pip install --no-cache-dir -r requirements-ocr.txt \
    && python -m pip install --no-cache-dir --no-deps paddleocr==3.1.0 \
    && python -c "import paddle; assert paddle.__version__.startswith('3.0.0')"

# Qwen3-8B çalışma zamanı ayrı ve sabitlenmiş katmandadır. Model ağırlıkları
# imaja kopyalanmaz; çalışma anında yalnızca yerel, salt-okunur bind mount ile
# erişilir. CUDA 12.8 PyTorch tekerleği Blackwell GPU'ları destekler.
# Bazı CUDA/PyTorch tekerlekleri, Docker katmanına uyumsuz ya da bozulmuş
# önceden derlenmiş ``.pyc`` dosyaları bırakabiliyor. Uygulama zaten bytecode
# yazmayı kapatır; bu dosyaları imajda bırakmak bitsandbytes'in torch._dynamo
# içe aktarmasını ``bad marshal data`` ile bozabiliyor. Kaynaktan bellek içi
# yükleme, GPU nicemleme çalışma zamanını deterministik kılar.
RUN python -m pip install --no-cache-dir -r requirements-llm.txt \
    && find /usr/local/lib/python3.10/site-packages/torch -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

# bitsandbytes'in Triton yolu GPU sürücüsüne uygun küçük bir CUDA yardımcı
# çekirdeğini ilk kullanımda derler; bu nedenle çalışma anında C derleyicisi
# de gerekir. Bu katman, büyük Python bağımlılıklarını önbellekte tutar.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/rapor_agent ./rapor_agent
COPY backend/scripts ./scripts
COPY schemas /schemas
COPY Templates/adli-rapor-sablonu-v2.docx /templates/adli-rapor-sablonu-v2.docx
COPY Templates/kurumsal-girdiler_mapping_alan-esleme-v2.json /templates/kurumsal-girdiler_mapping_alan-esleme-v2.json
# Rapor planı sistem istemi sürümlüdür; modele gönderilen bu yerel dosya
# imajda da bulunmalıdır. Model ağırlıkları ise kesinlikle kopyalanmaz.
COPY prompts /prompts

# Model indirme yalnizca docker build asamasinda olur; sonraki calisma aninda ag kullanilmaz.
RUN PADDLE_PDX_MODEL_SOURCE=BOS python scripts/prepare_ocr_models.py \
    && python scripts/verify_paddle_ocr.py

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app /opt/paddle-models

USER appuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "rapor_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
