# Changelog - Mışıl Baby

Tüm önemli değişiklikler bu dosyada belgelenecektir.

## [4.5.0] - 2026-08-23
### 🌟 Tier-1 Lüks Landing Page & Mağaza İndirme Dönüşümü
- **🛡️ Ücretsiz Doğrudan Erişim Koruması:** Açık web sürümü kaldırılarak tüm web trafiği App Store ve Google Play indirmelerine yönlendirildi.
- **🎨 21st.dev Dark Obsidian & Gold Landing Page:** Titanyum mockup, canlı nefes alan SweetSpot animasyonu ve modern bento kartları ile resmi tanıtım sayfası (`public/index.html` & `web-preview/index.html`) inşa edildi.
- **🎧 15 Sn Akustik Ses Örnekleyici (Web Audio Synthesizer):** 432 Hz şifalı frekansta 15 saniyelik ses önizlemesi ve süre sonunda mobil uygulamayı indirme yönlendirmesi entegre edildi.
- **🔗 Kök URL (`GET /`) Entegrasyonu:** Backend kök rotasına doğrudan landing page bağlandı.

## [4.4.0] - 2026-08-23
### 🚀 Google Play Store Lansman & Levitas Yayıncılık Paketi
- **🏢 Levitas Kimliği & Kurumsal Yayıncı Entegrasyonu:** Uygulama kimliği `com.levitas.misilbaby` (Android) ve `com.levitas.misilbaby` (iOS) olarak güncellendi; `app.config.ts` dosyası Levitas Enterprise standartlarına uyarlandı.
- **🎨 HD Mağaza Varlıkları (Store Assets):** Google Play Store gereksinimlerine tam uyumlu 512x512 uygulama simgesi (`icon_512.png`), 1024x500 vitrin afişi (`feature_graphic_1024x500.png`) ve 4 adet 1080x1920 dikey ekran görüntüsü (Ağlama Analizi, Ses Mikseri, Gece Lambası, Uyku Rehberi) üretildi.
- **📝 Google Play ASO & Mağaza Dokümanı:** 30 karakterlik uygulama adı, 80 karakterlik kısa açıklama ve 4000 karakterlik ASO optimizasyonlu tam açıklama `STORE_LISTING.md` olarak hazırlandı.
- **🔒 Gizlilik Politikası & Aile Güvenliği (COPPA/KVKK):** Çocuk ve bebek kategorisi için Google Play onaylı `PRIVACY_POLICY.md` dokümantasyonu tamamlandı.

## [4.3.1] - 2026-08-23
### 🌸 Uyumluluk, Güven Mimarisi, Fiyatlandırma & Ebeveyn Dili (Task Sprint Tamamlandı)
- **🩺 Tıbbi Feragatname & AAP Güvenlik Onayı (TASK-002):** Onboarding anketinin sonuna ve ilk girişe zorunlu tıbbi bilgilendirme ve açık rıza onay kutusu entegre edildi. Onay verilmeden ana ekrana geçiş kilitlendi ve onay anı (`medical_disclaimer_accepted_at`) kaydedildi.
- **👑 3'lü Plan Seçici & Apple Guideline 3.1.2 Uyumu (TASK-001 & TASK-006):** Yıllık (3 Gün Ücretsiz Deneme • ₺599.99/yıl), Aylık (₺149.99/ay) ve Ömür Boyu Tek Seferlik (₺1.499.99) plan seçicisi entegre edildi. Dinamik deneme bitiş tarihi (`Bugün + 3 Gün`) ve tek tıkla App Store abonelik iptal yönlendirmesi eklendi.
- **🎵 Ses Kütüphanesi Filtreleme İzolasyonu & 18 Parça Garantisi (TASK-003):** `.cat-chip` seçicisi `#view-sounds` içine scoped yapılarak filtre çakışması giderildi; 18 stüdyo parçasının (5 Ninni, 4 Anne Karnı, 5 Pışpış, 4 Doğa) kusursuz listelenmesi güvenceye alındı.
- **🔒 Akustik Ağlama Analizi RAM Sıfır-Depolama Şeffaflığı (TASK-004):** Mikrofona basılmadan önce görünür şeffaf bilgilendirme rozeti eklendi (Ses kaydı diske yazılmaz; 5 sn sunucu RAM analizinden sonra derhal kalıcı olarak silinir).
- **🌸 Anne-Baba Dostu Sıcak Sürüm Notları (TASK-005):** Geliştirici terimleri yerine anne ve babalara hitap eden anlaşılır ve şefkatli bir dil uygulandı.

