# İlk iterasyon: kaynaklı doğrulama dilimi

## Teslim edilen akış

İlk iterasyon yalnızca aşağıdaki dikey dilimi uygular:

```text
Yerel yükleme veya sentetik fixture
  → PNG/JPEG sayfası veya PDF sayfalaştırma
  → OCRLine (metin, güven, dört köşeli poligon, okuma sırası)
  → kural tabanlı alan çıkarımı ve JSON Schema doğrulaması
  → kaynak sayfası vurgusu, kullanıcı düzeltmesi ve tek tek onay
```

`backend/rapor_agent/ocr.py` içindeki `PaddleOcrProvider`, PaddleOCR 3.x çıktı farklarını `OCRLine` modeline izole eder. Paket veya yapılandırılmış yerel algılama/tanıma modeli kullanıma hazır değilse işlem hata durumu ile biter; başka OCR hizmetine geçmez veya çalışma anında model indirmez. Sentetik demo ise yalnızca açıkça `is_synthetic` işaretli satırları kullanır; yüklenen belge için fixture ya da gizli fallback uygulanmaz.

## Kanonik şema

`schemas/case-extraction.schema.json` sürümü `1.2.0` oldu. Kaynaklı alanlar artık şunları taşır:

- normalize edilmiş `value` ile birlikte belgeden alınan `original_value`;
- belge, sayfa, kanıt metni, OCR güveni ve özgün dört köşeli poligonu içeren `provenance`;
- kaynaklar çeliştiğinde sessiz seçim yerine tüm `candidates`.

Tarih normalizasyonu yalnızca çıkarım değeri için kullanılır; özgün değer ayrıca korunur. TCKN doğrulaması checksum ile yapılır; geçerli checksum kişinin kimliğini kanıtlamaz ve kullanıcı onayının yerini almaz.

Hasta kimliğinde doğum yeri ile doğum tarihi; tıbbi belge bilgisinde protokol numarası ve rapor numarası da ayrı alanlardır. `T.C. Kimlik No`, `Doğum Yeri ve Tarihi`, `Protokol No/Numarası` ve `Rapor No/Numarası` gibi etiketler kanıt satırı, poligon ve güven değeriyle eşleştirilir. Geçersiz TCKN checksum sonucu bloklayıcı uyarıdır; değer sessizce düzeltilmez.

Formlarda etiket ve değer PaddleOCR tarafından ayrı kutulara bölünmüşse, yalnızca aynı yatay satırda etiketin sağındaki en yakın, başka bir etiket olmayan kutu aday kabul edilir. Bu geometrik koşul sağlanmazsa alan `missing` kalır; satırlar veya sütunlar arasında tahminî eşleştirme yapılmaz.

Bir belgede birden fazla `Adı Soyadı` etiketi varsa, `muayene eden`, `hekim`, `doktor`, `düzenleyen` veya imza bağlamındaki aday hasta kimliği alanına alınmaz. Hasta/muayene edilen bağlamındaki aday kaynaklanır; kalan belirsizlikte alan sessizce seçilmez.

## Kullanıcı deneyimi ve sınırlar

- TCKN alan kartında varsayılan olarak maskelenir; kullanıcı açıkça **Açık göster** seçeneğini tıklarsa yerel oturumda görüntülenir.
- Kaynak düğmesi ilgili belge ve sayfayı seçer; OCR poligonu sarı vurgulanır.
- `missing` ve `conflict` alanlar onaylanamaz. Çatışan adaylar kaynaklarıyla listelenir.
- Alanı düzeltmek `user_corrected` durumunu atar ve önceki onayı kaldırır.
- Ham belge, OCR metni veya alan değeri uygulama loguna yazılmaz. Denetim kaydında yalnızca olay türü ve alan yolu bulunur.
- İstemci/sunucu sözleşmesi `case-extraction.schema.json` dosyası üzerinden doğrulanır; kopya bir vaka şeması oluşturulmamıştır.

## Açık blocker’lar

| Blocker | Bu iterasyondaki davranış |
| --- | --- |
| Kurumsal Word şablonu yok | `.docx` rotası yok; Word düğmesi pasif. |
| Kimliksiz kurum örneği yok | OCR kalite eşiği için kurum verisi üzerinde iddia yok. |
| SAYI numaralandırma kuralı yok | Kaynakta olmayan numara üretilmez. |

Bu blocker’lar API sonucunda `blocking` uyarı olarak görünür ve `ready_to_generate` değerini `false` tutar.

## Doğrulama kapsamı

`backend/tests/test_first_slice.py` şunları denetler:

1. Sentetik üst yazı + genel adli muayene belgesinin sayfa, poligon, alan ve onay akışını;
2. Farklı iki kaynakta ad-soyad çelişkisinin adaylarıyla korunmasını;
3. Eksik ve düşük güvenli kritik alanların bloklayıcı uyarı olmasını;
4. Yerel OCR erişilemezken otomatik başka servise geçilmemesini.
5. Kimlik/protokol/rapor numarası etiket varyantlarının kaynak kanıtıyla çıkarılmasını.

İstemci testleri TCKN maskelemesini ve çok değerli alan düzeltmesini denetler. Kurumsal kalite metrikleri, kimliksiz kurum doğrulama seti sağlanana kadar ölçülmüş sayılmaz.
