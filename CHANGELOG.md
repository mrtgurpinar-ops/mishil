# Changelog - Mışıl Baby
 
Tüm önemli değişiklikler bu dosyada belgelenecektir.
 
## [4.21.0] - 2026-09-11
### 🛡️ Ödeme, Abonelik ve Deneme Mimarisi Tam Kapsamlı Mantık Güvenliği (Build 33)

Kullanıcının "başka mantık hatası var mı kontrol et tam kapsamlı kontrol istiyorum, ya şunu atlamışız demek istemiyorum lütfen bunu ince ayar tüm detay kontrol sağlayarak yap özellikle ödeme için" talimatı üzerine tüm ödeme, yetkilendirme ve mağaza köprüleri taranarak 5 kritik mantık açığı kapatıldı:
1. **Deneme Süresi Mantık Koruması:** `getTrialStatus()` içinde anahtar yokken kendi kendine `mishil_trial_start` oluşturup "Şimdilik Atla" diyen ücretsiz kullanıcılara tüm Pro özellikleri 7 gün bedava açma açığı kökten kapatıldı.
2. **VIP Satın Alma & Yenileme Modal Kapatma:** Native IAP ve geri yükleme tamamlandığında `vip-renewal-modal` ekranının açık kalması engellendi; anında otomatik kapanış sağlandı.
3. **Anlık Arayüz Tazeleme:** Satın alma ve geri yükleme bittiği an Ayarlar rozetlerinin (`✓ AKTİF PLANINIZ`) beklemeden anında yenilenmesi sağlandı (`updateSubscriptionStatusUI` ve `renderAllViews`).
4. **RevenueCat Geri Yükleme & Senkron Plan Tespiti:** Geri yüklemede (`RESTORE_PURCHASES`) ve canlı senkronizasyonda (`syncEntitlementToWebView`) kullanıcının aktif planının (Yıllık/Aylık) RevenueCat haklarından dinamik okunması ve diske eşitlenmesi sağlandı.
5. **Native Paywall Geri Yükleme Güvenliği:** `subscription.tsx` içinde `res.success` yerine `res.success && res.isActive` kontrolü getirilerek hiç ödemesi olmayan kullanıcıların Pro'yu bedava açması engellendi; `useSubscriptionStatus.ts` 7 gün ile hizalandı.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.21.0'`, `BUILD_NUMBER = 33` (`mobile/app.config.ts`, `public/app.html`, `WEB_APP_META`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts` (270 KB).
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

## [4.20.0] - 2026-09-11
### 🛡️ Ayarlar Abonelik Yönetimi, Plan Yükseltme (Upgrade) Güvenliği & Mağaza Köprüsü (Build 32)

Kullanıcının "ödeme sistemini kontrol et aylık ödediğinde ayarlardan yıllık seçip devam ediyor olabilir bunu doğru kurmuş olmamız önemli" talimatı doğrultusunda:
1. **Bedelsiz Plan Değiştirme Yanılgısının Engellenmesi:**
   - Ayarlar altındaki abonelik kartlarına tıklandığında yerel depolamadaki planın (`mishil_subscription_plan`) anında ve ücretsizce değiştirilmesi engellendi. Artık kart seçimi yalnızca hedef seçimi (`settingsTargetPlan`) tutar.
2. **Aktif Plan Dinamik Rozetlemesi & Yükseltme Butonu:**
   - Kullanıcının aktif abonelik planına göre (Aylık/Yıllık) ilgili karta yeşil `✓ AKTİF PLANINIZ` rozeti dinamik olarak atanır.
   - Aylık plandaki kullanıcı Yıllık karta tıkladığında kartın altında belirgin bir `👑 Yıllık VIP Plana Yükselt (%67 Tasarruf Et)` butonu gösterilir.
   - Bu butona tıklandığında `executeSettingsPlanAction()` üzerinden Google Play ve App Store IAP yükseltme (Proration/Upgrade) akışı başlatılır; mağaza işlemi onaylamadan plan asla değiştirilmez.
3. **Apple & Google Mağaza Abonelik Yönetim Köprüsü (Guideline 3.1.2):**
   - Yıllık plandaki kullanıcı aylık karta geçmek istediğinde veya "Aboneliği Yönet / İptal Et" butonuna bastığında StoreKit (`apps.apple.com/account/subscriptions`) ya da Google Play Store (`play.google.com/store/account/subscriptions`) doğrudan açılarak periyot düşürme/iptal akışı mağaza kurallarına uygun şekilde yönlendirilir.
   - `MishilUnifiedWebView.tsx` içerisine `MANAGE_SUBSCRIPTIONS` mesaj yakalayıcısı ve `Linking` köprüsü eklendi.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.20.0'`, `BUILD_NUMBER = 32` (`mobile/app.config.ts`, `public/app.html`, `WEB_APP_META`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts` (268 KB).
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

## [4.19.1] - 2026-09-10
### 💳 Genişletilmiş Çoklu Mağaza ID Köprüsü & Test Satın Alma Onarımı (Build 31)

Kullanıcının "yeni test kullanıcısı eklendiğinde abonelik paketi bulunamadı diyor, satın alma yapılamıyor bunun sebebi nedir" sorgusu ve ardından "genişlet güncelle" talimatı doğrultusunda:
1. **Çoklu Aday Ürün Kimliği Eşleştirme Motoru:** Tekil `misil_monthly` araması yerine hem iOS StoreKit 2 hem Google Play Billing için aday liste mimarisine geçildi (`['monthly', 'misil_monthly', 'misil_baby_monthly', '$rc_monthly', 'misil_sub_monthly']` ve yıllık için `['yearly', 'misil_annual', 'misil_yearly', 'misil_baby_annual', '$rc_annual', 'annual']`).
2. **'no_package' Engelinin Aşılması:** RevenueCat Dashboard offerings verisi gecikse veya panelde ürünler henüz eşlenmemiş olsa dahi, mağazada açılan ürün adı ne olursa olsun StoreKit ve Play Billing doğrudan taranarak test kullanıcısının karşısına resmi satın alma penceresinin gelmesi sağlandı.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.19.1'`, `BUILD_NUMBER = 31` (`mobile/app.config.ts`, `public/app.html`, `WEB_APP_META`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts` (260 KB).
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS.

## [4.19.0] - 2026-09-10
### 🎁 Ücretsiz Deneme Süresini 7 Güne Çıkarma & Çoklu Platform (iOS, Google Play, RevenueCat) Tam Uyumu (Build 30)

Kullanıcının "ücretsiz deneme 7 gün olsa daha iyi bence" ve "iOS google play ve revenue cat için hiçbirinde aksama olmadığını kontrol et" talimatları doğrultusunda tüm ücretsiz deneme kurgusu 3 günden tam 7 güne (168 saat) çıkarıldı ve çoklu platform mağaza uyumluluğu sağlandı:
1. **iOS StoreKit 2 & App Store Review Guideline 3.1.2 Uyumu:**
   - Apple Şeffaf Abonelik Kuralı (Guideline 3.1.2) uyarınca tüm ekranlarda (`app.html`, React Native `subscription.tsx`) "7 günlük deneme süresi içinde ₺0 ödersiniz, süre dolmadan en az 24 saat önce iptal edilebilir" net şartları güncellendi.
2. **Google Play Console & Billing Library Senkronu:**
   - Tanıtım deneme teklifi (Introductory Free Trial) baz planlarıyla tam hizalandı; Google Play Console'daki 7 günlük periyot (`P7D`) ile WebView ve native köprüler birebir eşitlendi.
3. **RevenueCat SDK & `FALLBACK_OFFERINGS` Senkronu:**
   - `mobile/features/subscription/revenuecat.ts` içerisindeki yedek paket açıklamaları "7 Gün Ücretsiz Deneme" olarak güncellendi. Paket tanımlayıcıları (`$rc_monthly`, `$rc_annual`, `misil_monthly`, `misil_annual`) ve entitlement (`pro`) korunarak sıfır kesinti sağlandı.
4. **Native Paywall & Ayarlar Ekranları (`subscription.tsx`, `settings.tsx`, `register.tsx`):**
   - React Native native ekranlarındaki tüm rozetler (`En Çok Tercih Edilen • 7 Gün Ücretsiz`), CTA butonları (`7 Gün Ücretsiz Başla`) ve hesap durumu (`7 Günlük Ücretsiz Deneme`) senkronize edildi.
5. **Dinamik 7 Günlük Deneme Motoru & Yerel Tarih Gösterimi:**
   - `getTrialStatus()` içindeki hesaplama `7 * 24 * 60 * 60 * 1000` (168 saat) olarak güncellendi; `updateTrialEndDateDisplay()` cihaz yerel takvimine göre tam 7 gün sonrasının Türkçe tarihini (`X Ay Yıl`) dinamik olarak oluşturacak şekilde doğrulandı.
6. **Backend Servis & Kural Senkronizasyonu:**
   - `app/core/config.py` `TRIAL_DURATION_DAYS = 7` yapıldı; `app/services/subscription.py` deneme başlatma yanıtları 7 güne çekildi.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.19.0'`, `BUILD_NUMBER = 30` (`mobile/app.config.ts`, `public/app.html`, `WEB_APP_META`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts` (260 KB).
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, Playwright Uçtan Uca 7-Day Trial Testi PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

