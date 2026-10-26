# Implementation Plan: Mışıl Baby Dönüşüm (CRO), Freemium Sınırları & Satın Alma Psikolojisi Optimizasyonu

- **Tahmini Efor:** ~25-30 Dakika (Kodlama, UI Entegrasyonu & Yerel Doğrulama)
- **Kapasite Kullanımı:** Kalan bağlam limitinin yaklaşık %6-8'i

---

## 🎯 Netleştirilmiş Hedef & Kapsam (Refined Scope)
Mışıl Baby’nin yüksek indirme hacmini gerçek gelire (Trial ve VIP Abonelik) dönüştürmek amacıyla; kullanıcının stratejik geri bildirimleri doğrultusunda **fiyat sabitliği korunan**, **uygulamayı basit bir ses çalar yerine bir 'Bebek Uyku & Ağlama Mühendisliği Ekosistemi' olarak konumlandıran**, **ücretsiz ve VIP sınırları milimetrik olarak çizilmiş** derinlemesine bir dönüşüm sistemi kurulacaktır.

- **Hedef Proje:** `projects/mishil`
- **Etkilenen Katman:** `public/app.html` (Onboarding Adım 1–5, Paywall, Freemium Kapıları, VIP Modalları)
- **Kapsam Dışı Bırakılanlar:** Fiyat değişikliği yapılmayacak; gereksiz iptal uyarıları (Blinkist hatırlatma bildirimleri) iptal tetikleme riski nedeniyle tamamen plan dışı bırakılmıştır.

---

## 🏎️ 3 Ajanlı Görev Dağılımı (Tri-Agent Protocol)
- **Claude Şeridi (Mimari, Değer Konumlandırma & Algı):**
  - "Sadece Müzik Değil, Tam Ekosistem" paywall metin ve değer hiyerarşisi (MışılSpot™ Algoritması + Akustik DSP Ağlama Analizi + Mışıl Dadı™ 7/24 AI + 18 Stüdyo Mikseri).
  - Freemium sınırlarının matematiksel ve fonksiyonel ayrımı (Feature-Gating).
- **Codex Şeridi (Teknik İcra, Sürtünme Analizi & Testler):**
  - Adım 5 Paywall'da gecikmeli (2.5 sn) `skipOnboardingToApp()` bağlantısının bağlanması.
  - `requireActiveSubscription()` fonksiyonunun freemium matrisine göre güncellenmesi (Hangi fonksiyonların serbest geçeceği, hangilerinin `openVipRenewalModal()` açacağı).
  - Tıbbi feragatnamenin sürtünmesizleştirilmesi (`checked` otomatik onay ve buton kilidinin açılması).
- **Antigravity Şeridi (Tasarım, Güven Rozetleri, Mağaza Uyumu & Orkestrasyon):**
  - Apple Guideline 3.1.2(c) ve Google Play Answer 15748846 uyumluluğunun korunması (Reviewer bypass `MISIL-REV-9842` ve EULA bağlantıları).
  - VIP rozetlerinin ve dönüşüm tetikleyicilerinin modern Glassmorphic arayüzle giydirilmesi.

---

## 🛡️ Risk Seviyesi & Kademeli Doğrulama Kapısı
- **Seviye 2 (Orta Risk / Standart Modüller - Dual Check):**
  - Ödeme akışları ve onboarding yaşam döngüsü doğrudan etkilendiği için ikili denetim uygulanır.
  - Claude ekosistem değer metinlerini ve yasal uyumu denetler; Codex yerel depolama (`localStorage`) ve yetkilendirme kapılarını test eder.
  - Geliştirmeler yalnızca yerel ortamda kalır; yazılı insan onayı olmadan canlıya (`git push`) push edilmez.

---

## ⚠️ Kısıtlar ve Önleyici Tedbirler
1. **Fiyat Sabitleme Kuralı:** App Store ve Google Play'de tanımlı ₺149.99/ay ve ₺599.99/yıl fiyatları sabit kalır; fiyat karmaşası yaratılmaz.
2. **İptal Tetikleme Yasağı:** Kullanıcıya "Aboneliğiniz bitmek üzere, unutmayın iptal edin" şeklinde hatırlatmalar konulmayacak; düşük fiyatlı SaaS modellerinde bu tip bildirimler churn'ü gereksiz yere artırır.
3. **Canlıya Alma Yasağı:** Kullanıcı açıkça "canlıya al" demedikçe `git push origin main` çalıştırılmaz.
4. **Native Build Gereksizliği (Yeşil Durum):** Değişiklikler Webview (`public/app.html`) katmanında kalacağından yeni bir EAS build gerekmez.

