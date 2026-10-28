# Implementation Plan - Meta Reklam Görselleri ve Metinlerinin Güncellenmesi (Çift Mağaza: App Store & Google Play)

**Tahmini Efor:** ~15-20 Dakika  
**Tahmini Kapasite Kullanımı:** %3 - %4

---

### 🎯 Netleştirilmiş Hedef & Kapsam (Refined Prompt)
- **Hedef Proje:** `projects/mishil` (Mışıl Baby)
- **Hedef Modüller & Varlıklar:**
  1. `projects/mishil/kullanici/reklamlar/` dizinindeki Meta reklam görsellerinin temizliği: Kullanılmayan 3 dosyanın (`01_Misil_Ses_Mikseri_Reklam.jpg`, `02_Misil_SweetSpot_Uyku_Penceresi_Reklam.jpg`, `03_Misil_Aglama_Analizi_Atak_Haftasi_Reklam.jpg`) silinmesi; yalnızca "Gercek" adını taşıyan 3 ana reklam görselinin tutulması.
  2. Tutulan 3 "Gerçek" görseldeki (`01_Misil_Gercek_App_MisilSpot_Uyku_Sayaci.jpg`, `02_Misil_Gercek_App_Aglama_Analizi.jpg`, `03_Misil_Gercek_App_18_Studyo_Sesleri.jpg`) tekil **"Download on the App Store"** rozetinin yerine, Android Google Play yayınımız da canlıda olduğu için **App Store + Google Play (Çift Mağaza Rozeti)** yerleştirilmesi.
  3. Metinlerdeki tek taraflı iOS referanslarının ("iOS için indir", "Yalnızca iOS", "App Store üzerinden indirin" vb.) taranarak hem iOS hem Android'i kapsayacak çift mağaza formatına güncellenmesi (`INSTAGRAM_KILAVUZU_VE_METINLERI.md`, `preview_bio.html`, post karusel açıklamaları).

### 🏎️ Ajan Uzmanlık Şeritleri ve Görev Dağılımı (Tri-Agent Roles)
- **Claude Şeridi:** Reklam metinleri ve CTA stratejisinde dönüşüm optimizasyonu, tek taraflı platform kısıtlarının kaldırılması, marka anayasasına uygun çift mağaza metin revizyonu.
- **Codex Şeridi:** Yüksek kaliteli görsel işleme ve kompozitleme scriptinin (`scripts/update_meta_ad_badges.py` - Pillow / OpenCV) kodlanması; 1024x1024 kayıpsız formatta orijinal arka plan gölge ve ışık dengesini bozmadan App Store & Google Play rozetlerinin piksel seviyesinde yerleştirilmesi.
- **Antigravity Şeridi (Orkestrasyon, UI & Varlık Yönetimi):**
  - Dosya temizliğinin icrası (kullanılmayan 3 dosyanın güvenle kaldırılması).
  - Görsel rozet güncellemelerinin yerel ortamda üretilip teyit edilmesi.
  - İlgili dokümantasyonların ve metin kılavuzlarının senkronize edilmesi.

### 🛡️ Risk Seviyesi & Kademeli Doğrulama (Tiered Review Gate)
- **Risk Seviyesi:** **Seviye 1 (Düşük Risk / Rutin Pazarlama & Görsel Varlık Revizyonu - Fast Lane)**
- Core uygulama mimarisine veya native koda dokunulmaz. Yerel görsel işleme ve markdown/kılavuz metin revizyonudur. Görseller üretildikten sonra yerel görsel önizleme aracıyla piksel kalitesi doğrulanacaktır.

### ⚠️ Kısıtlar ve Önleyici Tedbirler
- Yalnızca "Gercek" etiketli 3 dosya korunacak, diğerleri temizlenecektir.
- Orijinal mockupların (iPhone ekranındaki arayüzün) netliği bozulmayacak, yalnızca alt rozet bandı profesyonel çift rozet (Apple + Google Play) olarak yenilenecektir.
- Canlı ortama izinsiz push yapılmayacak, tüm çalışmalar yerel ortamda tamamlanıp kullanıcı onayına sunulacaktır.

---

