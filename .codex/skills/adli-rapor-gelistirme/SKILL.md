---
name: adli-rapor-gelistirme
description: Yerel OCR ve yerel LLM kullanan adli tıbbi rapor taslak uygulamasını geliştirir veya gözden geçirir. Belge sınıflandırma, kaynak gösteren alan çıkarımı, insan onayı, Word şablonu ve hassas sağlık verisi sınırlarıyla ilgili değişikliklerde kullanılır; genel OCR veya sıradan belge üretimi işlerinde kullanılmaz.
---

# Adli rapor geliştirme

Bu projede doğruluk, izlenebilirlik ve kullanıcı onayı hızdan önce gelir. Uygulama yalnızca taslak üretir; tıbbi kanaat veren ya da imzalı nihai rapor düzenleyen özerk bir sistem gibi davranmaz.

## Çalışma ilkeleri

1. Önce proje kökündeki `ADLI_RAPOR_PROJE_TALIMATI.md` ve `AGENTS.md` dosyalarını oku.
2. Değişiklik alanı OCR, veri çıkarımı, LLM istemi, rapor üretimi veya hassas veri işleme ise [alan kuralları](references/alan-kurallari.md) dosyasını da oku.
3. Rapor metni ya da `.docx` şablonu değişiyorsa [rapor sözleşmesi](references/rapor-sozlesmesi.md) dosyasını da oku.
4. OCR çıktısını gerçek kabul etme. Her alanı kaynak belge, sayfa, kanıt metni ve güven değeriyle taşı.
5. Eksik veya çelişkili veriyi tahmin etme. `missing` ya da `conflict` olarak işaretle ve kullanıcı onayı iste.
6. LLM serbest metinden doğrudan Word dosyası üretmemeli. Önce şemaya uyan yapılandırılmış çıktı üretmeli; sunucu şemayı doğrulamalı; yalnızca onaylı alanlar şablona aktarılmalı.
7. TCKN, yaşamı tehlikeye sokma ve basit tıbbi müdahale değerlendirmesi gibi kritik alanları otomatik onaylama.

## Mimari sınır

- Önerilen MVP: React/Vite istemci, FastAPI/Python uygulama servisi, SQLite, PaddleOCR ve Ollama uyumlu yerel model sunucusu.
- MERN kesin gereksinimse Express yalnızca kimlik doğrulama ve orkestrasyon katmanı olmalı; OCR/LLM/Word işleri Python servisinde kalmalı.
- Bulut OCR, bulut LLM, üçüncü taraf telemetri ve gerçek hasta verisini test fixture'ına yazma yasaktır.
- Belge üretiminde kurumdan alınmış `.docx` şablonunu `docxtpl` ile doldur. Şablon sağlanmadıysa yalnızca açıkça “örnek” olarak işaretlenmiş taslak üret.

## Tamamlanma ölçütü

Bir özellik; doğrulama, sentetik test, hata durumu, kaynak izleme ve kullanıcı arayüzündeki onay akışı birlikte çalışmadan tamamlanmış sayılmaz. Güvenlik veya kurum politikası konusunda doğrulanmamış bir “uyumludur” iddiasında bulunma.
