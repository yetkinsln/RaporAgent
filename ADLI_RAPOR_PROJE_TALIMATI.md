# Yerel Adli Rapor Taslak Sistemi — Coder Görev Tanımı

## 1. Amaç

Telefon fotoğrafı veya PDF olarak yüklenen adli tıbbi belgeleri tamamen yerel ortamda okuyup alanlarını kaynaklarıyla çıkaran, kullanıcıya doğrulatan ve kurumun Word şablonuna uygun bir **rapor taslağı** oluşturan masaüstü-odaklı web uygulaması geliştir.

Bu uygulama karar destek ve yazım yardımcısıdır. Yetkili hekimin tıbbi değerlendirmesinin, düzeltmesinin, onayının veya imzasının yerini alamaz.

## 2. Temel kullanıcı akışı

1. Kullanıcı yeni bir vaka oluşturur.
2. Şu belge türlerinden bir veya daha fazlasını JPG, PNG veya PDF olarak yükler:
   - Üst yazı
   - Genel adli muayene raporu
   - Epikriz/acil servis notu
   - Adli Tıp Anabilim Dalı muayene notu
3. Sistem dosyaları güvenli biçimde yerel çalışma alanına alır, PDF sayfalarını görüntüye dönüştürür ve belge türünü önerir.
4. Kullanıcı belge türlerini görür ve gerektiğinde düzeltir.
5. Sistem sayfa yönü/perspektifi ile metin satırı yönünü düzeltir, OCR yapar ve alanları çıkarır.
6. Doğrulama ekranında belge görüntüsü solda, çıkarılmış alanlar sağda gösterilir. Bir alana tıklanınca kaynak sayfadaki kanıt bölgesi vurgulanır.
7. Düşük güvenli, eksik veya çelişkili alanlar açıkça işaretlenir. Kullanıcı kritik alanları tek tek onaylar/düzeltir.
8. Sistem onaylı veriden rapor önizlemesi üretir.
9. Son kontrol tamamlandığında `.docx` oluşturulur ve indirilir.

## 3. Zorunlu alanlar ve kaynaklar

### Üst yazı

- Gönderen makam
- Yazı tarihi
- Yazı sayısı
- Hasta adı soyadı
- TCKN
- Doğum tarihi
- İlgili olay
- Rapor istenen hususlar

### Genel adli muayene raporu

- Raporu düzenleyen hastane/kurum
- Rapor tarihi
- Rapor sayısı
- Başvuru/olay tarihi ve saati
- Başvuru nedeni/olay türü
- Klinik bulgular
- Kaynakta açıkça yazıyorsa BTM değerlendirmesi
- Kaynakta açıkça yazıyorsa hayati tehlike değerlendirmesi

### Epikriz veya acil servis notu

- Kurum/birim
- Tarih
- Protokol numarası
- Öykü, tetkik, tanı, tedavi ve önemli klinik bulgular

### Adli Tıp muayene notu

- Muayene tarihi ve saati
- Öykü
- Genel durum, bilinç ve oryantasyon/kooperasyon
- Travmatik lezyonlar
- Ekstremite/ROM/kas gücü/ambulasyon
- Nörolojik ve diğer sistem muayeneleri

## 4. Veri güvenilirliği sözleşmesi

Her değer düz metin olarak değil, aşağıdaki meta verilerle tutulur:

```json
{
  "value": "örnek değer",
  "status": "extracted",
  "source_document_id": "doc_123",
  "page": 1,
  "evidence_text": "kaynakta görülen kısa ifade",
  "ocr_confidence": 0.94,
  "polygon": [[10, 20], [220, 18], [222, 52], [12, 54]]
}
```

`status`: `extracted`, `user_corrected`, `missing` veya `conflict` olmalıdır. Hasta kimliği, üst yazı bilgileri ve tıbbi sonuç alanları kullanıcı onayı olmadan `approved` sayılmaz. Kanonik ayrıntı `schemas/case-extraction.schema.json` dosyasındadır.

## 5. OCR ve belge işleme gereksinimleri

- PaddleOCR 3.x için tek bir adaptör sınıfı oluştur; kütüphane çıktısını uygulamanın kanonik `OCRLine` modeline dönüştür.
- Türkçe için `lang="tr"` ve Latin PP-OCRv5 tanıma modelini yapılandırılabilir seçenek olarak değerlendir; gerçek kurum örneklerinden oluşturulmuş anonimleştirilmiş doğrulama setinde ölçüm yapmadan model üstünlüğü iddia etme.
- Belge yönü, unwarping ve metin satırı yönü seçeneklerini belge tipine göre deneyebilmek için yapılandırılabilir tut.
- OCR poligonlarını, özgün metni ve güven değerini sakla.
- Ön işleme tek bir zorunlu threshold zinciri olmamalı. Orijinal/düzeltilmiş/kontrast varyantlarından hangisinin kullanılacağı ölçülebilir kalite sonucuna göre seçilmeli.
- Dört köşe bulunamıyorsa orijinal görüntüyle devam et ve manuel kırpma/döndürme seçeneği sun.
- TCKN checksum doğrulaması yap; ancak geçerli checksum doğru kişiye ait olduğunu kanıtlamaz.
- Tarihleri `DD.MM.YYYY` kanonik biçimine dönüştürmeden önce belgedeki özgün değeri sakla.
- Birden çok sayfalı ve aynı türden birden çok belgeyi destekle.

