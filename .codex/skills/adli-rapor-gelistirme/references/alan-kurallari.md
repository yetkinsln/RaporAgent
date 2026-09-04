# Alan ve güvenlik kuralları

## Değiştirilemez kurallar

- Sistem “taslak” üretir. Son tıbbi değerlendirme, düzeltme, onay ve imza yetkili kullanıcıya aittir.
- Kaynakta bulunmayan bilgi üretilmez. Dil modeli boşlukları makul görünen ifadelerle tamamlayamaz.
- Her çıkarılmış alan şu bilgileri taşır: değer, belge kimliği, sayfa, kısa kanıt metni, OCR güveni ve durum.
- `missing`, `conflict` veya eşik altı güvene sahip kritik alan varken Word üretimi engellenir.
- TCKN arayüzde maskeli gösterilir; açık gösterim ve dışa aktarma yetkilendirilmiş işlem olmalıdır.
- Ham belgeler, OCR metinleri ve raporlar uygulama loglarına yazılmaz. Hata loglarında yalnızca vaka kimliği, aşama, hata kodu ve teknik iz bulunur.
- Geliştirme ve otomatik testlerde yalnızca sentetik, açıkça sahte veriler kullanılır.
- Dış ağ çağrıları varsayılan olarak kapalıdır. Model ve OCR paketlerinin ilk indirilmesi ayrı kurulum adımıdır; çalışma sırasında hasta verisi ağdan çıkmaz.

## Kritik alanlar

Şu alanlarda kullanıcı onayı zorunludur:

- Hasta adı soyadı, doğum tarihi ve TCKN
- Üst yazıyı gönderen makam, tarih, sayı ve istenen hususlar
- Genel adli muayene raporu hastanesi, tarih ve sayı
- Olayın türü/tarihi
- Yaşamı tehlikeye sokup sokmadığı
- Basit tıbbi müdahale ile giderilebilirlik
- Arıza/lezyon/yaralanma ifadesi

## Çelişki davranışı

Aynı alan farklı belgelerde farklıysa:

1. Değerlerden birini sessizce seçme.
2. Her iki değeri kaynaklarıyla göster.
3. Alanı `conflict` durumuna getir.
4. Kullanıcının seçimini `user_corrected` olarak ve değişiklik kaydıyla sakla.

## OCR davranışı

- Orijinal dört köşeli poligonu sakla; yalnızca eksen hizalı dikdörtgene indirgeme.
- Orijinal, perspektif düzeltilmiş ve gerektiğinde kontrast artırılmış görüntü varyantlarını değerlendir. Eşiklenmiş görüntü her belge için zorunlu değildir.
- Belge sınırı bulunamazsa işlemi sonlandırmak yerine orijinal görüntüyle devam et ve manuel kırpma uyarısı üret.
- Okuma sırasını yalnızca `y` koordinatına göre kurma; satır kümeleri ve sütun düzenini dikkate al.
- Normalize edilmiş metin yalnızca arama/eşleştirme içindir. Kullanıcıya gösterilen ve rapora aktarılan değer özgün Türkçe karakterleri korur.

## LLM davranışı

- Sıcaklık düşük tutulur ve yapılandırılmış JSON şeması zorlanır.
- Kanıtı olmayan alan `null` döner.
- Model tıbbi hüküm çıkaramaz; yalnızca kaynakta açıkça bulunan hükmü işaretleyebilir.
- Model çıktısı Pydantic/JSON Schema ile doğrulanmadan veri tabanına “onaylı” olarak yazılmaz.