### 🔬 Tüm Mock/Statik Verileri Tam Dinamize Etme & Biyolojik Uçtan Uca Entegrasyon (Build 29)

Kullanıcının "mock veri taraması yap nasıl dinamize ederiz önerilerini sun" incelemesi ve ardından "seçenek c" onayı doğrultusunda sistemdeki tüm sahte ve statik veriler uçtan uca dinamik hale getirildi:
1. **Akustik Ağlama Analizi Dinamizasyonu:** Sabit `%82 Yorgunluk` HTML kartı tamamen kaldırılarak; hem canlı FastAPI DSP (`POST /api/v1/cry-analysis/analyze` ve `/api/v1/cry/analyze`) hem de çevrimdışı biyolojik motoru (`evaluateClientCryProbabilities`) ile uyanıklık penceresi, beslenme aralığı ve atak durumuna duyarlı anlık dinamik olasılıklar (`cause-1-val`, `cause-2-val`, `cause-3-val`) ve klinik aksiyon tavsiyesi (`cry-action-tip`) entegre edildi.
2. **Bireyselleştirilmiş Onboarding Uyku Raporu:** Sabit "45 dk ➔ 12 dk" ve "4 kez ➔ 1 kez" yazıları kaldırıldı; annenin ankette girdiği gerçek gece uyanma sıklığı (`quizAnswers.nightWakes`) ve uykuya direnç süresine (`quizAnswers.sleepResistance`) göre 7 günlük kişisel hedefler ve ay bazlı regresyon teşhisi bağlandı.
3. **Mışıl Dadı Çevrimdışı Klinik Uzman Motoru:** `fallbackDadiLocalResponse` motoru zenginleştirildi; bebeğin ayına, günlük uyku açığına (`calculateRoutineRollup()`), uyanıklık penceresine ve Wonder Weeks sıçramasına duyarlı 6 farklı klinik protokol (kısa uyku, gece beslenmesi, atak, gaz masajı, oda sıcaklığı vb.) devreye alındı.
4. **Wonder Weeks Dinamik Geri Sayım & Fırtına Zirvesi:** Bir sonraki zihinsel sıçramaya kaç gün kaldığı (`X gün kaldı: Hazırlık Modu`) ve atak haftası içerisindeki fırtınalı zirve günleri dinamik rozetle görselleştirildi.
5. **Pediatrik Aşı Takip Defteri:** Aşının uygulandığı gerçek tarih kaydedilerek rozette dinamik gösterilmesi sağlandı.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.18.0'`, `BUILD_NUMBER = 29` (`mobile/app.config.ts`, `public/app.html`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts` (259 KB).
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, Playwright Uçtan Uca Simülasyon %100 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

## [4.17.0] - 2026-09-10
### 🌟 Mışıl Holistik Gelişim Endeksi (MHGE) & Akıllı Klinik Skorlama Motoru (Build 28)

Kullanıcının "gelişim skoru hesaplamasını kontrol et önerilerini sun tüm yapıya uygun bir öneri ve skorlama olmalı" talebi doğrultusunda, eski sahte puanlama (`isManual ? 78 : 94`) ve sabit 210 dk uyku hedefi tamamen kaldırılarak Mışıl Baby'nin tüm modülleriyle entegre çalışan **Mışıl Holistik Gelişim Endeksi (MHGE)** mimarisine geçildi:
1. **Yaşa Göre Dinamik Pediatrik Uyku Bütçesi (%40 Ağırlık):** WHO ve AAP standartlarına göre bebeğin ayına bağlı dinamik günlük uyku hedefi (`getPediatricDailySleepTargetMins`) entegre edildi (0-2 ay: 15 saat, 3-5 ay: 14 saat, 6-8 ay: 13.5 saat, 9-11 ay: 13 saat, 12+ ay: 12 saat).
2. **Gerçek SweetSpot Zaman Sapması Toleransı (%30 Ağırlık):** Bebeğin son uykusunun hesaplanan biyolojik uyku penceresiyle (`sweetSpot`) dakikası dakikasına ne kadar örtüştüğü ölçülür. ±15 dk mükemmel (100 puan), ±30 dk çok iyi (85 puan), ±45 dk kabul edilebilir (70 puan).
3. **Beslenme & Bez Biyolojik Dengesi (%15 Ağırlık):** Son 24 saatteki beslenme aralığı (2.5 - 4 saat) ve yeterli hidrasyon/bez sayısı (≥4 bez) değerlendirilir.
4. **Wonder Weeks Atak Haftası Koruma Kalkanı (%15 Ağırlık):** Bebek gelişimsel sıçrama (Wonder Weeks leap) dönemindeyse sistem bunu otomatik tespit eder; SweetSpot toleransını +15 dk genişletir ve skoru en az 90 puan koruma kalkanına alır.
5. **Akıllı Klinik Rehberlik Tavsiyesi (`advice`):** Skora göre generic olmayan, bebeğin o anki uykusuzluk, aşırı yorgunluk veya atak durumunu ebeveyne açıklayan rehberlik metinleri üretir.
6. **4 İlerlemeli Holistik Skor Kartı UI:** Analiz sekmesindeki skor kartı; Sirkadiyen Uyku, SweetSpot, Beslenme/Bez ve Wonder Weeks bileşenlerini ayrı barlarla ve dinamik klinik tavsiye kutusuyla görselleştirir.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.17.0'`, `BUILD_NUMBER = 28` (`mobile/app.config.ts`, `public/app.html`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts` (247 KB).
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

## [4.16.0] - 2026-09-10
### 🚀 DOM Hiyerarşi Onarımı, 5 Sayfada Yekpare Başlık & Kaydırma Kilidi Çözümü (Build 27)

Kullanıcının "başlığın şerit şeklinde aşağı inmesi bana güzel gelmedi, mışıl dadı, sesler ve ayarlar sayfalarının üstünde hala boşluk var, bu ekranlar aşağıda kaydırılmıyor artık haliyle kullanılamıyor gibi bir şey, tüm projeyi kontrol et, tüm sayfalarda aynı olmalı" bildirimleri doğrultusunda:
1. **DOM Kapatma Tagı Onarımı & Kaydırma Kilidi Çözüldü:** `public/app.html` satır 2088'deki fazlalık `</div>` etiketi kaldırıldı. `main-app-screen` konteynerinin erken kapanması önlenerek Mışıl Dadı, Sesler ve Ayarlar sekmeleri tekrar ana kaydırma konteyneri (`.screen-container`) içerisine alındı. 18 parça ses ve tüm uzun sekmeler akıcı kaydırma yeteneğine kavuşturuldu (`canScroll: true`).
2. **Tavan Boşlukları Sıfırlandı:** Dışarıda kalan sekmelerin üzerindeki 82px'lik yapay boşluk giderildi; 5 sayfanın 5'i de ortak safe padding (`var(--device-safe-top, 6px)`) ile aynı tavan hizasında başlatıldı.
3. **Tüm Sayfalarda Yekpare Başlık Mimarisi:** `.app-header` üzerindeki `position: sticky; top: 0; background: var(--bg-night);` kaldırıldı; tüm sayfalarda `position: relative; background: transparent !important;` uygulanarak sayfa kaydırılırken üstte oluşan yapay koyu şerit/bant tamamen ortadan kaldırıldı.
4. **Tam Proje HTML Tag Denetimi & escapeHtml Entegrasyonu:** 5.600+ satırlık HTML kodunun tamamı taranarak sıfır tag hatasına indirildi. Eksik olan `escapeHtml` yardımcı fonksiyonu eklenerek runtime çökmeleri önlendi.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.16.0'`, `BUILD_NUMBER = 27` (`mobile/app.config.ts`, `public/app.html`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts` (242 KB).
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

## [4.15.0] - 2026-09-10
### 🌐 Evrensel Adaptif Cihaz Motoru (`DeviceAdaptiveEngine`) & Akıcı Tam Ekran Viewport Mimarisi (Build 26)

Kullanıcının ilettiği "hala alakasız yukarıda kalan boşluk var, tam ekrana oturmuyor bunu çözecek düzgün bir metodoloji bulmalısın" ve "tüm farklı mobil cihazlarda o mobil cihaza göre şekillenmeli" yönlendirmeleri doğrultusunda:
1. **Yapay Tavan Boşluğu Sıfırlandı:** Önceki versiyonda çentik koruması amacıyla konulan sabit `calc(max(54px, env(safe-area-inset-top) + 20px))` kuralı kaldırıldı; tarayıcı veya masaüstünde oluşan yapay 74px+ gereksiz boşluk temizlendi.
2. **Evrensel Adaptif Cihaz Motoru (`applyUniversalDeviceMetrics`):** Cihazın fiziksel ekran boyutunu, yönünü (portrait/landscape) ve platform ortamını (Masaüstü, Native Expo iOS/Android, Bağımsız PWA, Mobil Tarayıcı Safari/Chrome) anlık tespit eden JavaScript motoru eklendi. CSS değişkenleri (`--device-safe-top`, `--device-safe-bottom`) her donanımın kendi geometrisine göre dinamik olarak hesaplanmaktadır.
3. **Akıcı Tam Ekran (Fluid Fullscreen) Mimarisi:** Masaüstü veya mobilde sabit piksel telefon kutusu yerine `100% width/height/dvh` akıcı tam ekran mimarisine geçildi; geniş ekranlarda içeriğin okunabilirliğini korumak için `max-width: 540px; margin: 0 auto;` odaklama container'ı uygulandı.
4. **Donanım Çentiği ve Sahte Bar Temizliği:** Cihazların üzerinde yapay duran `.device-notch` ve `.status-bar` (sahte pil/saat) her platformda tamamen gizlenerek cihazın kendi donanım barının doğal çalışması sağlandı.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.15.0'`, `BUILD_NUMBER = 26` (`mobile/app.config.ts`, `public/app.html`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts` (241 KB).
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

