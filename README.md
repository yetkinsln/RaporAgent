# Rapor Agent — ilk dikey dilim

Bu depo, adli tıbbi rapor için **nihai karar vermeyen** ve yalnızca yerelde çalışan taslak uygulamasının ilk dilimini içerir:

`yükleme → sayfa görüntüsü → OCR poligonları → kaynaklı alan çıkarımı → kullanıcı onayı`

Bu sürümde yerel Qwen3-8B ile şemalı bölüm planından oluşturulan, kullanıcı incelemesi gerektiren JSON/TXT rapor taslağı kaydı vardır. Word çıktısı, kurumun verdiği boş eski `.doc` belgesinden yerelde türetilen `Templates/adli-rapor-sablonu-v2.docx` ve sürümlü JSON eşleme sözleşmesiyle üretilir. SAYI yalnızca kullanıcı tarafından manuel girilir; uygulama numara üretmez veya önermez. Kaynak alanları ve Word girdileri açıkça onaylanmadan `.docx` oluşturulmaz.

## Çalıştırma

### Docker (önerilen, OCR CPU + yerel LLM GPU)

Docker imajı; PaddleOCR 3.1.0, PaddleX 3.1.2 ve resmi PaddlePaddle 3.0.0 CPU tabanını kullanır. Türkçe için gerekli iki model (`PP-OCRv5_server_det` ve `latin_PP-OCRv5_mobile_rec`) **yalnızca `docker compose build` sırasında** imaja alınır. Çalışma anında uygulama sadece bu imaj içi model yollarına başvurur; model indirme veya bulut OCR fallback'i yoktur.

Yerel Qwen3-8B için proje kökündeki `qwen3-8b/` klasörü zorunludur. Klasör imaja kopyalanmaz; API'ye salt-okunur bağlanır. 8 GB VRAM bulunan sistemlerde model 4-bit GPU yükleme ile çalışır. GPU veya model erişilemezse taslak üretimi hata verir; CPU ya da bulut sağlayıcısına geçmez. İlk model yüklemesi, ilk taslak isteğinde birkaç dakika sürebilir.

```powershell
docker compose build
docker compose up -d
docker compose ps
```

Tek komutla başlatmak ve tarayıcıyı açmak için proje kökünde:

```powershell
.\start.ps1
```

Kod, Dockerfile veya bağımlılıklar değiştiyse imajları da yenilemek için:

```powershell
.\start.ps1 -Rebuild
```

Tarayıcı açmadan yalnızca yerel servisi doğrulamak için `-NoBrowser` eklenebilir.

Arayüz `http://127.0.0.1:5173` adresinde açılır. Vaka verileri proje kökündeki `runtime-data/` dizininde kalır; bu dizin kaynak denetimine dahil edilmez. Gerçek PaddleOCR motorunu imajdaki sentetik belgeyle tekrar denetlemek için:

```powershell
docker compose exec api python scripts/verify_paddle_ocr.py
```

Docker Desktop çalışmıyorsa yukarıdaki komutlar başlatılamaz; uygulama başlatılmadan önce Docker Desktop kurulup Linux container modu açık olmalıdır.

### Yerel geliştirme

Python 3.11–3.13 ile, proje kökünden:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn rapor_agent.main:app --host 127.0.0.1 --port 8000
```

Yerel PaddleOCR adaptörünü gerçek yüklemelerde kullanmak için paket kurulumu ve daha önce kurumca edinilmiş yerel model klasörleri gerekir; çalışma sırasında model indirilmez:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
.\.venv\Scripts\python.exe -m pip install --no-deps paddleocr==3.1.0
$env:RAPOR_AGENT_PADDLE_DET_MODEL_DIR = "C:\yerel-modeller\paddle\det"
$env:RAPOR_AGENT_PADDLE_REC_MODEL_DIR = "C:\yerel-modeller\paddle\rec"
```

Başka bir terminalde:

```powershell
cd frontend
npm install
npm run dev
```

Arayüz `http://127.0.0.1:5173` adresinde açılır. **Sentetik vakayı yükle** düğmesi, gerçek kişi verisi içermeyen üst yazı ve genel adli muayene belgesini oluşturur. Gerçek yüklemelerde PNG, JPEG ve PDF imzası doğrulanır; dosya adı disk yolu olarak kullanılmaz.

Kaynak sayfasındaki `↶`, `↷`, **Kırp** ve **Sıfırla** kontrolleri sayfayı yerelde düzeltir. Bu işlem özgün dosyayı değiştirmez; önceki OCR/alan çıkarımını geçersizleştirir ve yeniden OCR çalıştırılmasını gerektirir. Ayrıntı için [manuel sayfa düzeltmesi](docs/iteration-02-page-corrections.md) belgesine bakın.

Tüm kritik alanlar kaynaklarıyla onaylandığında **Taslağı üret ve yerelde kaydet** etkinleşir. Qwen'in planı sunucuda şemayla doğrulanır; taslak `runtime-data/cases/<vaka>/reports/` altında kullanıcı adı içermeyen rastgele kimlikle `.json` ve `.txt` olarak saklanır. Ayrıntı için [yerel taslak iterasyonu](docs/iteration-03-local-report-draft.md) belgesine bakın.

Çıkarılan alanları kullanıcı incelemesinden sonra tek işlemde onaylamak için **Okunan alanları topluca onayla** kullanılabilir. Eksik, çelişkili ve checksum doğrulamasını geçmeyen TCKN alanları onaylanmaz; gerekçeleri görünür kalır. Word panelinde manuel SAYI, rapor tarihi, muayene tarih-saati, anamnez ve güncel muayene bulguları kaydedilip ayrıca onaylandıktan sonra asıl kurum düzeninde taslak indirilir. Ayrıntı için [toplu onay ve Word üretim kapısı](docs/iteration-04-bulk-approval-and-word-gate.md) ve [kurumsal Word taslağı](docs/iteration-05-institutional-docx.md) belgelerine bakın.

## Testler

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm.cmd run build
npm.cmd test
```

Test fixture’ları açıkça sentetiktir. Kullanıcının arayüzden yüklediği belgeler yalnızca yerel `runtime-data/` alanında işlenir; kaynak koduna, fixture’a veya uygulama loglarına eklenmez.

## Üretim ortamı notu

Uygulama işlevsel olarak yerel Docker akışında çalışır. Kurumsal canlı kullanımdan önce disk şifreleme, kullanıcı/rol yetkilendirmesi, yedekleme ve saklama-silme süreleri kurum tarafından ayrıca belirlenmelidir.
