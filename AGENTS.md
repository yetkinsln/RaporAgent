# Coder çalışma talimatları

Bu depo bir belge işleme ve adli tıbbi rapor **taslak** uygulamasıdır.

## Başlamadan önce

1. `ADLI_RAPOR_PROJE_TALIMATI.md` dosyasını oku.
2. Adli rapor alanına dokunan işlerde `.codex/skills/adli-rapor-gelistirme/SKILL.md` becerisini kullan.
3. İstenen değişiklik gerektirmiyorsa teknoloji veya kapsamı kendiliğinden büyütme.

## Değiştirilemez sınırlar

- Tüm hasta verisi yerelde işlenir; bulut OCR/LLM/analitik servisine gönderilmez.
- Sistem nihai tıbbi karar vermez ve kullanıcı onayı olmadan `.docx` üretmez.
- Eksik veya çelişkili değer tahmin edilmez.
- Her alanın kaynak belge, sayfa ve kanıt metni saklanır.
- Gerçek kişisel/sağlık verisi koda, fixture'a, ekran görüntüsüne veya loga eklenmez.
- API ve veri modellerinde mümkün olduğunca tek bir kanonik şema kullanılır; istemci ve sunucu kopyaları otomatik üretilir.
- Mevcut kurumsal `.docx` şablonu varsa biçimi kodla yeniden kurmak yerine o şablon doldurulur.

## Uygulama yaklaşımı

- Küçük, uçtan uca çalışan dilimler geliştir: yükleme → OCR → doğrulama → onay → taslak üretimi.
- Her dilimde başarı yolu kadar düşük OCR güveni, eksik belge, çelişki ve servis erişilemiyor durumlarını test et.
- Değişen davranış için test ekle. Sentetik Türkçe örnekler kullan.
- Bağımlılık sürümlerini kilitle ve PaddleOCR API sürümü değişikliklerini adaptör içinde izole et.
- Gizli hata yutma veya otomatik fallback ile veri seçme yapma; kullanıcıya eyleme dönük hata göster.

## Teslim ölçütü

Kod, testler, kullanıcıya görünen hata/uyarılar ve ilgili dokümantasyon birlikte güncellenmiş olmalıdır. Çalıştırılmamış testleri çalışmış gibi bildirme.
