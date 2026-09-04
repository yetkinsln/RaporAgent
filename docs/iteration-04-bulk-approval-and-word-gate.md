# Dördüncü iterasyon: toplu onay ve Word üretim kapısı

## Toplu onay

Kullanıcı, OCR/çıkarım incelemesinden sonra **Okunan alanları topluca onayla** düğmesini kullanabilir. Bu bir otomasyon değildir: düğme açık kullanıcı onayı ister ve denetim kaydına yalnızca onay sayısı ile alan yollarını yazar.

- Kaynakta değeri olan, çelişkisiz alanlar onaylanır.
- `missing`, `conflict` ve checksum doğrulamasını geçmeyen TCKN alanları atlanır.
- Atlanan alanlar arayüzde alan adı ve gerekçesiyle gösterilir.
- Epikriz ve Anabilim Dalı özetleri de kaynaklı alan kartları olarak görünür; gizli alan onayı yoktur.

## Word üretim kapısı

Bu belge, kurumsal girdiler sağlanmadan önceki Word üretim kapısını açıklar. Girdiler daha sonra sağlanmış ve işlevsel üretim akışı [beşinci iterasyonda](iteration-05-institutional-docx.md) uygulanmıştır.

Bu davranış bir eksik fallback değil, zorunlu güvenlik kapısıdır. Gerçek üretimi açmak için aşağıdaki kurum girdileri gerekir:

1. Yer tutucuları ve biçimi korunacak gerçek kurumsal `.docx` şablonu;
2. Şablon alanları ile kanonik kaynak alanları eşleştirme kararı;
3. Kimliksiz kurum örnekleriyle render/doğruluk kabul testi;
4. `6153143-101.00-26/` SAYI önekinden sonraki değerin üretim kuralı.

Şablon yokken kodla benzer görünümlü kurumsal Word dosyası üretilmez.