## [2.8.0] - 2026-08-23
### 🌙 Segmented Focus Hub, Klinik Dinamik Gelişim Algoritması & 5-Core Analiz Merkezi
- **🥇 Segmented Focus Hub (2 Modlu Ana Sayfa):** Dikey yığın tamamen kaldırılarak üstte tek tıkla değişen `[ 🌙 SweetSpot & Uyut ]` (dingin nefes alan ay ve tek butonla uyutma) ve `[ ⏱️ Bugünkü Uykular ]` (tamamlanan uyku seansları ve bütçe) segment kontrolü entegre edildi.
- **🧠 Dinamik Klinik Gelişim Skoru Motoru:** Statik puan yerine gerçek matematiksel formül entegre edildi: $\text{Skor} = (S_{\text{uyku}} \times 0.40) + (S_{\text{sweetspot}} \times 0.35) + (S_{\text{atak}} \times 0.25)$.
- **📊 5-Core Akıllı Navigasyon & Zengin Analiz Sekmesi (`view-analytics`):** Menü kalabalığı 5 temel sekmeye (`SweetSpot`, `Analiz`, `Mışıl Dadı`, `Sesler`, `Ayarlar`) indirgendi. Yeni Analiz sekmesinde haftalık uyku çubuk grafiği (Bento Chart) ve filtrelenebilir dikey rutin akışı sunuldu.
- **🎙️ Mışıl Dadı İçine Entegre Akustik Ağlama Analizi:** Menüyü şişirmemek adına Ağlama Analizi doğrudan Mışıl Dadı'nın içine akıllı modal kart olarak bağlandı.
- **🔄 Canlı Uyku Oturumu & Otomatik SweetSpot Öteleme:** "Bebek Uyandı" denildiği an uyku süresi günlüğe kaydedilir ve sıradaki SweetSpot saati bebeğin uyandığı dakikanın üzerine uyanıklık penceresi (90 dk) eklenerek anında canlı yeniden hesaplanır.

## [2.7.0] - 2026-08-23
### 🌙 UI / UX & Tasarım Mühendisliği Yükseltmesi (Dünya Standartları)
- **✨ Canlı Uyku Modu & Dinamik Mor Nefes Alan Ay Dönüşümü:** "Uyku Başlat" aksiyonu ile Ay göstergesi uyanıklık sayacından canlı uyku sayacına (`isSleeping = true`, mor/lila nefes aurası) morph eder ve geçen uyku süresini canlı sayar.
- **⏱️ Sakinleştirici Sesler Mini-Bar Uyku Zamanlayıcısı:** Alt çalar barına `15 dk / 30 dk / 45 dk / 60 dk / Kesintisiz` geri sayım sayaç hapları entegre edildi.
- **📊 Rutinler Dikey Bento Zaman Çizelgesi & Günlük İstatistik Widgetları:** Düz liste yerine dikey bağlantı çizgili, saat rozetli Bento akışı ve sayfa başında toplam uyku, beslenme ml ve bez sayaçları eklendi.
- **📱 Dokunsal Haptik Ergonomi (`expo-haptics`):** Hızlı rutin butonları, mikrofon kaydı, ses seçimi ve tema geçişleri için web ve mobil güvenli haptik mikro-titreşimler entegre edildi.
- **⚙️ Sadeleştirilmiş Modüler Ayarlar & Sürüm/Changelog Takipçisi:** Ayarlar sekmesi 4 net gruba ayrıldı (Bebek & Aile, Görünüm, Abonelik, Sürüm Notları) ve `VersionChangelogModal` ile `v4.3.0` sürüm geçmişi erişilebilir kılındı.

## [2.6.1] - 2026-08-23
### 🎯 Mışıl Dadı AI: Doğrudan Odak, Bağlam İzolasyonu & Hap Bilgi Mimarisi
- **Gevezelik ve Ezber Şablonların Temizlenmesi:** "Derin nefes al", "omuzlarını bırak" gibi tekrarlayan edebi teselliler ve her soruya zorla dayatılan 3 adımlı genel şablonlar kaldırıldı.
- **Doğrudan Soruya Odaklanma (55-100 Kelime):** İlk cümlede doğrudan soruya cevap veren, en fazla 2 kısa paragraf veya 2-3 hap maddeden oluşan net klinik format uygulandı.
- **Bağlam İzolasyonu:** Bebeğin ayı ve sıçrama durumu arka plan referansına çekildi; oda sıcaklığı veya beslenme sorulduğunda zorla 4. Ay Regresyonu dersi anlatılması engellendi.
- **Sıcaklık (Temperature) Optimizasyonu:** Model sıcaklığı `0.40` seviyesine çekilerek sapmalar ve laf uzatmaları sıfırlandı.