---

## 🧭 1. ÜCRETSİZ ATLA DURUMUNDA HANGİ KISIMLAR ÜCRETSİZ, HANGİLERİ VIP OLACAK? (FREEMIUM MATRİSİ)

Kullanıcı Adım 5 Paywall ekranında *"Şimdilik Sınırlı Modda Devam Et"* dediğinde uygulama içine alınır. Bu durumda modüller arasındaki sınırlar şu şekilde kesin olarak belirlenmiştir:

| Modül / Özellik | Ücretsiz Sürüm (Free Tier) | VIP Sürüm (Abonelikli) | Neden Bu Şekilde Sınırlandırıldı? |
| :--- | :--- | :--- | :--- |
| **Bebek Profili & Yaş Hesabı** | 🟢 **Tam Açık:** Bebeğin adı, doğum tarihi, düzeltilmiş haftası ve rol hafızaya kaydedilir. | 🟢 **Tam Açık** | Ebeveynin uygulamaya bağlanması (Personalization Lock-in) için profil açık olmalıdır. |
| **MışılSpot™ Uyku Penceresi** | 🟢 **Bugünkü 1 Uyku Tahmini Açık:** Bebeğin sıradaki biyolojik uyku saati ve kalan dakikası gösterilir. | 🟢 **Sınırsız 7/24 Dinamik Takvim:** Gün boyu değişen tüm şekerleme ve gece uykusu pencereleri + 15 dk kala bildirim. | Huckleberry'nin dünyadaki 1 numaralı taktiği: Ebeveyne sıradaki uykuyu gösterip doğruluğu ispatlanır; günün kalanını ve bildirimleri VIP kilitler. |
| **Canlı Hilal Uyku Sayacı** | 🟢 **Açık (Temel Sayaç):** Hilal butonuna basarak uyku başlatılır, süre sayılır ve yerel günlüğe kaydedilir. | 🟢 **Gelişmiş Uyku Analizi:** Uyku verimliliği skoru, aşırı yorgunluk tespiti ve grafik trendleri. | Ebeveyn bebeğini uyuturken uygulamayı her gün açmalıdır (Daily Active User). Temel sayaç engellenirse ebeveyn başka sayaç indirir. |
| **Akustik Uyku Sesleri** | 🟡 **3 Temel Ses Açık (15 Dk Seans):** Anne Karnı/Rahim İçi, 432Hz Pembe Gürültü ve Klasik Ninni. | 🟢 **18 Stüdyo Sesi + Sınırsız Çalma:** Fön, Yağmur, Okyanus, Rüzgar, Süpürge, Araba vb. + Sabaha kadar kesintisiz döngü + Kilit ekranında arka planda çalma. | 3 sesle bebeğin sakinleştiği kanıtlanır; ancak sabaha kadar kesintisiz çalma ve zengin mikser kütüphanesi VIP'ye yönlendirir. |
| **Akustik Ağlama Analizi (DSP)** | 🔴 **Kilitli (VIP Özelliği):** Açılışta 5 saniyelik tanıtım demosu gösterilir, "Dinle ve Analiz Et"e basınca VIP Modal açılır. | 🟢 **Sınırsız Akustik Dinleme:** Librosa 13-bant MFCC & Spectral frekans analiziyle Açlık, Gaz, Yorgunluk ve Ağrı ayrımı. | Çok yüksek algılanan değere (Perceived Value) sahip donanım katmanı; doğrudan satın alma tetikleyicisidir. |
| **Mışıl Dadı™ 7/24 AI Koç** | 🔴 **Kilitli (VIP Özelliği):** Sekmeye basıldığında veya soru kutusu açıldığında VIP Modal açılır. | 🟢 **Sınırsız AI Soru-Cevap:** Bebeğin ayına, kilosuna ve uyku geçmişine göre kişiselleştirilmiş 7/24 rehberlik. | Gemini AI token maliyeti olan ve ebeveynin tüm sorularına yanıt veren amiral gemisi özellik. |
| **BabySteps™ Gelişim Atakları** | 🟡 **Temel Hafta Özeti:** Bebeğin o an hangi haftada olduğu ve atak durumunun adı görünür. | 🟢 **Derin Atak Rehberi:** Huysuzluk belirtileri, yeni kazanılacak motor beceriler ve atağı atlatma ebeveyn stratejileri. | Wonder Weeks kurgusu: Atağın geldiğini söyleyip panik/merak uyandırılır, nasıl çözüleceği VIP arkasında tutulur. |
| **Çoklu Ebeveyn / Aile Kodu** | 🔴 **Kilitli:** "Eşinle Eşitle" seçeneği VIP gerektirir. | 🟢 **Sınırsız Bulut Eşitleme:** Anne ve babanın telefonlarında eşzamanlı veri takibi. | Aile için ikinci telefonun eklenmesi net bir ödeme noktasıdır. |