## [4.14.0] - 2026-09-10
### 🎯 Ses Menüsü Scroll Kilit & Aşağı Kayma Çözümü, Masaüstü Dikey Kilit ve Yapışkan Başlık Mimarisi (Build 25)

Kullanıcının ilettiği "ses menüsü hala daha aşağı kaymış ve oynamadığı için altta gözüküyor" ve "üst başlıklar ekranın çok üstünde kaldığı için gözükmüyor" bildirimleri üzerine yapılan derin DOM ve CSS reflow incelemesi sonucunda:
1. **DOM Reflow Sıralama Hatası Giderildi:** `switchTab` içinde `scrollTop = 0` çağrısı, yeni sekme (`view-sounds`) henüz `display: none` halindeyken çalıştırıldığı için tarayıcı tarafından yutuluyordu. Kod, yeni görünüm `display: block` yapıldıktan sonra çalışan çift katmanlı `requestAnimationFrame` ve 25ms güvenlik kuyruğuna bağlandı.
2. **Masaüstü Dikey Merkezleme Tuzağı (`margin: auto 0;`) Kaldırıldı:** Flexbox dikey ortalaması ekran boyutu 844px'ten küçük olduğunda tüm telefon çerçevesini ekranın üstünden dışarıya (-70px negatif alana) itiyordu. Bu durum başlıkların ekran dışında kalmasına ve sayfa tepe noktasında olduğu için kullanıcının ekranı oynatamamasına yol açıyordu. `margin: 0 auto !important; margin-top: 12px !important; align-self: flex-start;` yapılarak tepe taşması tamamen çözüldü.
3. **Mobil Çentik & Güvenli Alan Tavanı Artırıldı:** Mobildeki 28px'lik yetersiz padding, Dynamic Island ve çentikleri kapsayacak şekilde `calc(max(54px, env(safe-area-inset-top) + 20px))` yapıldı.
4. **Yapışkan Başlık (Sticky App-Header):** `.app-header` `position: sticky; top: 0; z-index: 60;` yapılarak ses listesinde gezinirken başlıkların ve filtrelerin daima görünür kalması sağlandı.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.14.0'`, `BUILD_NUMBER = 25` (`mobile/app.config.ts`, `public/app.html`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts` (240 KB).
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

## [4.13.0] - 2026-09-10
### 🚀 3 Günlük Ücretsiz Deneme Motoru, Satın Alma & Scroll Sıfırlama, Viewport Sığmama ve Canlı Veri Onarımı (Build 24)

Kullanıcının doğrudan inceleme geri bildirimleri doğrultusunda:
1. Satın al tuşuna basıldığında tetiklenmeme sorunu giderildi; hem web/PWA hem mobilde anında deneme başlatma ve VIP satın alma açıldı.
2. 3 gün ücretsiz deneme çelişkisi çözüldü; 72 saatlik gerçek dinamik `TrialEngine` entegre edildi, deneme süresince tüm Pro özelliklere kesintisiz erişim sağlandı.
3. Sesler ve Ayarlar sekmelerine geçildiğinde ekranın aşağı kaymış başlama sorunu `switchTab` scroll-reset ile çözüldü.
4. Telefon ekranının en üstünün çerçevenin/ekranın dışında kalması ve sığmama sorunu CSS esnek padding ve viewport düzenlemesiyle giderildi.
5. HTML'de kalan sahte sabit skor barları ve uydurma ortalama uyku verileri temizlenerek gerçek kayıtlara bağlandı.

#### 🛡️ Fixed & Functional
- **Satın Al ve Geri Yükle Onarımı:**
  - Onboarding ve VIP yenileme modalındaki "Hemen Başla" ve "VIP Aboneliği Başlat" butonları web ortamında `mishil_subscription_active` ve `mishil_trial_start` değerlerini işleyip modalı kapatarak Pro yetkilerini anında devreye sokacak şekilde bağlandı.
- **72 Saatlik Dinamik Ücretsiz Deneme Motoru (`TrialEngine`):**
  - İlk kayıt anından itibaren 72 saatlik geri sayım mekanizması kuruldu. `requireActiveSubscription()` fonksiyonu deneme süresince kilit açarak kullanıcının her tıklamada satın alma modalına zorlanmasını engelledi.
  - Ayarlar sekmesindeki deneme durumu `updateSubscriptionStatusUI()` ile dinamikleştirildi (kalan saat ve dakika anlık hesaplanır).
- **Sekme Geçişlerinde Scroll Sıfırlama (Scroll-To-Top):**
  - `switchTab(tabName)` tetiklendiğinde `.screen-container` ve sayfa pencere kaydırma pozisyonu en başa (`scrollTop = 0`) çekilerek Sesler ve Ayarlar sekmesinin aşağı kaymış başlaması tamamen önlendi.
- **Viewport & Dikey Taşma Düzeltmesi:**
  - `body` üzerindeki `align-items: center` esnekliği `flex-start` ve `overflow-y: auto` olarak güncellendi; dikey sığmama durumunda üst kısmın ekran dışına taşması engellendi. Mobil safe-area padding'leri optimize edildi.
- **Statik Sahte Skor ve Uyku Verisi Temizliği:**
  - Bento kartlarındaki sabit `85/100`, `92/100`, `80/100` sahte yüzdeleri ve `Ort: 13.8 Saat` statik metinleri kaldırıldı; `renderWeeklyChart` gerçek uyku sürelerinin ortalamasını dinamik hesaplayacak şekilde güncellendi.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.13.0'`, `BUILD_NUMBER = 24` (`mobile/app.config.ts`, `public/app.html`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts`.
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

## [4.12.0] - 2026-09-10
### 👑 Tekil RevenueCat Mimarisi (3 Gün Mağaza Denemesi + Aylık VIP) & Analiz Sekmesi Sadeleştirmesi (Build 23)

Kullanıcının talimatları ve onayladığı uygulama planı uyarınca:
1. Analiz sekmesindeki bilişsel yükü düşürmek için 7 analitik kart 3 dinamik segmente ayrıldı.
2. Freemium ve kontrol açıkları kapatıldı; tekil 3 gün ücretsiz deneme + Aylık VIP (ve Yıllık VIP) iş modeline geçildi.
3. RevenueCat canlı offering fiyatları native köprü üzerinden web arayüzüne anlık enjekte edildi.
4. Kafa karıştıran Ömür Boyu paketi kaldırılarak 2-tier temiz paket sunumuna geçildi.

#### ✨ Added
- **3'lü Segment Hap Menüsü (Analiz Sekmesi):**
  - Analiz sekmesi 7 ardışık karttan kurtarılarak `[ 📊 Uyku & Ritim | 💉 Sağlık & Gelişim | 📜 Aktivite ]` şeklinde 3 odak paneline bölündü.
  - `switchAnalyticsSegment()` mimarisi ile kullanıcı istediği alt paneli anında görüntüler, bilişsel aşırı yüklenme önlendi.
- **Canlı RevenueCat Fiyat Köprüsü:**
  - `MishilUnifiedWebView.tsx` ve `revenuecat.ts` üzerinden Google Play ve App Store canlı yerel para birimi fiyatları (`window.__MISHIL_STORE_PRICES__`) otomatik olarak WebView'e aktarıldı ve `applyStorePrices()` ile arayüzdeki fiyat metinleri dinamikleştirildi.
- **Dinamik 18 Stüdyo Sesi VIP & Ücretsiz Göstergesi:**
  - İlk 2 akustik ninni (`brahms_lullaby`, `moonlight_lullaby`) ücretsiz denemeye açık bırakıldı; diğer 16 parça VIP kilitli hale getirilerek arayüzde şık yeşil "ÜCRETSİZ" ve altın "👑 VIP" rozetleri ile donatıldı.

#### 🛡️ Fixed & Security
- **Freemium Açığı Kapatıldı & VIP Koruması Genişletildi:**
  - `requireActiveSubscription()` fonksiyonundaki `null` durumu açığı kapatıldı; `mishil_subscription_active === 'true'` veya `mishil_admin_gate === 'unlocked'` olmayan durumlarda Pro özellikler engellendi.
  - VIP erişim kapısı; Mışıl Dadı AI Koçu'nun yanı sıra Analiz Sekmesi (`switchTab('analytics')`), Canlı Uyku Başlatma (`toggleLiveSleep()`), Manuel Rutin Ekleme (`openAddRoutineModal()`) ve 16 stüdyo sesine bağlandı.
