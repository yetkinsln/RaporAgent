# Teknik karar notları ve resmi kaynaklar

- PaddleOCR 3.6 çok dilli belgelerinde Türkçe `tr` olarak listelenir ve Latin PP-OCRv5 tanıma modelinin desteklediği diller arasındadır: https://www.paddleocr.ai/v3.6.0/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html
- PaddleOCR genel OCR hattı; belge yönü, unwarping, satır yönü, tespit ve tanıma bileşenlerini ayrı seçenekler olarak sunar: https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html
- Ollama yapılandırılmış çıktıda JSON Schema kabul eder. Yine de model cevabı sunucuda Pydantic ile doğrulanmalıdır: https://docs.ollama.com/capabilities/structured-outputs
- Ollama'nın OpenAI uyumlu yerel API'si sağlayıcı adaptörü yazmayı kolaylaştırabilir: https://docs.ollama.com/api/openai-compatibility
- `docxtpl`, Word'de hazırlanmış `.docx` şablonlarına Jinja benzeri alanlar yerleştirerek biçimi koruyan belge üretimini amaçlar: https://github.com/elapouya/python-docx-template
- `python-docx` metin, tablo, bölüm, stil, üstbilgi ve altbilgi işlemleri için kullanılabilir: https://python-docx.readthedocs.io/

Bağımlılıklar uygulama başlamadan sabit sürümlere kilitlenmeli; “latest” sürüm üretim ortamında kendiliğinden çekilmemelidir.