---

## 💡 2. "AHA! MOMENT" (İLK DEĞER KANITI) NASIL KURULACAK? (DETAYLI DENEYİM TASARIMI)

Bir ebeveyn için "Aha!" anı sadece ses dinlemek değildir. Uykusuz bir anne/baba için gerçek dönüşüm şudur:
**"Bu uygulama benim bebeğimi anlıyor ve bana sihirli bir rehberlik sunuyor!"**

### İlk 60 Saniyedeki 3 Kademeli Değer Zirvesi:
1. **Kişiselleştirilmiş Sirkadiyen Şok (0-15. Saniye):**
   - Onboarding Adım 4'ten Adım 5'e geçerken ekranda 1.8 saniyelik bir analiz animasyonu çalışacak:
     `"Pediatrik Sirkadiyen Ritim Hesaplanıyor..."`
   - Adım 5 açıldığında: *"Mina için Mevcut Uyku Riski: Yüksek Aşırı Yorgunluk. Hedef: 45 dakikalık dalma süresini 12 dakikaya düşürmek."* Ebeveyn ilk kez veriye dayalı bir analizle karşılaşır.
2. **Uygulamaya Girildiği Anki Karşılama (15-30. Saniye):**
   - Kullanıcı sınırlı modla ana ekrana girdiğinde, Home ekranında bebeğin adı ve fotoğrafı/avatarı ile birlikte dev bir kart parlar:
     `"🌙 Mina İçin Sıradaki MışılSpot™ Penceresi: 14:20 (Kalan: 24 Dk). Bu saatte odayı karartıp Anne Karnı sesini açın."`
   - Ebeveyn saatine bakar ve şunu der: *"Evet, tam da bu saatlerde huysuzlanmaya başlıyordu!"* İşte güvenin kazanıldığı an burasıdır.
3. **Acil Yatıştırma Deneyimi (30-60. Saniye):**
   - Kullanıcı "Anne Karnı" sesine dokunduğunda 432Hz tıbbi frekanstaki stetoskopik kalp atışı ve rahim sıvısı sesi çalmaya başlar.
   - 15 dakikalık seans geri sayımı başlar: *"Mina'nın kalp ritmi dengeleniyor..."*

---

## 💰 3. DEĞER KONUMLANDIRMA & FİYAT ÇERÇEVELEME (PRICING FRAMING)

Fiyatlar değiştirilmeyecek; ancak uygulamanın algısı **"Müzik Uygulaması"** kalıbından tamamen koparılıp **"Tam Donanımlı Akıllı Bebek Bakım Asistanı"** seviyesine taşınacaktır.

### A. Fiyat Çerçevelemesi (No-Brainer Framing)
* **Mevcut Yanlış Algı:** *"Birkaç ninni dinlemek için ayda ₺149 verilir mi?"* (Kullanıcı Spotify ile kıyaslıyor).
* **Yeni Çerçeve:**
  * **Yıllık VIP (Öne Çıkarılan Plan):** ₺599.99/yıl ➔ **`Ayda Sadece ₺49.99`**
  * **Mikro-Bilişsel Kıyaslama:** *"Günde sadece ₺1.64 — Bir fincan çaydan daha ucuza; 7/24 AI Uyku Danışmanı, Akustik Ağlama Teşhisi ve Deliksiz Geceler."*
  * **Alternatif Maliyet Çıpası:** *"Özel Uyku Danışmanlığı: ₺3.500 - ₺7.500 / Ay | Mışıl Baby VIP: Ayda ₺49.99"*
