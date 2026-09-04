# Üçüncü iterasyon: yerel Qwen ile kaynaklı taslak

## Amaç

Kullanıcının tek tek onayladığı kritik alanlardan, tamamen yerelde saklanan bir rapor **taslağı** oluşturmak. Bu iterasyon Word üretimi, imza veya nihai tıbbi karar içermez.

## Akış

```text
Kaynaklı alan çıkarımı
  → kritik alanların kullanıcı onayı
  → Qwen3-8B ile şemalı bölüm planı
  → sunucuda plan doğrulaması
  → yalnızca onaylı değerlerle sabit metin şablonu
  → reports/draft-<id>.json + .txt yerel kaydı
```

- Qwen3-8B model klasörü Docker imajına kopyalanmaz; `qwen3-8b/` salt-okunur bağlanır ve çalışma anında dış ağ kapalıdır.
- Model, modelin kaynakta olmayan olgu eklemesini önlemek için serbest paragraf değil, üç bölümün (`introduction`, `general_forensic_exam`, `conclusion`) JSON planını üretir.
- Sunucu, Pydantic ile planın tam bölüm kümesini ve `schemas/report-draft.schema.json` ile kaydedilecek taslağı tekrar doğrular. Her bölümün kaynak alanları model çıktısından alınmaz; yalnızca kanonik sözleşmedeki onaylı alan yolları sunucu tarafından bağlanır.
- Taslak cümleleri sunucuda sabit sözleşme metinleriyle kurulur. Klinik bulgu ve iki sonuç değeri yalnızca kullanıcı onaylı değerler olarak yerleştirilir.
- TCKN taslak bağlamına gönderilmez ve taslak metnine alınmaz.
- Alan düzeltmesi, belge türü değişimi, sayfa dönüşümü, belge yükleme veya belge silme; önceki taslak metadatasını `invalidated` yapar. Kaynak verisi değişmiş taslak tekrar açılamaz.
- Denetim kaydı taslak içeriğini değil; taslak kimliğini, model adını ve istem sürümünü saklar.

## Zorunlu koşullar

Tüm kritik alanlar eksiksiz, çelişkisiz ve kullanıcı tarafından onaylı olmadan taslak üretimi `409 report_approval_required` ile durur. Yerel Qwen çalışma zamanı, GPU veya model klasörü erişilemezse `503 llm_unavailable` ile durur; CPU, bulut veya başka model geri dönüşü yoktur.

Qwen3-8B'nin indirilen tam BF16 ağırlıkları 8 GB VRAM'e sığmadığından uygulama yalnızca 4-bit GPU yükleme ister. GPU belleğine bütünüyle sığmayan model CPU'ya sessizce taşınmaz.

## Açık blocker'lar

Kurumsal `.docx` şablonu, kimliksiz kurum belge örnekleri ve SAYI önekinden sonraki numaralandırma kuralı sağlanmadı. Bu nedenle taslak kaydedilebilir ve incelenebilir; fakat `.docx` üretim rotası ya da indirme düğmesi yoktur.

## Doğrulama

Sentetik testler şunları kapsar:

1. Onaylı alanlardan şemalı yerel taslak ve JSON/TXT dosyalarının kaydı;
2. TCKN'nin model bağlamı ve taslak metni dışında kalması;
3. Onaysız kritik alanlarda taslak oluşturmanın engellenmesi;
4. Yerel model erişilemezken fallback uygulanmaması ve dosya yazılmaması;
5. Modelin geçersiz bir kaynak yolu verse bile kaynak kümesini seçememesi veya azaltamaması.
