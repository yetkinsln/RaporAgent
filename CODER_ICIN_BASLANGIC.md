# Coder için başlangıç

İlk olarak şu dosyaları sırayla oku:

1. `AGENTS.md`
2. `ADLI_RAPOR_PROJE_TALIMATI.md`
3. `.codex/skills/adli-rapor-gelistirme/SKILL.md`
4. `docs/architecture.md`
5. `schemas/case-extraction.schema.json`

İlk geliştirme hedefi bütün projeyi tek seferde kurmak değil; sentetik bir üst yazı ve genel adli muayene belgesiyle şu uçtan uca dilimi çalıştırmaktır:

`yükleme → sayfa görüntüsü → OCR poligonları → kaynaklı alan çıkarımı → kullanıcı onayı`

Bu dilim test edilmeden LLM ile rapor yazımı veya Word üretimine geçme. İlk iterasyonda gerçek hasta verisi kullanma.

Kurumsal Word şablonu, kimliksiz örnek belgeler ve SAYI numaralandırma kuralı henüz sağlanmadıysa bunları açık blocker olarak kaydet; buna rağmen sentetik fixture, veri modeli, OCR adaptörü ve doğrulama arayüzü geliştirilebilir.
