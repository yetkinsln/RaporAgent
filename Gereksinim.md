Word üretimini güvenli ve kurumsal biçimde açabilmem için üç ayrı girdi paketi gerekiyor. En iyi teslim biçimi aşağıdaki gibi.

## 1. Kurumsal Word şablonu

Tercih edilen format: `.docx`

- Kurumun onaylı, boş veya tamamen sentetik verili nihai rapor şablonu olmalı.
- Üstbilgi, altbilgi, logo, tablolar, kenar boşlukları, imza bölümü, sayfa numaraları ve bölüm sonları korunmuş olmalı.
- PDF tek başına yeterli değildir; yalnızca görsel referans olarak eklenebilir. Doldurulabilir asıl dosya `.docx` olmalıdır.
- `.dotx` varsa `.docx` sürümü de istenir. Makrolu `.docm` tercih edilmez.
- Şablonda gerçek kişi bilgisi, gerçek imza veya gerçek sağlık verisi bulunmamalı.

Şablonun içine teknik yer tutucuları biz ekleyebiliriz. Örnek:

```text
Adı Soyadı: {{ patient.full_name }}
T.C. Kimlik No: {{ patient.tckn }}
Doğum Yeri / Tarihi: {{ patient.birth_place }} / {{ patient.birth_date }}
Protokol No: {{ medical.protocol_no }}
Rapor No: {{ medical.report_number }}
```

Bunlar kullanıcı onayı verilmiş alanlarla doldurulur. Eksik, çelişkili veya onaysız veri Word’e yazılmaz.

## 2. Kimliksiz doğrulama örnekleri ve alan eşlemesi

Buradaki amaç, “OCR’den gelen hangi veri Word şablonunun neresine yazılacak?” sorusunu kesinleştirmektir.

Önerilen klasör düzeni:

```text
kurumsal-girdiler/
  template/
    adli-rapor-sablonu-v1.docx
    adli-rapor-sablonu-v1-referans.pdf
  mapping/
    alan-esleme-v1.xlsx
  validation/
    vaka-01/
      kaynak-ust-yazi-sentetik.pdf
      kaynak-muayene-sentetik.pdf
      beklenen-rapor.docx
      beklenen-rapor.pdf
      beklenen-alanlar.json
    vaka-02/
      ...
  rules/
    sayi-numaralandirma-kurali.md
```

Örnek vakalar en az üç farklı durumu kapsamalı:

- Tüm gerekli alanların bulunduğu normal vaka.
- Bazı alanların eksik olduğu vaka.
- Aynı etiketin farklı kişiler için geçtiği vaka; örneğin “muayene edilen” ve “muayene eden” ad-soyadının karışmadığını gösteren vaka.
- Varsa çok sayfalı belge, ek klinik belge ve tarih biçimi farklılığı.

Örnekler ya tamamen sentetik olmalı ya da geri döndürülemez biçimde anonimleştirilmiş olmalı. Siyah kutu ile kapatılmış gerçek belge, orijinal dosya veya metadata içeriyorsa uygun değildir.

Alan eşlemesini kurum Excel/CSV/Markdown olarak teslim edebilir; uygulamada bunu sürümlü kanonik JSON eşlemesine dönüştürürüz. Excel için önerilen sütunlar:

| Şablondaki bölüm | Kanonik alan yolu | Word yer tutucusu | Zorunluluk | Biçim | Eksikse davranış |
|---|---|---|---|---|---|
| Muayene edilen | `patient.full_name` | `{{ patient.full_name }}` | Zorunlu | Metin | Boş bırak / üretimi engelle |
| TCKN | `patient.tckn` | `{{ patient.tckn }}` | Kurum kararı | 11 hane | Boş bırak |
| Üst yazı sayısı | `request.letter_number` | `{{ request.letter_number }}` | Opsiyonel | Metin | “Belirtilmemiş” yazma |
| Protokol no | `medical.protocol_no` | `{{ medical.protocol_no }}` | Zorunlu | Metin | Üretimi engelle |
| Muayene eden | `medical.examiner_full_name` | `{{ medical.examiner_full_name }}` | Kurum kararı | Metin | Boş bırak |

“Eksikse davranış” sütunu özellikle önemlidir. Sistem kendi başına “bilinmiyor”, “normaldir” veya benzeri hukuki/tıbbi ifade üretmez. Kurumun önceden onayladığı sabit bir ifade kullanılacaksa bunun da eşlemede açıkça yazması gerekir.

## 3. SAYI numaralandırma kuralı

Bu kural kısa bir `.md`, `.txt`, Word belgesi veya Excel tablosu olarak verilebilir. İçeriğinde formül kadar iş kuralı da bulunmalı.

Gerekli bilgiler:

- SAYI alanının kesin metin biçimi.
- Kurum/birim kodu.
- Yıl bilgisi ve yıl değişince sıfırlanma davranışı.
- Sıra numarasının hane sayısı ve baştaki sıfırlar.
- Protokol no, rapor no ve SAYI alanlarının birbirinden farkı.
- Numarayı uygulamanın mı üreteceği, yoksa EBYS gibi başka bir sistemden mi alacağı.
- Taslak yeniden oluşturulursa aynı numaranın korunup korunmayacağı.
- İptal, revizyon ve yeniden düzenleme davranışı.
- Eşzamanlı üretimde benzersizlik kuralı.
- En az üç sentetik örnek.

Örnek kural şablonu:

```md
Alan: SAYI
Biçim: [kurum-kodu]-[yıl]-[birim-kodu]-[altı haneli sıra]
Örnek: ABC-2026-ATM-000123

Sayaç: Her takvim yılı başında sıfırlanır.
Numara kaynağı: EBYS
Uygulama davranışı: EBYS numarası kullanıcı tarafından girilmeden Word üretilemez.
Revizyon: İlk SAYI korunur, revizyon eki ayrıca yazılır.
```

Eğer SAYI numarası EBYS tarafından veriliyorsa, en güvenli yaklaşım uygulamanın numara üretmemesi; kullanıcının onaylı numarayı girmesini zorunlu tutmasıdır.

Bu üç paketi yerel proje klasörüne koyduğunuzda; şablonu doğrudan dolduracak, yalnızca onaylı alanları kullanacak ve çıktıyı görsel olarak da doğrulayacak Word üretim adımını tamamlayabilirim.