### 1. Ajan Uzmanlık Şeritleri ve Görev Dağılımı (Tri-Agent Roles)
- **Claude Şeridi:** Metin revizyonu, CTA dili ve reklam hedefleme stratejisi denetimi.
- **Codex Şeridi:** Python PIL ile piksel hassasiyetinde çift rozet yerleştirme scripti.
- **Antigravity Şeridi:** Orkestrasyon, dosya temizliği ve görsel önizleme.

---

### 2. Aktarım ve İcra Yöntemi (Execution Strategy)
1. **Adım 1 - Dosya Temizliği:** `projects/mishil/kullanici/reklamlar/` altındaki kullanılmayan 3 dosya silinecek, yalnızca 3 "Gerçek" görsel bırakılacak.
2. **Adım 2 - Çift Rozet Tasarımı & Kompozit Scripti:**
   - Resmi App Store ve Google Play rozetleri vektörel/yüksek çözünürlüklü olarak hazırlanacak.
   - 3 görselin altındaki eski tekli rozet alanı arka plan dokusuna uygun olarak temizlenecek ve yan yana ortalanmış App Store + Google Play rozetleri yerleştirilecek.
3. **Adım 3 - Reklam & Tanıtım Metinlerinin Güncellenmesi:**
   - `INSTAGRAM_KILAVUZU_VE_METINLERI.md`: Bio, post ve Meta Ads filtreleri güncellenecek (Cihaz filtresi: iOS + Android; CTA: App Store & Google Play).
   - `post_01_uyku_pencereleri_karusel.md` ve `post_03_kucaktan_yataga_gecis.md` içerisindeki tekil App Store bağlantıları güncellenecek.
   - `public/preview_bio.html` içerisindeki "iPhone ve iPad için ücretsiz" ifadesi "iOS ve Android için ücretsiz" olarak revize edilecek.

---

### 3. Kademeli Çapraz Doğrulama Kapısı (Tiered Review Gate)
- **Seviye 1 (Rutin Fast Lane):** Görsel kompozitleri ve metin güncellemeleri yerel ortamda üretilip doğrulanacak. Harici token/CLI israfı yapılmayacak.

---

### 4. Limit/Kota Aşımı Durum Planı (Fallback Protocol)
- Tüm adımlar yerel ortamda Python Pillow ve metin düzenleme araçlarıyla yürütülecektir; harici kota riski bulunmamaktadır.

---

## Yapılacak İşler Listesi (Proposed Changes)

#### 1. `kullanici/reklamlar/` Klasör Temizliği
- [ ] Silinecekler: `01_Misil_Ses_Mikseri_Reklam.jpg`, `02_Misil_SweetSpot_Uyku_Penceresi_Reklam.jpg`, `03_Misil_Aglama_Analizi_Atak_Haftasi_Reklam.jpg`
- [ ] Tutulacaklar: `01_Misil_Gercek_App_MisilSpot_Uyku_Sayaci.jpg`, `02_Misil_Gercek_App_Aglama_Analizi.jpg`, `03_Misil_Gercek_App_18_Studyo_Sesleri.jpg`

#### 2. Çift Rozet (App Store & Google Play) Kompozitleme
- [ ] `01_Misil_Gercek_App_MisilSpot_Uyku_Sayaci.jpg` rozet bandı güncellemesi
- [ ] `02_Misil_Gercek_App_Aglama_Analizi.jpg` rozet bandı güncellemesi
- [ ] `03_Misil_Gercek_App_18_Studyo_Sesleri.jpg` rozet bandı güncellemesi

#### 3. Metin & Kılavuz Revizyonları
- [ ] `INSTAGRAM_KILAVUZU_VE_METINLERI.md`: "Yalnızca iOS" cihaz filtresi ve tekli App Store indirme çağrıları çift mağaza olarak güncellenecek.
- [ ] `public/preview_bio.html`: "iPhone ve iPad için" ibaresi güncellenecek.
- [ ] İlgili post karusel metinlerindeki mağaza bağlantıları güncellenecek.

---

## Doğrulama Planı (Verification Plan)
- [ ] 3 güncellenmiş reklam görseli `view_file` ile açılarak rozetlerin netliği, simetrisi ve okunabilirliği gözle kontrol edilecek.
- [ ] Metin dosyalarında grep yapılarak tek taraflı "iOS için" veya "Yalnızca iOS" kalıntısı olup olmadığı teyit edilecek.
