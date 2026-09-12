# Rapor Agent 1.0 — yerel yayın kılavuzu

## Yayın kapsamı

Bu sürüm tek iş istasyonunda veya kurumun yetkilendirilmiş yerel çalışma ortamında çalışır. Web arayüzü yalnızca `127.0.0.1:5173` adresine bağlanır; hasta belgesi, OCR sonucu ve rapor taslağı uzak bir servise gönderilmez.

Desteklenen uçtan uca akış:

`belge yükleme → sayfa kontrolü → PaddleOCR → kaynaklı alan çıkarımı → kullanıcı onayı → yerel Qwen taslağı → kurumsal DOCX taslağı`

DOCX yalnızca kritik alanlar onaylandığında, manuel SAYI ve güncel muayene bilgileri girildiğinde ve kullanıcı aktarımı ayrıca onayladığında oluşturulur. Çıktının durumu her zaman `review_required` olarak kalır.

## İş istasyonu gereksinimleri

- Windows 11 ve güncel Docker Desktop (Linux containers)
- NVIDIA GPU, güncel sürücü ve Docker GPU erişimi
- Proje kökünde eksiksiz `qwen3-8b/` model klasörü
- `Templates/adli-rapor-sablonu-v2.docx`
- `Templates/kurumsal-girdiler_mapping_alan-esleme-v2.json`
- Yerel veri alanı için yeterli ve kurum politikasına uygun şifreli disk alanı

## Kurulum ve başlatma

İlk kurulumda veya kod değiştiğinde:

```powershell
.\start.ps1 -Rebuild
```

Sonraki kullanımlarda:

```powershell
.\start.ps1
```

Betik Docker Desktop kapalıysa başlatır, zorunlu model/şablon dosyalarını denetler, servisleri ayağa kaldırır ve `/api/health` yanıtını bekler. Arayüz açıldığında üst çubukta teknik bileşen adları yerine tek bir anlaşılır uygulama durumu görünür.

Servisleri veriyi silmeden durdurmak için:

```powershell
.\stop.ps1
```

## Yayın öncesi doğrulama

```powershell
.\verify-release.ps1
```

Bu kontrol Compose yapılandırmasını, ön uç test ve üretim derlemesini, bağımlılık güvenlik denetimini, web Docker imajının gerçek yayın bağlamında oluşturulmasını ve sentetik arka uç sözleşme testlerini çalıştırır. Gerçek hasta verisi kullanmaz.

Canlı Docker kurulumunu sentetik örnekle doğrulama sırası:

1. **Örnek vakayla dene** ile iki kimliksiz belge oluşturun.
2. **Belgeleri oku ve bilgileri çıkar** düğmesine basın.
3. Kaynak bağlantılarının doğru sayfa poligonunu vurguladığını kontrol edin.
4. **Okunan alanları topluca onayla** işlemini açıkça onaylayın.
5. Yerel Qwen taslağını oluşturun.
6. Manuel SAYI ve sentetik muayene girdilerini yazıp aktarım onayını verin.
7. DOCX'i indirin ve kurum şablonunda görsel olarak inceleyin.
8. Deneme sonunda **Vakayı sil** ile sentetik vaka klasörünü temizleyin.

## Veri yaşam döngüsü

- Vaka verileri `runtime-data/cases/<opak-vaka-kimliği>/` altında tutulur.
- Tarayıcı yalnızca son opak vaka kimliğini saklar; belge ve alan içeriğini saklamaz.
- Tek belge silindiğinde özgün, sayfa ve türetilmiş dosyaları kaldırılır; çıkarım geçersizleşir.
- **Vakayı sil** tüm özgün belgeleri, OCR kayıtlarını, düzeltmeleri, taslakları ve DOCX'leri vaka diziniyle birlikte kaldırır.
- `docker compose down` veya `stop.ps1` vaka verisini silmez.

## Güvenlik sınırı ve kurumsal blockerlar

1.0 paketi genel internete veya kurum ağına doğrudan açılmamalıdır. Çok kullanıcılı/LAN yayını öncesinde kurumun aşağıdakileri yazılı olarak belirlemesi ve altyapıda uygulaması gerekir:

- kullanıcı kimlik doğrulama ve rol/yetki matrisi;
- iş istasyonu ve yedeklerin disk şifreleme standardı;
- vaka saklama, yedekleme ve güvenli imha süreleri;
- işletim sistemi hesabı, fiziksel erişim ve olay günlüğü politikası;
- sürüm dağıtımı, kod imzalama ve güncelleme sorumlusu;
- klinik kabul testi ve yetkili son kullanıcı onayı.

Bu maddeler kod tarafından tahmin edilemez ve kurum kararı olmadan uygulama genel ağa açılmaz.
