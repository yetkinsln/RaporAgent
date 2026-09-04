# Kurumsal Word şablonu uygulama sözleşmesi

- **Referans:** `C:\Users\Yetkin\Desktop\RaporAgent\Templates\adli-rapor-sablonu.docx`
- **SHA-256:** `33b027a49da0d2af14e670be4d38f4df3736bc276ac5ea8374ee1d7c41c4b082`
- **Bölümler:** tek, portre, Letter (8.50 × 11.00 inç); kenar boşlukları 0.80 inç.
- **Sayfa sayısı:** LibreOffice/soffice bu bilgisayarda bulunamadığından çözülmedi. Üretilen belge, uygun bir Office/LibreOffice çalışma zamanında ayrıca render edilerek incelenecek.
- **Stil kanıtı:** 35 doğrudan run, 32 doğrudan paragraf biçimlendirmesi var; şablonun görünümü korunacak ve genel stil/preset uygulanmayacak.
- **Kontroller:** Word içerik denetimi bulunmuyor; eşleme, Jinja yer tutucuları üzerinden yapılıyor.

## Düzenlenebilir slotlar

Eşleme çalışma kitabındaki 15 slot yalnızca aynı ada sahip Jinja yer tutucusuyla doldurulur: belge numarası ve tarihi; üst yazı makamı ve sayısı; hasta kimlik/protokol bilgileri; muayene tarihi; anamnez; bulgular; sonuç; muayene edenin adı ve isteğe bağlı sicil bilgisi.

## Koruma ve doğrulama kapıları

- Referans dosya salt okunur tasarım otoritesidir; üretimde çalışma kopyası `docxtpl` ile doldurulur.
- Şablon yer tutucuları ile Excel eşlemesi bire bir uyuşmadan üretim yapılmaz.
- Yalnızca kullanıcı tarafından onaylanmış OCR alanları ve açıkça kaydedilip üretim anında onaylanmış manuel Word alanları kullanılır.
- EBYS kaynaklı SAYI alanı uygulama tarafından üretilmez; biçim doğrulanır.
- Çözülmemiş Jinja yer tutucusu, `None`, `null` veya çoklu nokta bulunan çıktı saklanmaz.
- Üretimden sonra template/final paket farkı ve tüm sayfa render'ı, bir Office renderer kullanılabildiği ortamda gözden geçirilir.