## [2.6.0] - 2026-08-23
### ⚡ Gerçek Zamanlı Kelime Akışı (SSE Streaming) & Sıfır Kesilme Mimarisi
- **Mışıl Dadı Real-Time Streaming (`POST /api/v1/coach/stream`):** Google Gemini 3.5 Flash `:streamGenerateContent` SSE motoru ile kelimeler 300ms içinde ekrana canlı canlı akıtılır.
- **Sıfır Token Sınırı & Sıfır Kesilme:** Modelin klinik muhakeme derinliği kısıtlanmadan, cevaplar harf harf akıtılarak yarıda kesilme riski %100 ortadan kaldırıldı.
- **Modern `ReadableStream` İstemcisi:** Frontend üzerinde `ReadableStream` okuyucusu ve anlık markdown formatlayıcı ile akıcı canlı sohbet deneyimi sunuldu.

## [2.5.0] - 2026-08-23
### 🐘 Canlı PostgreSQL Veritabanı Tam Senkronizasyonu & Function-Bun Realtime WebSocket Relay
- **%100 Canlı PostgreSQL Veri Kalıcılığı:** Bebek profili (`POST /api/v1/baby/profile`), uyku oturumları (`POST /api/v1/sleep/log`), gelişim günlükleri ve Mışıl Dadı sohbet geçmişi doğrudan Railway canlı PostgreSQL veritabanına bağlandı.
- **⚡ Function-Bun Gerçek Zamanlı Ebeveyn & Dadı Senkronizasyonu (`services/function_bun`):** Yüksek hızlı Bun runtime WebSocket motoru ile anne bebeği uyuttuğunda veya dadı mamasını verdiğinde diğer tüm bağlı aile üyelerinin ekranı anında titreşerek canlı güncellenir (`SLEEP_STARTED`, `SLEEP_COMPLETED`, `LEAP_OVERRIDE`).
- **Uygulama İçi Canlı Veri Akışı:** `localStorage` sadece offline yedek katmanına çekilerek birincil veri kaynağı canlı PostgreSQL yapıldı.

## [2.4.0] - 2026-08-23
### 👨‍👩‍👧 Aile & Dadı Senkronizasyonu, Wonder Weeks % İlerleme Çubukları & Erken Atak Modu
- **Dinamik Wonder Weeks (10 Zihinsel Sıçrama) Motoru:** Bebeğin doğum tarihine gün gün duyarlı çalışan; her sıçramada dinamik **% dolum çubuğu**, fırtına zirvesi ve yaklaşan sıçramalara gün geri sayımı entegre edildi.
- **⚡ Manuel Erken Atak Başlatma Modu (Early Leap Override):** Bebek takvimden 1-2 hafta önce huysuzluk gösterdiğinde ebeveynin/dadının tek tıkla atağı manuel başlatması sağlandı. Bu modda SweetSpot uyanıklık penceresi otomatik olarak 15 dakika kısaltılarak aşırı yorgunluk kalkanı devreye girer.
- **Ana Ekran Gelişim Skoru Bento Kartı (%84):** SweetSpot ekranına bebeğin gelişim ayına, sirkadiyen dengesine ve aktif atağına göre hesaplanan canlı Gelişim Skoru eklendi.
- **👨‍👩‍👧 Aile & Dadı Paylaşımı (Co-Parenting Cloud Sync):** 6 haneli aile paylaşım kodu (`MSL782`), Anne 👩 / Baba 👨 / Dadı 👵 rol yönetimi ve Mışıl Dadı'nın kimliğe özel hitap etmesi sağlandı.

## [2.3.0] - 2026-08-23
### 🎙️ 18 Gerçek Stüdyo & Alan Kaydı Ses Kütüphanesi ve Canlı Gemini 3.5 Entegrasyonu
- **100% Gerçek Stüdyo & Alan Kaydı Parçalar:** Sentetik ve yapay sinüs frekansları tamamen kaldırılarak; gerçek akustik mekanik müzik kutuları, triküspit stetoskop kalp atışı (Lub-Dub), hidrofon su altı anne karnı, gerçek insan pışpışlaması (5S Shush), pencere yağmuru ve okyanus dalgaları gibi **24+ MB boyutunda gerçek stüdyo kayıtları** entegre edildi.
- **Canlı Google Gemini 3.5 Flash Motoru:** Mışıl Dadı'nın standart kalıplara düşme sorunu kökten çözüldü; API anahtarı otomatik yüklenerek canlı yapay zeka çıkarımı sağlandı.
- **`API_BASE` Akıllı İstemci Yönlendirmesi:** `file:///` veya web protokolünden bağımsız olarak tüm isteklerin canlı backend API'sine ulaşması sağlandı.

