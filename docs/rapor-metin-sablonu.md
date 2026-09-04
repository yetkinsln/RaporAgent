# Rapor metin şablonu

Bu şablon içerik sözleşmesidir. Kurumun gerçek `.docx` şablonu temin edildiğinde yer tutucular Word dosyasına taşınmalıdır.

```text
SAYI: 6153143-101.00-26/{{sayi_devami}}              TARİH: {{rapor_tarihi}}
KONU: {{hasta_ad_soyad}}

                              R A P O R

İLGİ: a) {{ust_yazi_makami}}'nin {{ust_yazi_tarihi}} tarih ve
         {{ust_yazi_sayisi}} sayılı yazısı.
      b) {{genel_rapor_kurumu}}'nun {{genel_rapor_tarihi}} tarih ve
         {{genel_rapor_sayisi}} sayılı genel adli muayene raporu.

İlgi (a) yazı ile başvuran {{hasta_ad_soyad}} hakkında,
{{olay_ifadesi}} nedeniyle {{istenen_hususlar}} hususlarında rapor
düzenlenmesi istenmektedir.

1. {{hasta_ad_soyad}} adına düzenlenen ilgi (b) formunda;
   {{genel_adli_muayene_ozeti}} kayıtlıdır.

2. {{hasta_ad_soyad}} adına {{epikriz_kurumu}} tarafından düzenlenen
   {{epikriz_tarihi}} tarih ve {{protokol_no}} protokol numaralı belgede;
   {{epikriz_ozeti}} kayıtlıdır.

3. {{hasta_ad_soyad}} hakkında {{muayene_tarihi}} tarihinde saat
   {{muayene_saati}}'te Adli Tıp Anabilim Dalımızda yapılan muayenede;
   öyküsünde {{muayene_oykusu}} ifade ettiği, yapılan muayenesinde
   {{muayene_bulgulari}} tespit edilmiştir.

SONUÇ: İlgili olay nedeniyle Adli Tıp Anabilim Dalımıza gönderilen,
{{tckn}} T.C. kimlik numaralı, {{dogum_tarihi}} doğumlu
{{hasta_ad_soyad}} hakkında; genel adli muayene raporu ve sunulan tıbbi
evrakın incelenmesi ile muayeneden elde edilen ve yukarıda kaydedilen
bilgi ve bulgulara göre, şahısta mevcut {{yaralanma_ifadesi}} nedeniyle;

1. Şahsın yaşamını {{hayati_tehlike_ifadesi}},
2. Yaralanmasının basit tıbbi müdahale ile giderilebilecek derecede
   hafif nitelikte {{btm_ifadesi}} kanaatlerimizi bildirir rapordur.

EKİ:
{{ek_listesi}}
```

## Zorunlu notlar

- `{{sayi_devami}}` için üretim kuralı kurumdan alınmadan otomatik değer verme.
- `{{hayati_tehlike_ifadesi}}` yalnızca onaylı `TEHLİKEYE SOKTUĞU` veya `TEHLİKEYE SOKMADIĞI` değerlerinden gelmelidir.
- `{{btm_ifadesi}}` yalnızca onaylı `OLDUĞU` veya `OLMADIĞI` değerlerinden gelmelidir.
- Belge türü sunulmadığında ilgili maddenin kaldırılacağı mı yoksa resmi bir “sunulmadı” ifadesi mi kullanılacağı kurum tarafından belirlenmelidir.
- Cümleler gerçek kurum örnekleriyle dilbilgisi ve terminoloji açısından yetkili kullanıcı tarafından son kez onaylanmalıdır.
