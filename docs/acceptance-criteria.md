# Kabul ve kalite ölçümü

## Ölçüm seti

Gerçek kişileri tanımlamayan, yetkili şekilde anonimleştirilmiş veya tamamen sentetik en az şu belge varyantları hazırlanmalıdır:

- Her belge türünden temiz tarama
- Telefon fotoğrafı: eğim, perspektif, gölge ve düşük ışık
- Döndürülmüş sayfa
- Çok sayfalı PDF
- Türkçe karakter yoğun metin
- Çelişkili kimlik/tarih alanları

## Alan bazlı metrikler

Sadece genel OCR karakter doğruluğu yeterli değildir. Aşağıdakileri ayrı raporla:

| Alan grubu | Ölçüm | MVP hedefi |
|---|---|---:|
| TCKN | Tam eşleşme + checksum | %100 doğrulama; yanlışsa otomatik onay yok |
| Tarih/saat | Normalize edilmiş tam eşleşme | ≥ %95 |
| Yazı/rapor/protokol sayısı | Tam eşleşme | ≥ %95 |
| Ad soyad | Türkçe karakter duyarlı tam eşleşme | ≥ %95 |
| Uzun klinik metin | Kullanıcı düzeltme oranı ve kaynak kapsaması | Baseline ölç, sürümler arasında iyileştir |

Hedefler anonimleştirilmiş kurum veri setinde ölçülmeden “sağlandı” sayılmaz.

## Zorunlu engeller

Aşağıdaki durumlarda `POST /report` başarısız olmalı ve kullanıcıya gerekçe dönmelidir:

- Kritik alan `missing` veya `conflict`
- Hasta kimliği onaylanmamış
- Hayati tehlike veya BTM sonucu onaylanmamış
- Şablon bulunamıyor/bozuk
- Çözülmemiş yer tutucu var
- Rapor bağlamı JSON Schema doğrulamasından geçmiyor

## Otomatik test katmanları

- Unit: TCKN, tarih, sayı ayrıştırma, dosya adı, placeholder taraması
- Contract: OCR/LLM sağlayıcı adaptörleri ve JSON Schema
- Integration: dosya yüklemeden önizlemeye sentetik vaka
- Golden document: oluşturulan DOCX içeriği ve temel stil özellikleri
- UI: çelişki seçimi, kaynak vurgusu, üretim düğmesi engelleri

Golden document testi yalnızca XML metnini değil; Word/LibreOffice ile açılabilirliği ve beklenen paragraf/stil özelliklerini de doğrulamalıdır.