## [2.2.0] - 2026-08-23
### 👵 Mışıl Dadı (4 Katmanlı Gemini LLM) & 18 Parçalı Zengin Ses Kütüphanesi
- **Mışıl Dadı Kimliği & Şefkatli Uzmanlık:** Soğuk "AI Koçu" tabiri kaldırılarak sıcak, şefkatli ve deneyimli **"Mışıl Dadı"** kimliğine geçildi.
- **4 Katmanlı Kesintisiz AI Mimarisi (`POST /api/v1/coach/chat`):**
  - Katman 1: Google Gemini 2.5 Flash / 3.6 Pro API
  - Katman 2: Google Gemini 1.5 Flash API (Yüksek hızlı yedek)
  - Katman 3: Pollinations AI Free LLM Fallback (Dış açık kaynak fallback)
  - Katman 4: Klinik Sirkadiyen Kural Motoru (Sıfır çökme & offline güvencesi)
- **Sıfır Çirkin Scrollbar & Kusursuz Mobil Yerleşim:** Ekrana sığmayan sohbet kutusu `flex: 1; min-height: 0;` ile tam ekrana oturtuldu; tarayıcının standart scrollbar'ı gizlendi (`scrollbar-width: none;`).
- **18 Stüdyo Master Parçalı Ses Kütüphanesi:**
  - 🎹 Ninniler (Brahms, Ayışığı, Mozart 432Hz, Celesta, Kadife Gitar)
  - 🤰 Anne Karnı & Nabız (60 BPM Tok Kalp, Amniyotik Sıvı, Plasenta, Sakin Nefes)
  - 💨 Gürültü & Pışpış (5S Dr. Karp Pışpış, 432Hz Pembe, Kahverengi Kolik Kalkanı, Fön Makinesi, Vantilatör)
  - 🌿 Doğa Sesleri (Orman Şırıltısı & Kuşlar, Gece Yağmuru, Okyanus Dalgaları, Cırcır Böcekleri)
- **Anlık Canlı Arama & 4 Kategori Filtresi:** Başlık, açıklama ve kategori bazında harf harf filtreleme motoru entegre edildi.

## [2.1.0] - 2026-08-23
### 👑 Mışıl Baby: Tam Kapsamlı Premium SaaS & SweetSpot® Dönüşümü
- **Marka & Kimlik Rebranding (Mışıl Baby):** "Mishil" hibrit yazılışı kaldırılarak, kültürel hafızadaki en sıcak ve doğal Türkçe marka olan **"Mışıl Baby"** tam olarak entegre edildi.
- **5 Adımlı İnteraktif Onboarding Teşhis Testi:** Bebeğin ayına, uykuya direnç süresine, gece uyanma sıklığına ve ebeveynin çaresiz kaldığı alana göre dinamik teşhis anketi kuruldu.
- **Kişiselleştirilmiş Uyku Skoru & Paywall Raporu:** Bebeğe özel Uyku Sağlığı Skoru (%38), aşırı yorgunluk riski ve 7 günlük hedef içeren yüksek dönüşümlü satış ekranı bağlandı.
- **SweetSpot® Biyolojik Uyku Saati Tahmincisi:** Bebeğin ayına ve sirkadiyen uyanıklık penceresine göre günün bir sonraki en ideal uyku dakikasını hesaplayan motor devreye alındı.
- **7/24 Mışıl AI Pediatrik Uyku Koçu:** Bebeğin yaşını ve verilerini hafızasında tutan, gece bölünmelerinde hızlı tavsiyeler sunan interaktif AI danışmanı entegre edildi.
- **Wonder Weeks (Gelişim Atakları) & 4. Ay Regresyonu Radarı:** 10 büyük zihinsel sıçrama haftası ve huysuzluk takvimi arayüze eklendi.