## 6. Yerel LLM gereksinimleri

- Model sunucusu varsayılan olarak `localhost` üzerinden çalışmalı. Ollama önerilir; sağlayıcı arayüzü LM Studio gibi OpenAI uyumlu yerel sunuculara da izin verebilir.
- Yapılandırılmış çıktı JSON Schema ile zorlanmalı ve sunucuda Pydantic ile tekrar doğrulanmalı.
- Alan çıkarımı önce deterministik kurallar/regex ve konumsal ipuçlarıyla yapılır. LLM; belge sınıflandırma, bağlamlı özetleme ve kanıt adaylarını ilişkilendirme için yardımcıdır.
- Model kaynakta bulunmayan bilgi üretemez. Kanıt bulunamazsa `null`/`missing` döndürür.
- LLM’ye yalnızca gerekli OCR bölümleri gönderilir; tüm vaka verisini gereksiz yere bağlama koyma.
- İstemler sürümlenir ve her üretilen taslakta model adı, model sürümü/digest'i, istem sürümü ve zaman damgası teknik denetim kaydına eklenir.
- LLM erişilemiyorsa deterministik alan çıkarımı ve manuel düzenleme çalışmaya devam etmelidir.

## 7. Rapor oluşturma kuralları

- Kurumdan alınmış gerçek `.docx` dosyası şablon olarak kullanılmalı. `docxtpl` ile yer tutucular doldurulmalı; gerekiyorsa son rötuşlar `python-docx` ile yapılmalı.
- Şablonun yazı tipi, punto, kenar boşluğu, paragraf aralığı, başlık, alt çizgi ve sayfa yapısı korunmalı.
- `SAYI` öneki: `6153143-101.00-26/`. Önekten sonraki değer kaynakta yoksa uydurulmaz.
- Tarih: varsayılan olarak günün tarihi önerilir ve kullanıcıya onaylatılır.
- Konu: onaylanmış hasta adı soyadı.
- İlgi (a): gönderen makam + üst yazı tarihi + sayısı.
- İlgi (b): genel adli muayene raporunu düzenleyen kurum + tarih + sayı.
- Maddeler sırasıyla genel adli muayene raporu, epikriz/acil servis notu ve Adli Tıp muayene notundan oluşturulur.
- Sonuçtaki hayati tehlike ve BTM seçenekleri kullanıcı tarafından açıkça onaylanmadan rapor üretilemez.
- Çözülmemiş `...`, `…..`, `{{placeholder}}`, `None` veya `null` bulunan belge indirilemez.
- Dosya adı: `AD_SOYAD-rapor01.docx`; aynı dosya varsa sıra numarası artırılır ve dosya ezilmez.

Tam metin sözleşmesi: `.codex/skills/adli-rapor-gelistirme/references/rapor-sozlesmesi.md`.

## 8. Arayüz gereksinimleri

- React + Vite ve koyu tema.
- Aşamalar: Vaka → Belgeler → OCR → Doğrulama → Önizleme → İndir.
- Yükleme alanı sürükle-bırak ve dosya seçimi desteklemeli.
- Her dosyada belge türü, sayfa sayısı, işlem durumu ve hata bilgisi görünmeli.
- Sayfa görüntüsü üzerinde OCR kutuları açılıp kapatılabilmeli; seçili alanın kanıt kutusu vurgulanmalı.
- Alan kartlarında değer, kaynak, güven ve durum görünmeli.
- Çelişkiler yan yana karşılaştırılmalı; kullanıcı hangi değeri seçtiğini görebilmeli.
- “Word oluştur” düğmesi, zorunlu kontroller tamamlanmadan pasif olmalı ve nedenini açıklamalı.
- TCKN varsayılan olarak maskeli olmalı.

## 9. Önerilen mimari

### Önerilen MVP

- Frontend: React, Vite, TypeScript
- Backend: FastAPI, Pydantic
- OCR/görüntü: PaddleOCR, OpenCV, PyMuPDF veya eşdeğer yerel PDF dönüştürücü
- Yerel LLM: Ollama sağlayıcı adaptörü
- Word: docxtpl + python-docx
- Veritabanı: SQLite; çok kullanıcılı kurulum gerekiyorsa PostgreSQL'e geçirilebilir
- Kuyruk: MVP'de uygulama içi görev yöneticisi; eşzamanlı kullanım artarsa ayrı iş kuyruğu

Python zaten OCR, şema doğrulama ve Word üretim merkezidir. Bu nedenle sırf “MERN” adı için Express ve MongoDB eklemek MVP'yi gereksiz yere iki backend'e böler.

### MERN kesin zorunluysa

