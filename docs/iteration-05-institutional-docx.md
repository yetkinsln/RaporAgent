# Iteration 05 — Asıl kurumsal Word taslağı v2

## Kaynak ve dönüşüm

- Düzen otoritesi `Templates/Doldurulmamış-asıl-şablon.doc` dosyasıdır ve değiştirilmeden korunur.
- Bu eski OLE `.doc` dosyası yalnızca geliştirme sırasında, yerel Docker içindeki LibreOffice ile `.docx`e dönüştürülmüştür.
- Uygulamanın doldurduğu dosya `Templates/adli-rapor-sablonu-v2.docx`tir. Başlık, A4 sayfa boyutu, kenar boşlukları, paragraf girintileri, otomatik numaralandırma ve EKİ konumu boş asıl şablondan gelir.
- `Templates/Doldurulmuş.doc` yalnızca yerel görsel/yerleşim karşılaştırmasında kullanılmıştır. İçindeki değerler koda, mapping'e, teste, ekran görüntüsüne veya loga kopyalanmamıştır.

## Eşleme sözleşmesi

`Templates/kurumsal-girdiler_mapping_alan-esleme-v2.json`, 25 benzersiz şablon bağlam alanını ve her alanın kaynağını belirtir. Uygulama açılışında şu koşullar doğrulanır:

1. Mapping sürümü `2.0.0` ve hedef şablon adı doğrudur.
2. SAYI politikası `manual`, `auto_generate: false` değerindedir.
3. JSON'daki bağlam yolları ile Word paketindeki Jinja yer tutucuları bire bir aynıdır.
4. Çıkarım kaynaklı değerler `missing` veya `conflict` değildir ve kullanıcı tarafından onaylanmıştır.
5. TCKN checksum doğrulamasından; hayati tehlike/BTM alanları kapalı `yes`/`no` sözleşmesinden geçmiştir.

## Akış

1. OCR alanları belge, sayfa, kanıt metni, poligon ve kullanıcı onayıyla tamamlanır.
2. Kullanıcı Word paneline SAYI değerini aynen manuel girer. Uygulama değer üretmez, tamamlamaz veya biçim önermesi yapmaz.
3. Kullanıcı ayrıca rapor tarihi, muayene tarih-saati, anamnez ve güncel muayene bulgularını yerelde girer.
4. Kullanıcı hem aktarılacak alanları işaretleyerek hem de ikinci onay penceresinde üretimi açıkça onaylar.
5. Sunucu onaylı kaynakları deterministik Türkçe cümlelere yerleştirir. Qwen serbest metni veya model tarafından uydurulan bir değer Word'e aktarılmaz.
6. Çözülmemiş Jinja etiketi, `None`, `null`, çoklu nokta veya yinelenen ZIP parçası kalırsa çıktı kabul edilmez/temizlenir.
7. Başarılı dosya vaka altındaki `reports/` dizinine `AD_SOYAD-rapor01.docx` biçiminde, mevcut dosyayı ezmeden yazılır.
8. Kaynak alanı, belge türü, sayfa dönüşümü veya Word girdisi değişirse önceki DOCX taslağı `superseded` olur ve indirme rotası `409` döndürür.

## Alan kullanımı

- Manuel: `document.number`, `document.date`, `manual.examination_date`, `manual.examination_time`, `manual.history`, `manual.current_exam_findings`.
- Kaynaklı: gönderen makam/yazı tarihi/yazı sayısı/olay/istenen hususlar; muayene edilen kişinin kimliği; genel adli muayene kurum, tarih, rapor, protokol, başvuru nedeni ve bulguları.
- Türetilmiş: doğum yeri+tarihi birleşimi ile yalnızca kullanıcı onaylı `yes`/`no` değerlerinden oluşturulan hayati tehlike ve BTM cümleleri.
- Muayene eden kişinin adı, cinsiyet ve sicil alanları sağlanan asıl çıktı düzeninde bulunmadığından v2 Word formundan çıkarılmıştır.

## Doğrulama

- Backend sentetik testi; 25 alanlı sözleşmeyi, tamamen manuel SAYI'yı, açık onay kapısını, indirilebilir DOCX'i, sıra artırmayı ve kaynak değişince geçersizleşmeyi kapsar.
- Frontend testi ve TypeScript üretim derlemesi Word formu değişikliğini kapsar.
- Sentetik DOCX yerelde PDF/PNG'ye dönüştürülmüş; tek sayfa A4 kaldığı, başlık/tarih, 1–3 inceleme maddeleri, 1–2 sonuç maddeleri ve EKİ konumunun taşmadığı görsel olarak doğrulanmıştır.

## Yerel Qwen3 GPU çalışma zamanı

- Qwen3 yalnızca NVIDIA GPU üzerinde 4-bit nicemleme ile yüklenir; CPU veya uzak model geri dönüşü yoktur.
- Docker imajı, PyTorch paketinden önceden derlenmiş bytecode dosyalarını LLM kurulumu sonrasında temizler. Bu, `bitsandbytes` içe aktarımında görülebilen `bad marshal data` hatasını önler.
- Model klasörü salt-okunur bağlanır; `HF_HUB_OFFLINE` ve `TRANSFORMERS_OFFLINE` ile çalışma anında dış model kaynağı kullanılmaz.
