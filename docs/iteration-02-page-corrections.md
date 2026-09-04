# İkinci iterasyon: manuel sayfa düzeltmesi

## Amaç

Telefon fotoğrafı veya döndürülmüş sayfa ile gelen belgelerde, kullanıcı OCR çalışmadan önce sayfayı yerelde döndürebilir veya kırpabilir. Bu iterasyon LLM, rapor metni ya da Word üretimi eklemez.

## Davranış

- `↶` ve `↷` düğmeleri sayfayı 90° sola/sağa döndürür.
- **Kırp** seçildiğinde kullanıcı sayfa üzerinde alanı sürükleyerek işaretler; küçük ya da geçersiz alan sunucuda reddedilir.
- **Sıfırla**, özgün sayfaya döner. Özgün yükleme hiçbir zaman değiştirilmez.
- Belge kartındaki **Belgeyi sil** düğmesi, onay sonrasında yalnızca seçilen belgenin özgün, sayfa ve türetilmiş yerel dosyalarını siler. Diğer belge dosyaları korunur; silinen belgenin kanıtlarını içerebileceği için mevcut alan çıkarımı da geçersizleşir.
- Her düzeltme `data/cases/<case-id>/derived/` altında yeni türetilmiş PNG oluşturur. Kullanıcı dosya adı türetilmiş yol için kullanılmaz.
- Dönüşüm, eski OCR satırlarını ve alan çıkarımını görünümden kaldırır; belge `OCR bekliyor` durumuna döner. Kullanıcı yeniden OCR çalıştırmadan yeni sayfadan alan çıkarımı yapılmaz.
- Eski OCR satırları yalnızca vaka içindeki yerel `ocr_history` kaydında tutulur; istemciye veya loglara gönderilmez.

Sentetik fixture sayfaları da aynı dönüşüm geometrisini uygular. Bu sayede sarı kaynak vurgusu, döndürülmüş sayfanın güncel koordinatlarına karşılık gelir. Gerçek belge için OCR adaptörü türetilmiş görüntüyü yeniden okur; fixture çıktısı kullanılmaz.

## Bilinen kapsam

Perspektif/unwarping için otomatik seçim bu iterasyonda eklenmedi. Kullanıcı manuel dönüşümden sonra OCR’ı yeniden çalıştırır. Belge sınırı bulunamadığında sistem otomatik kırpma tahmini yapmaz ve kullanıcıya seçim imkânı bırakır.

## Doğrulama

Backend testleri şunları kapsar:

1. Döndürülmüş sentetik PNG sayfanın yerel PNG türevine dönüşmesi;
2. Sayfa boyutlarının ve OCR poligonlarının dönüşümle güncellenmesi;
3. Önceki çıkarımın geçersizleşmesi ve OCR sonrası alanların yeniden üretilmesi;
4. Sıfırlama ile özgün boyut ve dönüşüm geçmişine dönülmesi;
5. Geçersiz kırpma alanının istek doğrulamasında reddedilmesi.
6. Belge silindiğinde yalnızca o belgeye ait özgün/türetilmiş dosyaların kaldırılması ve çıkarımın geçersizleşmesi.