* **Aylık Plan:** ₺149.99/ay ("Esnek, taahhütsüz seçenek" olarak yanında tutulur, yıllık planın değerini katlar).

### B. Paywall Değer Rozetleri (Müzik Değil, Ekosistem)
Adım 5 Paywall ve uygulama içi VIP pencerelerinde sadece sesler değil, 4 sütunlu ekosistem açıkça sergilenecektir:
1. `🧠 MışılSpot™ AI Sirkadiyen Takvim (Ağlamasız Uyku Saati)`
2. `🎙️ Librosa Nöral Ağlama Analizi (Açlık, Gaz, Uyku Teşhisi)`
3. `🤖 Mışıl Dadı™ 7/24 Pediatrik AI Uyku Koçu`
4. `🎧 18 Stüdyo Akustik Mikseri & Sabaha Kadar Kesintisiz Çalma`

---

## 🛠️ 4. TEKNİK İCRA PLANI (`public/app.html`)

### Adım 1: Adım 5 Paywall Ekranının Dönüştürülmesi
1. **Tıbbi Feragatname:** Checkbox varsayılan `checked` yapılır. Buton üzerindeki engel kaldırılır; yasal metin şık bir AAP rozetiyle buton altına bağlanır.
2. **Yıllık Planın Varsayılan Yapılması:** `onboarding-plan-yearly` seçili (`selected`) hale getirilir; `Ayda Sadece ₺49.99` tasarruf rozeti parlatılır.
3. **Ekosistem Özellik Kartları:** 4'lü fonksiyon matrisi eklenir (MışılSpot, Ağlama Analizi, Mışıl Dadı, 18 Ses).
4. **2.5 Saniye Gecikmeli "Sınırlı Modda Devam Et" Bağlantısı:**
   - Butonun altına soluk, minimal bir link:
     ```html
     <div id="onboarding-skip-wrap" style="text-align: center; margin-top: 12px; opacity: 0; transition: opacity 0.6s ease;">
       <button type="button" onclick="skipOnboardingToApp()" style="background: none; border: none; color: var(--text-muted); font-size: 11px; cursor: pointer; text-decoration: underline;">
         Şimdilik Sınırlı Modda Keşfet ➔
       </button>
     </div>
     ```
   - Adım 5 açıldığında `setTimeout(() => skipWrap.style.opacity = '0.7', 2500)` ile dürtüsel kaçış engellenir.

### Adım 2: `requireActiveSubscription()` ve Freemium Kapılarının Ayrılması
Mevcut kodda her şeyi kilitleyen satırlar freemium kuralına göre güncellenir:
1. **Canlı Uyku Hilali (`toggleLiveSleep`):** Temel sayaç ücretsiz kullanıcıya açılır.
2. **Ses Listesi (`renderSoundsList` / `togglePlayTrack`):** İlk 3 ses (`anne_karni`, `pembe_gurultu`, `ninni_brahms`) ücretsiz çalabilir; diğer 15 ses tıklandığında `openVipRenewalModal()` açılır.
3. **Mışıl Dadı (`view-coach`) ve Ağlama Analizi:** Tıklandığında değer odaklı `openVipRenewalModal()` açılır.

### Adım 3: Yerel Test & Doğrulama
1. Sıfır hafıza ile onboarding başlatılıp Adım 1'den 5'e test edilecek.
2. "Sınırlı Modda Keşfet" tıklandığında profilin başarıyla kaydedilip Home ekranına geçtiği doğrulanacak.
3. Home ekranında SweetSpot'un çalıştığı, hilal sayacının uyku saydığı, ilk 3 sesin çaldığı teyit edilecek.
4. Ağlama Analizine veya Mışıl Dadı'ya tıklandığında VIP modalın doğru açıldığı ve fiyatların doğru göründüğü kontrol edilecek.