- React arayüz → Express API/orchestrator → Python OCR/LLM/Word servisi
- MongoDB vaka meta verisini tutabilir; ham dosya ve üretilen Word belgeleri dosya sisteminde şifreli/erişim kontrollü saklanır.
- Express ile Python arasında aynı JSON Schema/OpenAPI sözleşmesi kullanılır.

Akış ve sınırlar `docs/architecture.md` dosyasında ayrıntılıdır.

## 10. API kapsamı

İsimler örnektir; OpenAPI sözleşmesiyle kesinleştir:

- `POST /api/cases`
- `POST /api/cases/{case_id}/documents`
- `PATCH /api/documents/{document_id}/type`
- `POST /api/cases/{case_id}/process`
- `GET /api/jobs/{job_id}`
- `GET /api/cases/{case_id}/extraction`
- `PATCH /api/cases/{case_id}/fields/{field_path}`
- `POST /api/cases/{case_id}/validate`
- `POST /api/cases/{case_id}/report-preview`
- `POST /api/cases/{case_id}/report`
- `GET /api/reports/{report_id}/download`

Dosya uzantısına güvenme; MIME/imza kontrolü, boyut ve sayfa sınırı uygula. Yüklenen dosya adını doğrudan disk yolu olarak kullanma.

## 11. Güvenlik ve mahremiyet

- Uygulama çalışma anında internet erişimine ihtiyaç duymamalı.
- Ham dosyalar ve türetilmiş veriler için saklama süresi ve silme akışı yapılandırılmalı.
- Rol/yetki, ekran kilidi/oturum süresi ve denetim kaydı kurumla netleştirilmeli.
- Denetim kaydı kimin hangi alanı ne zaman değiştirdiğini tutmalı; gereksiz sağlık içeriğini loglamamalı.
- Yedekleme, disk şifreleme, KVKK yükümlülükleri ve kurum içi dağıtım için kurumun hukuk/bilgi güvenliği birimiyle ayrıca değerlendirme yapılmalı. Kod kendi başına “KVKK uyumlu” ilan edilmemeli.

## 12. Test ve kabul ölçütleri

Asgari senaryolar:

- Düzgün taranmış PDF
- Eğik/perspektifli telefon fotoğrafı
- 90° ve 180° dönük sayfa
- Düşük kontrast ve gölgeli sayfa
- Çok sayfalı belge
- Aynı hastaya ait alanlarda tutarlı belgeler
- İki belgede farklı TCKN/tarih/ad soyad
- Eksik epikriz veya eksik üst yazı
- Yerel LLM kapalı
- OCR güveni düşük kritik alan
- Aynı isimle ikinci rapor üretme
- Yer tutucu kalmış rapor üretme girişimi

Kabul için:

- Zorunlu kritik alanların hiçbiri sessizce uydurulmamalı.
- Kullanıcı her rapor cümlesini kaynak alanlara kadar izleyebilmeli.
- Kritik çelişki varken rapor indirilememeli.
- Oluşan `.docx`, Word/LibreOffice ile açılmalı ve kurum şablonunun düzeni korunmalı.
- Tüm temel işlem gerçek hasta verisi olmadan sentetik fixture'larla test edilebilmeli.
- Test hedefleri ve ölçüm yöntemi `docs/acceptance-criteria.md` içinde uygulanabilir biçimde tutulmalı.

## 13. Aşamalı geliştirme planı

1. Vaka/dosya yükleme, güvenli depolama ve belge görüntüleme
2. OCR adaptörü, poligonlar ve manuel kırpma/döndürme
3. Kanonik şema, deterministik alan çıkarımı ve TCKN/tarih doğrulama
4. Kaynak vurgulu doğrulama ve çelişki ekranı
5. Yerel LLM ile şemalı yardımcı çıkarım/özetleme
6. Kurumsal Word şablonu, önizleme ve indirme engelleri
7. Denetim kayıtları, veri silme, paketleme ve performans ölçümü

Her aşama uçtan uca çalışan ve test edilmiş bir dikey dilim olarak teslim edilmelidir.

## 14. Kapsam dışı

- Otomatik tanı koymak veya tıbbi kanaat üretmek
- E-imza atmak
- UYAP, HBYS veya başka kurumsal sisteme entegrasyon (ayrı yetki ve kapsam gerekir)
- Buluta belge göndermek
- Mobil uygulama
- İlk sürümde genel amaçlı RAG/vektör veritabanı

## 15. Başlamadan önce kullanıcıdan istenecek girdiler

Kodlamayı tamamen durdurmadan iskelet ve sentetik testler hazırlanabilir; fakat gerçek `.docx` üretimi ve alan eşikleri için şunlar gerekir:

- Kimlik bilgileri temizlenmiş her belge türünden örnekler
- Kurumun gerçek Word şablonu
- SAYI önekinden sonra numaranın nasıl üretileceği
- Eksik belge durumunda kullanılacak resmi ifade
- Sonuç seçeneklerinin kesin kurumsal yazımı
- Kullanıcı/rol ve saklama süresi beklentileri