## [2.0.0] - 2026-08-23
### 🎨 Major UI/UX Devrimi (21st.dev Design Engineering & Glassmorphism Edition)
- **OKLCH Dinamik Işık Auraları (`lp-glow-pulse`):** Uygulama arka planına derinlik katan çok katmanlı radyal aurora ışık auraları entegre edildi.
- **Bento Grid Mizanpajı & Spotlight Takipçisi:** Ana sayfa kartları asimetrik Bento Grid düzenine geçirildi; her karta dokunma/fare hareketinde parlayan radyal ışık (Spotlight) kazandırıldı.
- **Animated Border Beam (Dönen Konik Işık Huzmesi):** Canlı uyku takibinde (Hilal) ve aktif modlarda dönen konik ışık kenarlığı devreye alındı.
- **Blur-to-Focus Geçiş Fiziği (`lpHeroIn`):** Sekme geçişleri ve açılır modallara 21st.dev standardında pürüzsüz `blur(10px) -> blur(0)` yay fiziği eklendi.
- **Spring Physics Butonlar & Glassmorphic Dock:** Alt menü barı ve butonlara dokunmatik mikromekanik yay tepkisi uygulandı.

## [1.9.0] - 2026-08-23
### Added & Upgraded (Canlı Mikrofon Ağlama Analizi, Kapsamlı Ayarlar & İnteraktif Rutin Modalı)
- **Gerçek Mikrofon & Web Audio MediaRecorder Kayıt Motoru:** `navigator.mediaDevices.getUserMedia` ile 5 saniyelik canlı ses dalgası görselleştiricisi ve ses kaydı entegre edildi.
- **FastAPI Canlı API Entegrasyonu (`POST /api/v1/cry/analyze`):** Kaydedilen gerçek ses blob'u veya cihazdan yüklenen dosya FastAPI backend'ine gönderilerek Librosa 13 MFCC / FFT analiziyle canlı olasılık dağılımı (Yorgunluk, Açlık, Kolik) hesaplanır.
- **Kapsamlı Ayarlar (Settings) Sekmesi:**
  - Bebek Profili (Ad, Doğum Tarihi seçimi, otomatik ay ve gelişim atağı (Leap) hesaplayıcı).
  - Akıllı Bildirim & Uyku Alarmı Tercihleri (Toggle switch'ler).
  - Ebeveyn & Bakıcı Davet Kodu Üreticisi (`MISHIL-8492`).
  - Apple 3.1.1 Satın Alımları Geri Yükle ve Apple 5.1.1 Hesap/Veri Silme modalları.
- **İnteraktif Manuel Rutin Ekleme Modalı:** Beslenme (ml), Uyku (dk), Bez ve İlaç/Not kayıtları için modal form eklendi.

## [1.8.0] - 2026-08-23
### Added & Mastered (Gerçek Akustik Müzik Kutusu, Stetoskop Nabzı & 2.5s Cosine Crossfade Loop)
- **Akustik Fiziksel Modelleme & Stüdyo Tınıları:** Sentetik matematiksel sinüzoidler yerine ahşap rezonanslı narin çan tokmakları, canlı kuyruklu piyano harmonikleri ve kardiyoloji stetoskop çift vuruşlu (S1/S2) tok nabız modellerine geçildi.
- **2.5 Saniyelik Dikişsiz Kosinüs Geçiş Zarfı (Seamless Cosine Crossfade Loop):** Parça başa sardığında oluşan ani klik ve takılmalar 2.5 saniyelik dikişsiz örtüşme zarfıyla %100 sıfırlandı.
- **-14 LUFS Pik ve Dinamik Seviyeleme:** Kulaklık ve hoparlörlerde distorsiyon (clipping) oluşmaması için yumuşak pik sınırlayıcı (tanh soft limiter) uygulandı.

## [1.7.0] - 2026-08-23
### Added (Huckleberry & Napper Benchmark UI/UX İyileştirmeleri & Tek Dokunuş Uyku Sayacı)
- **Tek Dokunuşlu Canlı Uyku Sayacı (One-Tap Live Sleep Tracker):** Hilal göstergesi ve altındaki butona basıldığında uyku modu aktive edilerek geçen süreyi saniye bazında sayan `is_sleeping` canlı sayacı entegre edildi.
- **Dinamik Uyku Sonlandırma & Otomatik Rutin Girişi:** "Bebek Uyandı" tıklandığında geçen toplam süre otomatik hesaplanarak Rutin Günlüğü'ne uyku kaydı olarak eklenir ve bebeğin uyanıklık penceresi (wake window) adaptif olarak yeniden hesaplanır.
- **Görsel Hilal Aura Değişimi:** Uyku modunda hilal sıcak sarıdan gece mavisi aurasına (`#74B9FF`) geçerek ebeveyne loş ışıkta dingin geri bildirim sunar.

## [1.6.1] - 2026-08-23
### Added & Cleaned (Melodik Kristal Uyku Sesleri & Railway Tek Kart Sadeleştirmesi)
- **Railway Servis Sadeleştirmesi (Tek Çerçeve):** Atıl durumdaki `inspiring-enthusiasm` servisi Railway GraphQL API üzerinden silinerek dashboard'da yalnızca tek bir `mishil` servisi bırakıldı.
- **Melodik Uyku Parçaları Devrimi:** Parazit ve radyo hışırtısı hissi veren gürültü frekansları tamamen kaldırılarak yerine kristal netliğinde 5 melodik stüdyo parçası entegre edildi:
  1. `brahms_lullaby.wav`: Brahms Uyku Ninnisi (Piyano & Müzik Kutusu Melodisi)
  2. `moonlight_lullaby.wav`: Ayışığı Piyano Melodisi (Twinkle Calm Akorları)
  3. `deep_heartbeat.wav`: Tok Anne Kalp Atışı (Sıfır Hışırtı, 60 BPM Nabız)
  4. `forest_stream.wav`: Berrak Orman Su Şırıltısı & Yağmur
  5. `ocean_calm.wav`: Gece Okyanus Dalgaları (Sakinleştirici Ritim)
- **Mobil Web Simülatör & Mini Player:** `mobile/web-preview/index.html` arayüzündeki tüm ses kartları, açıklamaları ve mini çalıcı yeni melodik parçalarla senkronize edildi.

## [1.6.0] - 2026-08-23
### Added & Enhanced (Sıfır Cızırtılı DSP Akustik Ses Motoru & Master Varlıklar)
- **Paul Kellet 6-Kutuplu Gerçek Pembe Gürültü (Pink Noise):** -3dB/oktav analog eğri ve 300Hz 4-stage cascaded lowpass filtreleme ile kulaklık ve hoparlördeki tüm dijital cızırtı/tıklama ve yüksek frekans hışırtısı %100 yok edildi.
- **Dikişsiz Cosine Crossfade Döngüsü (Seamless Loop):** 16 saniyelik master parçaların başı ve sonu arasında 2.0 saniyelik dikişsiz örtüşme uygulanarak döngü başa sardığında oluşan ani klik/çıt sesleri engellendi.
- **Organik Anne Karnı & 62 BPM Nabız:** Stetoskopik çift vuruşlu (S1 Lub 46Hz, S2 Dub 64Hz) akustik rezonans ve amniyotik sıvı dalgalanması.
- **5S Dr. Karp Doğal İnsan Pışpışlaması:** 720Hz ve 1400Hz vokal trakt formantları ile asimetrik nefes alma-verme (exhale/inhale) zarfı.
- **Huzurlu Gece Yağmuru:** Poisson yumuşak damla dağılımı ve 42Hz derin ambient drone.
- **Brahms Ninni (Müzik Kutusu):** Kristal tınılı metal çan harmonikleri (2.75x & 5.4x overtones) ve eksponansiyel sönümleme ile ninni melodisi.
- **Web Audio Simülatör Entegrasyonu:** `mobile/web-preview/index.html` arayüzüne 5. ses olarak Brahms Ninni kartı eklendi ve tüm ses motoru yeni master dosyalardan beslenecek şekilde güncellendi.

## [1.5.0] - 2026-08-19
### Fixed (Kritik Bug Düzeltmeleri)
- **`main.py` Çift `GET /` Route:** İki kez tanımlanan route tek unified fonksiyona birleştirildi; dead code ortadan kaldırıldı.
- **`/delete-account` Broken HTML:** `<form>`, `<body>`, `<html>` kapanış tagları eksikti, Apple App Store review güvenliği sağlandı.
- **`security.py` Passlib Dead Import:** `CryptContext` import edilip kullanılmıyordu; kaldırıldı. `passlib[bcrypt]` bağımlılığı `bcrypt>=4.1.0` ile değiştirildi.
- **`config.py` DEBUG Default:** `DEBUG=True` → `DEBUG=False` olarak güvenli production değerine alındı. JWT_SECRET için production ortamında zayıf default uyarısı eklendi.
- **`wake_window.py` Endpoint Optional[int]:** `int = None` type annotation `Optional[int] = None` olarak düzeltildi.
- **Rate Limit Memory Leak:** `RATE_LIMIT_RECORD` dict hiç temizlenmiyordu. 5 dakikalık periyodik TTL cleanup fonksiyonu eklendi.
- **`conftest.py` Hard Import Crash:** `soundfile` bare import `try/except` ile sarıldı; soundfile yoksa test suite başlamadan çökmüyor, ilgili fixture skip ediliyor.
- **Wake Window Planlama Algoritması:** Nap loop'unda `current_time_cursor` güncellenmeden ikinci nap için kullanılıyordu. Cursor sırası düzeltildi.

### Fixed (Yüksek Öncelik)
- **Ses Katalog URL Çakışması:** `cdn.mishil.app` URL'leri config-tabanlı `/sounds/filename.mp3` relative URL'lere dönüştürüldü. `SOUNDS_BASE_URL` config'e eklendi.
- **`HEARTBEAT_CALM` Katalog Eksikliği:** Ağlama analizi bu ses tipini öneriyordu ama katalogda yoktu; eklendi.
- **RevenueCat CANCELLATION Bug:** `user.subscription_status` CANCELLATION event'inde güncellenmiyordu; düzeltildi.
- **Route Çakışması:** `GET /routines/baby/{baby_id}` → `GET /routines/logs/baby/{baby_id}` olarak taşındı; `{routine_type}` path param çakışması engellendi.
- **Test İzolasyonu:** `unittest.TestCase` pytest fixture tabanlı sınıflara dönüştürüldü; `mishil.db` üretim dosyası kirletilmiyor.
- **Rate Limit Bypass Eksikliği:** `/redoc`, `/sounds`, `/assets` bypass listesine eklendi.
- **30 Debug Script Temizliği:** Proje kökündeki geçici Railway/debug scriptleri `scripts/` klasörüne taşındı; `.gitignore`'a eklendi.
- **docker-compose Hardcoded Secret:** `POSTGRES_PASSWORD` ve `JWT_SECRET` `${ENV_VAR:?required}` syntax'ıyla zorunlu env'e taşındı.

### Fixed (Orta Öncelik)
- **`sound_url_mock` Field Adı:** Production API yanıtında "mock" sözcüğü kaldırıldı; `sound_url` olarak yeniden adlandırıldı.
- **`OVERSTIMULATED` Dead Enum:** Heuristic kural (yüksek RMS + yüksek ZCR) ve ebeveyn önerisi eklendi; artık aktif olarak üretilip tavsiye ediliyor.
- **`RoutineLogCreateRequest.routine_type`:** Endpoint path'ten alındığı için schema'daki gereksiz optional field kaldırıldı.
- **Çift `postgres://` Dönüşümü:** `config.py`'da zaten yapılan dönüşüm `db/base.py`'dan kaldırıldı.
- **`STATIC_API_KEY` Kaldırıldı:** Kullanılmayan hardcoded API key config'den çıkarıldı.
- **`requirements.txt`:** `passlib` kaldırıldı, `bcrypt>=4.1.0` bağımsız paket olarak eklendi.
- **`.gitignore`:** `scripts/`, `.pytest_cache/`, `.coverage` eklendi.

## [1.4.0] - 2026-08-19
### Added
- **Stüdyo Kaydı Akustik Ses Motoru:**
  - **432Hz Analog Pembe Gürültü (Pink Noise):** Voss-McCartney algoritması ve 432Hz sub-harmonik rezonans ile ipeksi derin uyku frekansı.
  - **Anne Karnı & 65 BPM Kalp Atışı:** 55-110Hz sub-bass kalp vuruşları ve amniyotik sıvı dinamiği.
  - **5S Dr. Karp İnsan Nefesi Pışpışlaması:** 850Hz vokal formantlı doğal insan nefes döngüsü.
  - **Gece Yağmuru & Doğa Ambiyansı:** Yüksek çözünürlüklü stereo ortam sesleri.
  - **Ses Seviyesi & Yumuşak Fade Zarfı:** 1.5s Fade-in ve 1.2s Fade-out ile bebeği uyandırmayan yumuşak geçişler ve dinamik Volume Slider.

## [1.3.0] - 2026-08-19
### Added
- **360° Güvenlik & Dayanıklılık:**
  - **In-Memory Rate Limiter:** IP tabanlı kayan pencere koruması (120 req / dakika).
  - **Production Exception Shield:** RFC 7807 uyumlu, iç Python stack trace ve hassas verileri gizleyen global hata kalkanı.
  - **Native Bcrypt Hashing:** Passlib wrap-bug hatasını önleyen, 72-byte güvenli kesimli yerel Bcrypt parola motoru.
- **UI/UX & Mağaza Uyumluluğu:**
  - **Haptic Dokunsal Titreşim:** Buton ve sekme dokunuşlarında titreşimli geri bildirim (`navigator.vibrate`).
  - **Apple Restore Purchases:** Apple Guideline 3.1.1 zorunlu abonelik geri yükleme ve RevenueCat senkronizasyon arayüzü.
  - **Ebeveyn & Bakıcı Paylaşımı:** Anne/Baba ortak bebek profili davet mekanizması.
- **Otomatik Test Kapsamı:** Standart Python `unittest` ile tüm auth, bebek, rutin ve DSP ağlama analizi testlerinin %100 yeşil geçmesi.

## [1.2.0] - 2026-08-19
### Added
- **App Store & Google Play Store Hazırlık Paketi:**
  - **EAS Build Yapılandırması (`eas.json`):** Production ve preview profilleri ile Android `.aab` ve iOS `.ipa` derleme pipeline'ı.
  - **Paket Kimliği & İzinler (`app.config.ts`):** `com.mrtgurpinar.mishil` bundle identifier, mikrofon izni ve arka plan ses izinleri.
  - **Mağaza Varlıkları (Assets):** 1024x1024 px resmi App Store ikonu, 1284x2778 px splash screen, adaptive foreground ve bildirim ikonları.
  - **Canlı Yasal Uç Noktalar (Compliance):** 
    - `/privacy`: COPPA, GDPR-K ve mikrofon gizlilik politikası sayfası.
    - `/terms`: Ebeveyn kullanım koşulları ve tıbbi feragatname (Medical Disclaimer).
    - `/delete-account`: Apple Guideline 5.1.1 zorunlu hesap silme talep sayfası.

## [1.1.0] - 2026-08-19
### Added
- **Web Audio API Native Sentezleyici Motoru:**
  - Sıfır dış dosya bağımlılığıyla çalışan gerçek zamanlı 432Hz Pembe Gürültü (Paul Kellet filtresi), Anne Karnı Ritmik Kalp Atışı (65 BPM Sub-bass pulse), Dr. Karp 5S Pışpışlama (Bandpass modulated noise) ve Gece Yağmuru ses motoru.
  - Canlı animasyonlu ses frekans dalgaları (Audio Visualizer Equalizer).
- **Hatch & Huckleberry Benchmark İyileştirmeleri:**
  - **Kapanma Zamanlayıcısı (Sleep Timer):** 15 dk, 30 dk, 45 dk, 60 dk ve Sürekli çalma seçenekleri ile otomatik yumuşak kapanış.
  - **24 Saatlik Görsel Uyku & Rutin Çizelgesi:** Bebeğin gün içindeki uyku, beslenme ve uyanıklık bloklarını gösteren etkileşimli timeline şeridi.
  - **Akıllı Çapraz Aksiyon:** Ağlama analizi sonucunda (%72 yorgunluk) tek tıkla doğrudan "432Hz Sesi Başlat & Uykuya Geç" akıllı ebeveyn köprüsü.
  - **Wonder Weeks Gelişim Sıçraması (Leap 5):** 6. ay regresyonu ve büyüme atağı rehberlik banner'ı.

## [1.0.0] - 2026-08-18
### Added
- **FastAPI Modüler Backend:**
  - Dinamik Wake Window & Kalan Günlük Uyku Bütçesi Motoru (Overtired %15 indirimi ile).
  - Librosa tabanlı Ağlama Sesi Heuristik Analiz Motoru (13 MFCC, Zero-Crossing Rate, Spectral Centroid).
  - RevenueCat Webhook & 3 Günlük Trial Yönetim Servisi.
  - Bebek profilleri, Rutin Günlüğü (Beslenme, Bez, Uyku) CRUD işlemleri.
  - JWT Kimlik Doğrulama, RFC 7807 Exception Handler ve JSON loglama altyapısı.
- **React Native (Expo Router + TypeScript) Mobil Frontend:**
  - `BreathingMoonIndicator` imza Reanimated nefes alan hilal animasyonu (4 sn döngü, sıcak bal rengi aurası).
  - `expo-av` ile 30 sn sayaçlı ses kaydı ve progress çubuğu ile analiz sonucu sunumu.
  - Çevrimdışı (Offline-first) rutin kuyruğu ve senkronizasyonu.
  - Arka planda kesintisiz çalan 432Hz Pembe Gürültü ve ortam sesleri oynatıcısı.
  - Melatonin dostu Gece Modu (`#141B2E`) ve şeffaf abonelik paywall ekranı.
- **İnteraktif Web Preview Simülatörü:**
  - Tarayıcıda anında çalışan iPhone çerçeveli dokunmatik simülatör (`web-preview/index.html`).