- **Onboarding Duvarı Koruması:**
  - Onboarding Adım 1 ve Adım 5 üzerindeki serbest atlama linkleri kaldırılarak kullanıcının 3 günlük ücretsiz denemeyi (App Store / Google Play In-App Purchase Trial) başlatması veya önceki satın alımlarını geri yüklemesi sağlandı.
- **Ömür Boyu Paket Temizliği:**
  - Karışıklık yaratan Ömür Boyu (Lifetime) paketi Onboarding, VIP Yenileme Modalı ve Ayarlar sekmesinden kaldırılarak temiz 2 pakete (Aylık VIP 3 gün ₺0 denemeli & Yıllık VIP %67 tasarruflu) indirildi.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.12.0'`, `BUILD_NUMBER = 23` (`mobile/app.config.ts`, `public/app.html`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts`.
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

## [4.11.1] - 2026-09-10
+### 🛡️ 360° Kod, Mantık, UX ve UI Düzeltmeleri & SweetSpot Dinamik Motoru (Build 22)
+
+360 derece kod taraması ile tespit edilen çalışma zamanı çökmesi, uyanıklık penceresi mantık hatası, canlı sayaç kalıcılığı ve tema kontrast sorunları giderildi.
+
+#### 🛠️ Fixed
+- **Kritik Çökme Giderildi (`ReferenceError: getBabyRoutines`):**
+  - `renderBabyRhythmReport()` içinde tanımsız olan `getBabyRoutines()` fonksiyonu yerine `activeRoutines` global dizisi bağlandı; sayfa ilk açılışında JS'in patlayıp aşı takvimi, Wonder Weeks ve profil yüklemesini durdurması önlendi.
+- **SweetSpot® Dinamik Referans Mantığı:**
+  - Sonraki ideal uyku vakti hesabı statik `Date.now()` yerine bebeğin son uyku kaydındaki uyanma saatine (`lastWakeDate`) bağlandı.
+  - Uyanıklık penceresi aşıldığında UI üzerinde belirgin uyarı (`⚠️ Uyanıklık penceresi aşıldı!`) ve renk uyarısı tetiklendi.
+  - Rutin ekleme modalında sabit 90 dk yerine bebeğin gelişim ayına uygun dinamik uyanıklık penceresi (`calc.wakeWindowMin`) uygulandı.
+- **Canlı Uyku Sayacı (Timer) Kalıcılığı:**
+  - `toggleLiveSleep()` içinde uyku başlama zamanı `localStorage`'a (`mishil_live_sleep_start`) kaydedildi; telefon ekranı kilitlendiğinde veya tarayıcı yenilendiğinde devam eden seansın silinmesi engellendi ve `checkAndRestoreLiveSleep()` ile otomatik geri yükleme sağlandı.
+- **Gece/Gündüz Uykusu Otomatik Ayrımı:**
+  - Saat 20:00 - 07:00 arasındaki uykular otomatik olarak "Gece Uykusu", gündüz uykuları "Gündüz Uykusu (Nap X)" olarak etiketlendi.
+- **Light Mode Kontrast İyileştirmesi:**
+  - Açık tema aktifleştiğinde kart ve başlık içindeki metinlerin beyaz zemin üzerinde görünmez olmasını engelleyen global adaptif tipografi kuralları (`[data-theme="light"]`) entegre edildi.
+- **iOS Form Auto-Zoom Engeli:**
+  - Input font boyutları 16px'e çekilerek iOS Safari'deki odaklanma yakınlaştırma bug'ı ortadan kaldırıldı.
+- **Modal Backdrop Dokunma Koruması:**
+  - Modalların dış karartma alanına (overlay) dokunarak tek hamlede kapatılabilmesi (`closeModalOnOverlay`) sağlandı.
+- **Sahte Veri Kalıntıları Temizlendi:**
+  - Mışıl Dadı karşılama baloncuğundaki sabit "Mina" ibaresi dinamik `baby.name` ile senkronlandı; anket rapor başlığı ve uyku bütçesi başlangıç değerleri dinamikleştirildi.
+
+#### 🔧 Chore
+- Sürüm artırımı: `APP_VERSION = '4.11.1'`, `BUILD_NUMBER = 22` (`mobile/app.config.ts`, `public/app.html`).
+- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts`.
+- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.
+
 ## [4.11.0] - 2026-09-09
### 🎨 Dark/Light Mode, Aşı Takvimi, Ritim Zirve Raporu, Serbest Onboarding & Apple Guideline 2.1/2.3.2 Uyumu (Build 21)

Apple App Store ret gerekçeleri (IAP submission & metadata) ve arkadaş incelemesindeki 8 kritik UX geri bildirimi çözüldü.

#### ✨ Added
- **Dark Mode & Light Mode Dinamik Tema Desteği:**
  - CSS `:root[data-theme="light"]` ve `:root[data-theme="dark"]` OKLCH tasarım tokenları eklendi.
  - Telefon sistem temasını (`prefers-color-scheme`) otomatik algılama ve anında tepki verme.
  - Ayarlar sekmesine 3 seçenekli tema yöneticisi eklendi: `[ 📱 Sistem (Otomatik) | 🌙 Koyu Gece | ☀️ Aydınlık Gündüz ]`. Tercih `localStorage`'da kalıcı saklanır.
- **Pediatrik Aşı Takvimi (T.C. Sağlık Bakanlığı & DSÖ Onaylı):**
  - Doğumdan 24. aya kadar 20 aşıyı içeren dinamik pediatrik aşı takip motoru (`VACCINE_SCHEDULE`).
  - Bebeğin doğum tarihine göre aşı gününü otomatik hesaplama ve durum rozetleri (`Tamamlandı ✅`, `Vakti Geldi 🔔`, `Gelecek ⏳`).
  - Checkbox ile aşıları tamamlandı olarak işaretleme ve `mishil_completed_vaccines` üzerinde saklama.
- **24 Saatlik Bebek Ritmi & Zirve (Peak) Saatler Analizi:**
  - Analiz sekmesine biyometrik ritim kartı eklendi: Girilen rutinlerden beslenmenin zirve yaptığı saatler (`08:30 • 12:30 • 16:30 • 20:00`), gaz ve bez değişim aralıkları ve en derin uyku blokları histogramı.
- **Girişte Fonksiyon Tanıtım Turu (Feature Highlights):**
  - Onboarding 1. adımına 4 temel fonksiyonu (SweetSpot uykusu, 18 stüdyo sesi mikseri, Wonder Weeks atakları, Mışıl Dadı AI koçu) tanıtan görsel kartlar eklendi.
- **Serbest "Şimdilik Atla ➔" (Ücretsiz Temel Mod):**
  - Onboarding başlığına ve adımlarına zorunlu kilitlemeyi kaldıran "Şimdilik Atla ➔" seçeneği getirildi. Bebeğin adı girilmemişse varsayılan "Bebeğim" olarak ücretsiz ana ekrana anında geçiş sağlanır.
- **Canlı Aile & Dadı Senkronizasyon Linki:**
  - Sabit mock aile metni yerine dinamik üye yönetimi (`mishil_family_members`), yeni dadı/bakıcı ekleme ve `navigator.share` / panoya kopyalama ile canlı aile davet bağlantısı üretimi (`shareFamilyInviteLink()`).

#### 🛠️ Fixed
- **Ücret Seçildiğinde Ödemeye Geçmeme Hatası (Missing `selectOnboardingPlan`):**
  - HTML'de çağrılan ancak script içinde tanımsız olan `selectOnboardingPlan` fonksiyonu yazılarak düzeltildi; kart seçildiğinde dinamik plan seçimi ve buton güncellemesi sağlandı.
- **Paywall Kilitlenme Sorunu:**
  - `chk-medical-disclaimer` varsayılan aktif ve bilgilendirici yapılarak `btn-onboarding-pro` butonunun tıklanamama engeli kaldırıldı; doğrudan "🎁 3 Gün Ücretsiz Dene ve Başlat" akışı açıldı.
- **StoreKit Satın Alma Hata Toleransı (`revenuecat.ts`):**
  - Offering paketleri yüklenemediğinde veya sandbox ortamında StoreKit üzerinden doğrudan `Purchases.getProducts(['misil_annual', 'misil_monthly'])` ve `purchaseStoreProduct` yedek kanalı devreye alındı.
- **Apple Guideline 2.3.2 Mağaza Metni Revizyonu:**
  - `APP_STORE_LISTING.md` mağaza açıklama metninde Ücretsiz Temel Özellikler ile VIP Ücretli Abonelik Gerektiren Özellikler Apple kurallarına uygun olarak açıkça ayrıştırıldı.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.11.0'`, `BUILD_NUMBER = 21` (`mobile/app.config.ts`, `public/app.html`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts` (221 KB).
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

## [4.10.2] - 2026-09-08
### 👑 Kalıcı Bebek Profili, Bağımsız VIP Yenileme & Canlı Lisans Senkronu

Kaynak: `projects/mishil/CLAUDE_HANDOFF.md` (Antigravity → Claude Code devir teslim, 7 adım).

#### ✨ Added
- **Bağımsız VIP yenileme modalı (`#vip-renewal-modal`):** Onboarding anketinden tamamen
  ayrı; başlık bebeğin adını dinamik okur. 3 paket kartı (Yıllık VIP / Aylık Pro / Ömür Boyu),
  "Yenile / Satın Al" (`PURCHASE_PACKAGE`) ve "Satın Alımları Geri Yükle" (`RESTORE_PURCHASES`)
  butonları. Abonelik açıkça pasifken (`mishil_subscription_active === 'false'`) Pro özellik
  (Mışıl Dadı AI Koçu) açılmak istendiğinde anket yerine doğrudan bu modal açılır.
- **Backend önbellek kilidi:** `/app` ve `/preview` `HTMLResponse` yanıtlarına
  `Cache-Control: no-store, no-cache, must-revalidate, max-age=0` + `Pragma: no-cache` + `Expires: 0`
  başlıkları eklendi; telefonlar eski HTML'i diske önbelleklemeden her zaman Railway'deki canlı
  kodu çeker.
- **Native canlı lisans doğrulaması:** `MishilUnifiedWebView` her başarılı yüklemede ve uygulama
  ön plana geldiğinde (`AppState` 'active') `Purchases.getCustomerInfo()` + `hasActiveEntitlement()`
  çağırır; sonucu WebView'e `localStorage.setItem('mishil_subscription_active', 'true'|'false')`
  olarak enjekte eder. Hak yoksa açık Mışıl Dadı sekmesi kapatılır (Pro kilit). Ağ/SDK hatasında
  durum değiştirilmez.

#### 🛠️ Fixed
- **Bebek profili %100 kalıcı:** `checkOnboardingState()` artık `mishil_baby_name` **ve**
  `mishil_baby_bdate` kayıtlıysa `#screen-onboarding` ekranını KESİNLİKLE açmaz; doğrudan ana
  ekrana geçer ve `mishil_onboarding_completed` bayrağını kendi kendine onarır. Hiçbir hata,
  çevrimdışı durum veya lisans senkronu bu iki kaydı sıfırlamaz.

#### 🔧 Chore
- Çevrimdışı paket yenilendi: `mobile/features/webview/offlineHtml.generated.ts` (`npm run bundle:offline`).
- Doğrulama kapısı: `tsc --noEmit` 0 hata, Jest 4/4 PASS.

## [4.10.1] - 2026-09-08
### 📱 Canlı Testflight Bulguları & Web Koruması (Build 19)

#### 🛠️ Fixed
- **Universal Viewport & Ekrana Sığma (Safe Area Flexbox):**
  - iOS Dynamic Island, çentik ve alt Home çizgisi olan tüm telefonlarda taşmayı önleyen 3 katmanlı kilitli Flexbox mimarisine geçildi (`position: fixed; inset: 0; height: 100dvh; overflow: hidden`).
  - Alt sekme çubuğu `env(safe-area-inset-bottom)` ile dinamik boşluk kazandı; `.screen-container` alt boşluğu `calc(76px + env(safe-area-inset-bottom))` ile içeriklerin çubuk arkasında kalması engellendi.
  - `.dadi-container` sohbet kutusu taşmaları önleyecek şekilde esnek `flex: 1 1 auto` ve responsive yükseklik kurallarıyla optimize edildi.
- **Mışıl Dadı AI Koçu — Tekrarları Önleyen Kademeli Klinik Akıl Yürütme Motoru:**
  - Basmakalıp tekrar yanıtları engellemek için `chat_history` bağlamını analiz eden, daha önce verilen tavsiyeleri hatırlayıp bir sonraki aşamaya geçen **kademeli pediatrik akıl yürütme (progressive clinical reasoning)** motoru entegre edildi.
  - 8 farklı klinik kategori (30 dk uyanma döngüsü köprüsü, gece beslenmesi seyreltme, 4. ay regresyonu, uykuya direnç krizleri, oda sıcaklığı/sirkadiyen ortam, günlük uyku süreleri, kundak/güvenli uyku, diş/atak) bebeğin haftasına göre parametrik olarak yapılandırıldı.
  - Soru şablonlarına art arda basılmasını önleyen `isDadiGenerating` durum kilidi, debounce mekanizması ve akış süresince butonları koruma kalkanı eklendi.
- **Canlı Web Koruması (Native-Only Download Wall & Admin Gate):**
  - Doğrudan `https://mishil-production.up.railway.app/app` linkine tarayıcıdan giren harici ziyaretçilere tam uygulama yerine şık, koyu obsidyen bir **İndirme Duvarı (Download Wall)** gösterilmesi sağlandı.
  - Yönetici/geliştirici önizlemesi için `?admin=mrtg.2591` URL anahtarı ve logoya 5 tıklama ile açılan gizli şifre kapısı devreye alındı (`localStorage.setItem('mishil_admin_gate', 'unlocked')`).
  - Mobil WebView içinde çalışan kullanıcılarda `window.__MISHIL_APP__.native` bayrağı sayesinde kilit otomatik olarak devre dışı bırakıldı.

## [4.10.0] - 2026-09-07
### 🐛 Dahili Test Bulguları — 9 Düzeltme (Build 18)

Kaynak: `projects/mishil/BUGFIX_PLAN_v4.10.0.md`. iOS + Android ayrı incelendi.

#### 🛠️ Fixed
- **İlk açılışta sahte "geçmiş veri" (5 aylık "Mina"):**
  - `loadBabyProfile()` ve `saveBabyProfile()` **hiç tanımlı değildi** — çağrıldıkları her yerde
    `ReferenceError` atıp dinamik render'ı durduruyor, sabit "Mina" HTML'i ekranda bırakıyordu.
    İkisi de yazıldı.
  - Tüm `|| 'Mina'` / `|| '2026-04-11'` fallback'leri kaldırıldı; `getBaby()` tek kaynak →
    kayıtlı profil yoksa `null`, ekranlar "bebek profili ekleyin" boş durumu gösteriyor.
  - Onboarding ve Ayarlar inputlarındaki ön-dolu `value="Mina"` / `value="2026-04-11"` silindi;
    ad + doğum tarihi zorunlu ve doğrulanıyor.
  - Analiz haftalık uyku grafiği artık **gerçek** son-7-gün kayıtlarından; sabit örnek veri silindi.
  - Sabit skor/yaş HTML değerleri (`%88`, `%38`, "4 Ay 12 Günlük") `—` ile başlayıp JS'ten doluyor.
- **Gelişim Atakları (Wonder Weeks) alanı geri geldi:** `renderWonderWeeksLeaps()` orphan'dı
  (konteyner + sekme + çağrı yoktu). Analiz sekmesine "🌱 Gelişim Atakları" bölümü + 10 kart eklendi,
  `renderAnalyticsView()` + `loadBabyProfile()` içine bağlandı.
- **Samsung'da kasma:** `androidLayerType` `"software"` → koşullu (`Android <9 software, 9+ hardware`);
  `.ambient-pulse` `blur(56px)` + `scale()` animasyonu `blur(40px)` + sadece `opacity`'ye indirildi
  (bulanık katmanın her karede yeniden rasterize edilmesi engellendi); `prefers-reduced-motion`
  altında dekoratif sonsuz animasyonlar durur.
- **Bazı sesler "yüklenemedi":** native ses motoru decode hatasında bir kez cache-bust ile tekrar
  deniyor; başarısız parça listede "KULLANILAMIYOR" işaretleniyor (sessiz kalma yok). NOT: 5 ses
  dosyası sunucuda şüpheli küçük — yeniden encode edilmeli (bkz. plan #4, sunucu işi).
- **Beslenme kaydı:** ana ekran "🍼 Beslenme" / "🚼 Alt" artık detay ekranını açıyor. Yapılı model:
  besleme türü (anne sütü / biberon-mama / biberon-ASS / katı), miktar (ml/g), süre (dk), not.
  Bez: tür (çiş / kaka / karma). Sabit `140 ml Anne Sütü` ön-dolu değeri kaldırıldı.
- **Sürüm notları statik + isim karmaşası:** native `Constants.expoConfig` → `window.__MISHIL_APP__`
  enjeksiyonu; Ayarlar rozeti + changelog modalı dinamik (`CHANGELOG_ENTRIES` + `renderChangelog()`).
  Sürüm şeması tek tip: `x.y.z (build N)`. `misil_onboarding_completed` → `mishil_onboarding_completed`
  (otomatik migrasyon). Sabit "v4.3.0 (Build 2026.08)" / "v4.3.1" ibareleri kaldırıldı.
- **iOS'ta haptik tamamen ölü:** `hapticPulse()` iki kez tanımlıydı; ikincisi (yalnız
  `navigator.vibrate` — iOS'ta yok) siliniyor, native köprü versiyonu kalıyor.
- **Apple App Store ITMS-90068 Uyumu (MinimumOSVersion >= 15.0):** `app.config.ts` içinde `expo-build-properties` altına `ios: { deploymentTarget: '15.1' }` yapılandırması eklendi. `core/mobile_compliance_checker.py` motoruna otomatik iOS deployment target denetimi entegre edildi.


#### 🔄 Changed — Onboarding / Paywall (plan #7, Seçenek A)
- Bedava katman kaldırıldı: onboarding "Atla ➔" butonu silindi. Abonelik zorunlu; bebek profili
  yoksa onboarding tekrar açılır (eski "Atla" ile geçmiş test kurulumları dahil).
- `activateTrialAndStart` native'de her zaman `MishilNative.purchasePackage()` → 3 günlük deneme
  mağazanın introductory offer'ı ile başlar; uygulama kendi "trial" state'i tutmaz.
- `finishOnboardingToApp` / `skipOnboarding` kullanımdan kaldırıldı.

#### 🧰 Tooling
- `offlineHtml.generated.ts` yenilendi. `RELEASE_READINESS.md` §5'e bulgular işlenecek.

#### 📦 Build
- Android `versionCode: 18` · iOS `buildNumber: 18` · `version: "4.10.0"`

## [4.9.1] - 2026-09-07
### 🎨 Ultra-Premium Vitrin Görselleri & App Store İnceleme Gönderimi (Waiting for Review)

#### ✨ Added
- **5 Adet Ultra-Premium Vitrin Görseli (1284 x 2778 px):** App Store (iPhone 6.5" / 6.7") ve Google Play için modern tasarım mühendisliği standartlarında, derin gece degrade zeminleri ve Türkçe tipografi ile üretildi:
  1. `1_Yapay_Zeka_Aglama_Analizi.png`: Akustik AI Ağlama Analizi ve Kolik/Gaz tespiti.
  2. `2_Beyaz_Gurultu_ve_Ninni_Mikseri.png`: 16+ Doğal Ses ve çoklu mikser arayüzü.
  3. `3_Huzurlu_Gece_Lambasi.png`: Melatonin dostu loş aydınlatma ve uyku zamanlayıcısı.
  4. `4_Sirkadiyen_Uyku_Takibi.png`: Pediatrik uyku skoru ve uyanıklık pencereleri.
  5. `5_Guvenlik_ve_Cevrimdisi_Kullanim.png`: %100 Çevrimdışı, sıfır reklam ve yerel gizlilik.
- Tüm görseller doğrudan `projects/mishil/kullanici/app_store/` ve `projects/mishil/kullanici/google_play/` altına yerleştirildi; masaüstüne tek bir geçici dosya bırakılmadı.

#### 🔄 Changed
- **Marka & Kurumsal Kimlik Düzeltmeleri:**
  - Uygulama adı App Store Connect ve yerelleştirme ayarlarında Türkçe karakterlerle **`Mışıl Baby: Bebek Uyku & Ses`** olarak eşitlendi.
  - Yayıncı ve telif hakkı ibaresi **`2026 Levitas Enterprise Intelligence & Technology`** olarak güncellendi.
- **Masaüstü Sıfır-Kirlilik Düzenlemesi:** Masaüstünde kalan `voltnet` tanıtım medyaları ait oldukları `projects/voltnet/assets/` dizinine taşındı; masaüstü tamamen arındırıldı.

#### 🚀 Release & Store Submission
- **Apple App Store Connect:**
  - Build 17 (`v4.9.0`) sürüme bağlandı.
  - App Review Information (İletişim Bilgileri: Murat Gürpınar, `mrtgurpinar@gmail.com`, şifresiz misafir modu erişimi) dolduruldu.
  - Yaş derecelendirmesi (4+), İçerik hakları ve Veri Toplama beyanları onaylandı.
  - Sürüm başarıyla **"Submit for Review"** yapılarak **`1.0 Waiting for Review` (İnceleme Bekliyor)** durumuna geçirildi.


## [4.9.0] - 2026-09-06
### 🔊 Native Arka Plan Ses Motoru — Kilitli Ekranda Ninni — Sürüm 16

WKWebView / Android WebView içindeki `<audio>` ve Web Audio API ekran kilitlenince
sesi durduruyordu (sentezlenen gürültüler arka planda **kesinlikle** çalmıyordu).
Uygulamanın çekirdek işlevi — bebek uyurken telefon cepteyken/kilitliyken ninninin
çalmaya devam etmesi — bu yüzden çalışmıyor ve App Store reddi riski taşıyordu.

#### ✨ Added
- **`features/audio/nativeAudioPlayer.ts` [YENİ]:** `expo-av` tabanlı native ses motoru.
  `Audio.setAudioModeAsync({ playsInSilentModeIOS: true, staysActiveInBackground: true, … })`
  ile sessiz modda ve arka planda kesintisiz döngü. Tek parça çalar, Railway'den stream eder.
- **Ses köprüsü mesajları:** WebView → native `AUDIO_PLAY {id,url}`, `AUDIO_STOP`,
  `AUDIO_TIMER {minutes}`, `AUDIO_VOLUME {value}`; native → WebView `AUDIO_STATE {playing,id,reason}`
  (mini player UI senkronu, timer/hata toast'ları).

#### 🔄 Changed
- **`app.html` ses motoru:** `togglePlayTrack` ve `setTimer`, `isNativeAudio()` doğruysa
  HTMLAudio yerine köprüye yönleniyor; tarayıcı önizlemesinde eski HTMLAudio yolu aynen
  duruyor. `MishilNative.audioBridge` bayrağı kill-switch (sorun olursa `false` → HTMLAudio).
- **`MishilUnifiedWebView.tsx`:** yeni ses mesajları işleniyor; `onLoad`'da `audioBridge = true`
  enjekte ediliyor; bileşen unmount'ında ses motoru kapatılıyor.

#### 🛟 Offline Fallback (R2) — %100 uzak URL bağımlılığı azaltıldı
- **`scripts/bundle-offline-html.js` [YENİ]:** `public/app.html` → gömülebilir TS modülü
  (`features/webview/offlineHtml.generated.ts`, repoya commit'li). `postinstall`'da ve
  `npm run bundle:offline` ile yenilenir; EAS build'de kaynak yoksa commit'li sürüm korunur.
- **`MishilUnifiedWebView.tsx`:** uzak sürüm 3 otomatik denemede de yüklenemezse artık
  boş/hata ekranı yerine **gömülü çevrimdışı sürüm** açılıyor; üstte "📴 Çevrimdışı sürüm"
  bandı, arka planda 20 sn'de bir uzak sürüme yeniden bağlanma denemesi, banda/butona
  dokununca manuel yeniden bağlanma. Bağlantı dönünce otomatik uzak sürüme geçiş.
- Gömülü sürüm `baseUrl` ile Railway köküne bağlı çalışır (fontlar, sesler, API şebeke
  dönünce çözülür). RevenueCat guard'ından bağımsız, ek native bağımlılık yok.

#### 🔧 RevenueCat Hizalama
- `FALLBACK_OFFERINGS` identifier'ları RevenueCat default paket kimlikleriyle hizalandı
  (`$rc_annual` / `$rc_monthly` / `$rc_lifetime`); `hasActiveEntitlement` önce panelde
  tanımlı `pro` entitlement'ını kontrol ediyor (genel yedek korunuyor).

#### ⚠️ Bilinen Sınır (takip)
- Android'de uzun (tüm gece) oturumlarda agresif OEM pil yöneticileri süreci öldürebilir.
  Tam çözüm: gerçek foreground service veya Expo SDK 52+ `expo-audio`. Bu sürümde
  `staysActiveInBackground` + `WAKE_LOCK` ile kısa/orta oturumlar hedefleniyor.
- Kilit ekranı oynatma kontrolleri (`MPNowPlayingInfoCenter` / media notification) bu
  sürümde yok — sonraki adım.

#### 📦 Build
- Android `versionCode: 16` · iOS `buildNumber: 16` · `version: "4.9.0"`

## [4.8.4] - 2026-09-06
### 💳 Abonelik Akışı Güvenlik Düzeltmeleri — Sürüm 15

Kod incelemesinde tespit edilen gelir sızıntısı ve mağaza politikası riskleri giderildi.

#### 🛠️ Fixed
- **"Satın Alımları Geri Yükle" herkese ücretsiz Pro veriyordu:** `restorePurchases()`
  hiç abonelik almamış kullanıcıda da başarıyla çözüldüğü, kod yalnızca `result.success`'e
  baktığı için Pro açılıyordu. Artık `hasActiveEntitlement(customerInfo)` ile
  `entitlements.active` / `activeSubscriptions` / tek seferlik işlemler kontrol ediliyor;
  aktif hak yoksa "geri yüklenecek abonelik bulunamadı" mesajı gösteriliyor.
- **`purchasePackage` her hata yolunda `success: true` dönüyordu:** `rawPackage` yoksa
  veya satın alma `userCancelled` dışında hata fırlatırsa fonksiyon sahte başarı
  döndürüp ödeme alınmadan Pro'yu açıyordu. Artık `no_package` / hata durumlarında
  `{ success: false }` dönüyor; sahte başarı yalnızca Expo `__DEV__` derlemesinde,
  yalnızca test amaçlı korunuyor. Üretimde ASLA ücretsiz Pro verilmiyor.
- **`PURCHASE_PACKAGE` / `RESTORE_PURCHASES` köprüleri:** WebView tarafında Pro,
  yalnızca `result.success && result.isActive` iken açılıyor; iptal sessiz geçiliyor,
  gerçek hata kullanıcıya bildiriliyor.
- **"Ömür Boyu" paketi her zaman sahte-başarı yoluna giriyordu:** `FALLBACK_OFFERINGS`
  içine `LIFETIME` girişi eklendi.
- **Tutarsız sabit fiyatlar:** `FALLBACK_OFFERINGS` yıllık fiyatı kart UI ile
  hizalandı (₺1.299,99 → ₺599,99); `selectPricingPlan` toast'undaki ömür boyu
  fiyatı düzeltildi (₺1.499.99 → ₺2.499.99). (Kalıcı çözüm: fiyatları Play Billing'den
  çekmek.)
- **Her açılışta abonelik toast'ı:** `onLoad` içindeki gereksiz `SUBSCRIPTION_RESULT`
  event dispatch'i kaldırıldı (durum zaten localStorage'da kalıcı).
- **Realtime WS sonsuz yeniden bağlanma:** `function-bun` servisi kapalıysa her 10 sn'de
  bir sınırsız denenen yeniden bağlanma, üstel geri çekilmeye (10s→5dk) ve 6 deneme
  limitine bağlandı; açık/bağlanıyor durumda çift soket engellendi.

#### 🍏 iOS Yayın Hazırlığı
- **`ios.buildNumber` eklendi** (`15`, Android `versionCode` ile hizalı; sürüm ve
  build numarası `app.config.ts` içinde tek yerden — `APP_VERSION` / `BUILD_NUMBER`).
- **`ITSAppUsesNonExemptEncryption: false`** eklendi — her TestFlight/App Store
  yüklemesinde çıkan ihracat uyumluluğu sorusunu otomatik geçer.
- `eas.json`: `cli.appVersionSource: "local"`, production `autoIncrement: false`,
  `channel` alanları (preview/production) eklendi.

#### 🛡️ Production Build Guard
- `app.config.ts`: `APP_ENV=production` iken RevenueCat anahtarı mock ise derleme
  **hata verip durur**. Sessiz "satın alma çalışmayan yayın" senaryosu artık
  build zamanında yakalanıyor. (Çözüm: `EXPO_PUBLIC_REVENUECAT_*` EAS secret'larını tanımla.)

#### 🧰 Tooling
- `core/mobile_compliance_checker.py` fiyat linti artık tekil kaynak `public/app.html`
  dosyasını da tarıyor (önceden yalnızca `mobile/app` ve `mobile/features`).
- jest yapılandırması: yalnızca `tests/**/*.test.ts` çalıştırılıyor; `e2e-flow.spec.ts`
  (Maestro YAML fixture, jest testi değil) ayrıldı → `npm test` yeşil (4/4).
- **`RELEASE_READINESS.md`** eklendi — Google Play + App Store için faz faz kusursuz
  yayın planı, cihaz test matrisi, bilinen riskler (özellikle iOS arka plan sesi) ve
  rollback planı.

#### 📦 Build
- Android `versionCode: 15` · iOS `buildNumber: 15` · `version: "4.8.4"` (minSdk 26 / targetSdk 36 korunuyor)

## [4.8.3] - 2026-09-06
### 🎯 Android Hedef API 36 (Android 16) — Google Play 2026 Zorunluluğu — Sürüm 14

#### 🔄 Changed
- **`targetSdkVersion` / `compileSdkVersion` 35 → 36:** 31 Ağustos 2026 itibarıyla Google
  Play yeni uygulama ve güncellemeler için **API 36 (Android 16)** hedefini zorunlu
  kıldığından, 4.8.2'deki geçici 35 kararı geri alındı. `android.suppressUnsupportedCompileSdk: '36'`
  bayrağı korunuyor.
- **`minSdkVersion: 26` (Android 8.0) korunuyor:** 4.8.2'de eklenen taban; Android 7.x
  cihazların Railway'in Let's Encrypt ISRG Root X1 köküne güvenmemesi kaynaklı
  "hiç açılmıyor" sorununu kapatır.
- **4.8.2 WebView dayanıklılık yaması aynen geçerli:** render süreci çökme kurtarma,
  gerçek retry akışı, `androidLayerType: "software"`, watchdog vb. değişmedi.
- `core/mobile_compliance_checker.py` asgari hedef eşiği tekrar 36'ya çekildi.

#### 📦 Build
- Android `minSdkVersion: 26`, `targetSdkVersion: 36`, `compileSdkVersion: 36`, `versionCode: 14`
- `version: "4.8.3"`

## [4.8.2] - 2026-09-06
### 📱 "Bazı Android Telefonlarda Açılmıyor" Dayanıklılık Yaması — Sürüm 13

Uygulama tamamen uzak URL'e (`app` sayfası, Railway) bağımlı tek WebView mimarisinde
çalıştığı için; şebeke/TLS hatası, Railway soğuk başlangıcı veya WebView render
sürecinin çökmesi durumunda kullanıcı boş/siyah ekranda kalıyordu. `MishilUnifiedWebView`
sıfırdan dayanıklı hale getirildi.

#### 🛠️ Fixed
- **Boş/siyah ekran (hata durumu hiç görünmüyordu):** `onLoadEnd` her koşulda (hata dahil)
  `error` state'ini sıfırladığı için hata ekranı asla çizilmiyordu. Artık yalnızca
  gerçekten başarılı yükleme (`onLoad`) "hazır" sayılıyor; hatalı yükleme hata ekranını
  koruyor.
- **WebView render süreci çökmesi → uygulama kapanması:** `onRenderProcessGone` (Android)
  ve `onContentProcessDidTerminate` (iOS) yakalanıp otomatik yeniden yükleme yapılıyor.
  Düşük RAM'li cihazlarda OOM kaynaklı kapanma engellendi.
- **GPU kaynaklı boş WebView:** `androidLayerType` `"hardware"` → `"software"` alındı;
  belirli Android GPU'larında donanım katmanının boş ekran vermesi giderildi.
- **Railway soğuk başlangıcı / zayıf şebeke:** Ana çerçeve hatasında kademeli gecikmeyle
  (2.5s → 5s → 7.5s) 3 kez sessiz otomatik yeniden deneme; ardından kullanıcıya **"Tekrar Dene"**
  butonlu hata ekranı gösteriliyor (önceki sürümde hiç retry yoktu).
- **Sonsuz spinner:** 25 sn içinde yüklenemeyen sayfa için watchdog zamanlayıcı eklendi.
- **Boş popup pencereleri:** `setSupportMultipleWindows={false}` ile harici bağlantıların
  dokunuşu yutan boş pencere açması engellendi.
- `mixedContentMode="never"` açıkça ayarlandı.

#### 🎯 Changed — Android Derleme Hedefi Sadeleştirildi
- **`targetSdkVersion` / `compileSdkVersion` 36 → 35:** Google Play güncel şartı API 35'tir
  (Android 15); 36'ya zorlamak Expo SDK 51 / AGP 8.3 üzerinde eski OS sürümlerinde
  sınıf-yükleme (`NoSuchMethodError` / `VerifyError`) çökme riski taşıyordu.
  `buildToolsVersion: '35.0.0'`, suppress bayrağı 35'e alındı.
- **`minSdkVersion: 26` (Android 8.0) sabitlendi:** Android 7.x cihazlar Railway'in
  kullandığı Let's Encrypt ISRG Root X1 köküne güvenmediği için HTTPS el sıkışması
  yapamıyor ve tek WebView mimarisinde uygulamayı hiç açamıyordu. Bu OS tabanı
  desteklenen cihazlar için sorunu kökten kaldırır (Android 7.x pazar payı < %1.5).

#### 📦 Build
- Android `minSdkVersion: 26`, `targetSdkVersion: 35`, `versionCode: 13`
- `version: "4.8.2"`

## [4.8.1] - 2026-09-06
### 🔓 Geliştirici Kilit Ekranının Kaldırılması & Google Play Yayına Hazırlık — Sürüm 12

#### 🛠️ Fixed — Mağaza Blokajı Kaldırıldı
- **`levitasPinOverlay` (Levitas Developer Mode) tamamen söküldü:** `public/app.html` en altındaki `display: flex` / `z-index: 999999` geliştirici PIN modalı, `checkDevPin()` fonksiyonu ve `pinError` / `devPinInput` elemanları silindi. Uygulama ilk açılışta sıfır gecikmeyle doğrudan ana sayfa / ninni oynatıcıya açılıyor.
- **Bypass kalıntıları temizlendi:** `app.html` içindeki `BYPASS_PIN` mesaj dalı ve `ReactNativeWebView` `load` listener'ı (`levitas_dev_auth` sessionStorage yazımları dahil) kaldırıldı.
- **`MishilUnifiedWebView.tsx` sadeleştirildi:** `onLoadEnd` içindeki `levitasPinOverlay` DOM manipülasyonu ve `levitas_dev_auth` enjeksiyonu çıkarıldı; yalnızca native bridge sinyali (`isNative`) ve `SUBSCRIPTION_RESULT` köprüsü bırakıldı.
- **Google Play "Broken Functionality" reddi riski giderildi:** İnceleme ekibi artık şifre ekranıyla karşılaşmadan uygulamayı test edebilir.

#### 📦 Build
- Android `versionCode: 12`
- `version: "4.8.1"`

## [4.8.0] - 2026-09-06
### 🏗️ Tekil Kod Tabanı (Single Source of Truth) Mimarisi — Sürüm 11

#### 🔄 Changed — Kalıcı Mimari Dönüşümü
- **Ayrı kod tabanı çalışması sona erdirildi:** Web (Railway `app.html`) ve mobil (React Native) arayüzlerinin birbirinden bağımsız geliştirilmesi problemi kalıcı olarak çözüldü.
- **`projects/mishil/public/app.html` artık tek kaynak:** Tüm ekranlar (SweetSpot, Analiz & Günlük 📊, Mışıl Dadı 👵, Sakinleştirici Sesler 🎵, Ayarlar ⚙️) yalnızca burada yaşıyor ve hem Railway canlı ortamında hem de Google Play uygulamasında **aynı anda** güncelleniyor.

#### ✨ Added — Yeni Bileşenler
- **`components/MishilUnifiedWebView.tsx` [YENİ]:** Tekil WebView native köprü bileşeni oluşturuldu. Railway canlı URL'ini (`https://mishil-production.up.railway.app/app`) donanımsal ivmelendirmeli, 60fps tam ekran olarak sunar.
- **JS Bridge (Native ↔ Web Köprüsü) [YENİ]:** `app.html` içine tam entegre edildi:
  - `HAPTIC` → `expo-haptics` native titreşim
  - `PURCHASE_PACKAGE` → RevenueCat / Google Play IAP
  - `RESTORE_PURCHASES` → Satın alım geri yükleme
  - `BYPASS_PIN` / `load` event → Geliştirici PIN overlay'i native uygulamada otomatik geçer
- **`hapticPulse()` Global Fonksiyonu [YENİ]:** Tüm butonlarda kullanılan haptik bridge + Web Vibration API fallback.
- **IAP Köprüsü `activateTrialAndStart()` [GELİŞTİRİLDİ]:** Native uygulamada Google Play IAP tetikler; tarayıcıda localStorage fallback çalışır.

#### 🛠️ Fixed — Düzeltilen Sorunlar
- Mağazadaki uygulama (Sürüm 10) ile Railway canlı arayüzü arasındaki görsel fark kalıcı olarak kapandı.
- Analiz & Günlük sekmesi, Bento grafikleri, Segmented SweetSpot Switcher ve Mışıl Dadı entegre ağlama çubuğu artık mobil uygulamada tam görünüyor.

#### 📦 Build
- Android `versionCode: 11`
- `version: "4.8.0"`


### 🛡️ Google Play Store API 36 (Android 16) & Play Billing Library 8+ Uyumluluğu
- **💳 Play Billing Library 8.0.0+ Geçişi:** `react-native-purchases` paketi `^9.0.0` sürümüne yükseltilerek Google Play Store'un zorunlu kıldığı PBL 8.0.0+ faturalandırma şartı karşılandı.
- **🎯 Target SDK 36 (Android 16):** `targetSdkVersion: 36`, `compileSdkVersion: 36` ve `buildToolsVersion: '36.0.0'` yapılandırması tamamlandı; `eas.json` Android derleme imajı `"image": "latest"` yapılarak Android 16 desteği sağlandı.
- **🩹 Expo Modules Core SDK 36 Null-Safety Yaması:** Android 16'da `requestedPermissions` alanının nullable olması nedeniyle Kotlin derleyicisinde oluşan `PermissionsService.kt:166:36` hatası için otomatik `patch-expo-permissions.js` postinstall yaması entegre edildi.
- **📦 Üretim Paketi Derlemesi:** Android `versionCode: 6` (Sürüm: `4.7.0`) üretim App Bundle (`.aab`) paketi Expo EAS bulutunda derlendi ve yerel `projects/mishil/mobile/misil-baby.aab` dosyasına indirildi.

## [4.7.0] - 2026-09-05
### 🚀 Mobil Çekirdek Deneyim, Mışıl Dadı AI & Ses/Onboarding Revizyonu
- **👶 İlk Açılış Onboarding Akışı:** `index.tsx` içindeki doğrudan `/(tabs)/home` yönlendirmesi düzeltildi. Kayıtlı bebek profili bulunmadığında kullanıcı otomatik olarak `/(onboarding)/baby-profile` ekranına yönlendirilerek ilk kurulum güvenceye alındı.
- **🎵 18 Gerçek Stüdyo Kaydı & Canlı Ses CDN Düzeltmesi:** Ses URL'lerindeki sahte `cdn.mishil.app` adresi kaldırılarak canlı Railway sunucu rotası (`https://mishil-api-production.up.railway.app/sounds/`) bağlandı; 18 stüdyo kaydı ve kategori filtreleme çipleri (`Tümü`, `Ninniler`, `Anne Karnı`, `Pışpış & Gürültü`, `Doğa Sesleri`) entegre edildi.
- **👵 Mışıl Dadı AI Sekmesi (`coach.tsx`):** Menü sekmelerine Google Gemini destekli Mışıl Dadı Pediatrik Danışman arayüzü eklendi; hızlı soru hapları ve akıllı offline pediatrik yanıt motoru inşa edildi.
- **🌱 Wonder Weeks & Dinamik Klinik Gelişim Takibi:** 10 Büyük Zihinsel Sıçrama veritabanı, bebeğin haftalık takvimine göre fırtına zirvesi uyarıları, % dolum çubuğu ve Mışıl Dadı klinik tavsiyesi ana sayfa bento kartı olarak eklendi.
- **👨‍👩‍👧 Aileye Katıl (Kod Gir) Modalı:** Ayarlar sekmesine eş ve dadıların 6 haneli kod girerek bebeğe bağlanabileceği `JoinFamilyModal` ve rol seçimi entegre edildi.
- **🔄 Çevrimdışı Kuyruk & Açık Eşitleme Geri Bildirimi:** "2 çevrimdışı kayıt bekliyor" banner'ı interaktif hale getirildi; senkronizasyon sırasında yükleme durumu, başarılı/başarısız Alert diyalogları ve takılı kalan kayıtları tek tıkla temizleme imkanı (✕ butonu) eklendi.
- **📱 Sürüm Yükseltmesi:** `version: 4.7.0`, Android `versionCode: 5` olarak güncellendi.

## [4.6.2] - 2026-08-23
### 📱 PWA & Apple Touch Icon & Favicon Standardizasyonu
- **🍏 Apple iOS Safari Ana Ekrana Ekleme:** `apple-touch-icon.png` (180x180 px) ve ilgili iOS Web Clip meta etiketleri bağlandı.
- **🤖 Android Chrome & PWA Manifest:** `manifest.json`, `icon-192.png` ve `icon-512.png` PWA ikonları eklendi.
- **🌐 Web Sekmesi Favicon:** `favicon.ico`, `favicon-32x32.png` ve `favicon-16x16.png` FastAPI doğrudan rotalarıyla servis edildi.

## [4.6.1] - 2026-08-23
### 👶 Konsept 2 (Uyuyan Bebek & Ay) Master İkon Entegrasyonu
- **🎨 Resmi İkon Belirlendi:** Kullanıcı tercihiyle Concept 2 (Bulut Üzerinde Uyuyan Bebek ve Ay) tüm mobil (`icon.png`, `adaptive-icon.png`, `splash.png`, `favicon.png`) ve mağaza varlıklarına (`icon_512.png`, `ios_icon_1024.png`) işlendi.

## [4.6.0] - 2026-08-23
### 👑 Fiyatlandırma & Paywall Mimarisi (Seçenek B) & Evrensel Master İkon
- **❌ "Ücretsiz Temel" Seçeneği Kaldırıldı:** Gelir kaybını önlemek ve dönüşümü artırmak için onboarding paywall'ından ücretsiz devam butonu kaldırıldı.
- **👑 3'lü Sağlam VIP Fiyatlandırma (Seçenek B):**
  - **Yıllık VIP:** ₺599.99 / Yıl (3 Gün Ücretsiz Deneme Dahil • Aylık ₺49.99 • %67 Tasarruf)
  - **Aylık VIP:** ₺149.99 / Ay (Esnek Aylık Plan)
  - **Ömür Boyu VIP (Aile):** ₺2.499.99 (Tek Seferlik • Tüm Aile ve Gelecek Bebekler Dahil Sonsuz Erişim)
- **🎨 Evrensel Master İkon Standardı (Lüks Altın Hilal & Yıldız Tozu):** Tüm temas noktalarında (`icon.png`, `adaptive-icon.png`, `splash.png`, `favicon.png`, `icon_512.png`, `ios_icon_1024.png`) tek tip lüks ikon üretildi.

## [4.5.1] - 2026-08-23
### 🔐 Şifreli Geliştirici Geçidi (PIN-Protected Developer Gateway)
- **🔑 Geliştirici Önizleme Modu (`GET /app` & `GET /preview`):** Canlı geliştirme ve test kontrolleri için PIN korumalı tam çalışan uygulama sayfası (`public/app.html`) entegre edildi.
- **🛡️ `levitas2026` Şifre Doğrulaması:** `sessionStorage` üzerinden yetkilendirme ile izinsiz ziyaretçiler engellenirken, geliştiricinin kesintisiz test yapabilmesi sağlandı.

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
