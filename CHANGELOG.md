# Changelog - Mishil

Tüm önemli değişiklikler bu dosyada belgelenecektir.

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
