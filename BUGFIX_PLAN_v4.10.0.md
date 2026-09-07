# Mışıl Baby — Test Bulguları & Çözüm Planı (hedef v4.10.0 / build 18)

> Kaynak: 2026-09-07 dahili test geri bildirimi (build 16/17).
> Kapsam: tek WebView mimarisi — UI `projects/mishil/public/app.html`, native köprü
> `mobile/components/MishilUnifiedWebView.tsx` + `mobile/features/audio/nativeAudioPlayer.ts`.
> iOS ve Android farkları her maddede işaretli.

---

## 0. Bulgu Özeti

| # | Sorun | Kök neden | Platform | Efor | Risk |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | İlk açılışta sahte "geçmiş veri" (5 aylık "Mina") | Her yerde `\|\| 'Mina'` / `\|\| '2026-04-11'` fallback + sabit HTML + sabit haftalık grafik | Ortak | M | Orta |
| 2 | Gelişim atakları / Wonder Weeks alanı yok | `renderWonderWeeksLeaps()` orphan — konteyner + sekme + çağrı silinmiş | Ortak | M | Düşük |
| 3 | Samsung'da kasma | `androidLayerType="software"` + ağır CSS (blur/oklch/aura animasyonları) | **Android** | S | Orta (boş ekran regresyonu) |
| 4 | Bazı sesler "yüklenemedi" | 5 ses dosyası şüpheli küçük (81–432 KB), muhtemel truncate/kötü encode; iOS AVPlayer daha katı | Ortak (**iOS ağır**) | S+sunucu | Düşük |
| 5 | Beslenme quick-log: ne/nasıl girilemiyor | Ana ekran "🍼 Beslenme" → `quickLog()` düz string yazıyor; yapılı alan (`ml`, tür) yok | Ortak | M | Düşük |
| 6 | Rutinler analize yansımıyor, yüzeysel | Model `{type,title,detail:string,time,durationMins}` — toplulaştırma yok; haftalık grafik sabit | Ortak | L | Düşük |
| 7 | "Atla" → bedava erişim, deneme başlıyor mu belirsiz | `skipOnboarding()` sadece flag yazıp uygulamayı açıyor; paywall/trial/abonelik kilidi yok; [4.6.0]'da kaldırılan bedava katman geri gelmiş | Ortak | M | **Karar gerek** |
| 8 | Sürüm notları statik + isim karışıklığı | Settings rozeti + changelog modalı sabit HTML (v4.3.0/v4.3.1); native sürümü WebView'e geçmiyor; "Mina/Mışıl/Mishil/misil" ve v4.3.x/Build 2026.08/4.9.0(17) karışık | Ortak | S/M | Düşük |
| 9 | iOS'ta haptik tamamen ölü | `function hapticPulse()` **iki kez** tanımlı (satır 2276 native köprü + satır 3515 sadece `navigator.vibrate`); ikincisi kazanıyor, iOS'ta `vibrate` yok | **iOS** | S | Düşük |

---

## 1. Ortak (app.html) düzeltmeleri

### 1.1 Sahte veri temizliği (#1)
- **Onboarding inputları:** `app.html:1320` `value="Mina"` ve `app.html:1324` `value="2026-04-11"` kaldırılacak — yalnızca `placeholder`.
- **Tek kaynak:** `getBaby()` yardımcı ekle — `mishil_baby_bdate` yoksa `null` döner.
  ```js
  function getBaby() {
    const bdate = localStorage.getItem('mishil_baby_bdate');
    if (!bdate) return null;
    return { name: localStorage.getItem('mishil_baby_name') || 'Bebeğiniz', bdate };
  }
  ```
- **Tüm `\|\| 'Mina'` / `\|\| '2026-04-11'` fallback'leri kaldır** (satırlar: 2509, 2631, 2835, 2836, 3559 ve SweetSpot/wake-window hesapları). Baby `null` ise:
  - Ana ekran, Analiz, Gelişim: "Önce bebek profili ekleyin" boş durumu (CTA → onboarding adım 1).
  - Hiçbir skor/tarih/pencere hesaplanmaz.
- **Sabit HTML değerleri** → `—` yap, JS doldursun: `baby-header-subtitle` (1499), `acc-profile-summary` (1793), gelişim skoru kartı (1610, 1613, 1636–1639), rapor skoru (1418), `report-baby-title` (1412 "Mina İçin" → JS), `onboarding-trial-end-text` (1482).
- **Haftalık grafik (`app.html:3138–3145`):** sabit `weeklyData` kaldırılacak; son 7 günün `activeRoutines` uyku loglarından gün gün hesapla, veri yoksa 0 (boş bar) + "Kayıt biriktikçe dolar" notu.
- **Onboarding'de kayıt garantisi:** `nextQuizStep` yerine adım 1'den çıkarken adı+tarihi anında `localStorage`'a yaz + boşsa ilerletme.

### 1.2 Gelişim atakları alanını geri getir (#2)
- `WONDER_WEEKS_LEAPS` DB + `renderWonderWeeksLeaps()` + `.leap-item-card` CSS **duruyor** — sadece görsel katman silinmiş.
- `view-analytics` içine "🌱 Gelişim & Wonder Weeks" bölümü ekle:
  - `#leaps-hero-title`, `#leaps-hero-overall-percent`, `#leaps-hero-desc`, `#leaps-hero-progress-bar`, `#leaps-early-override-badge`
  - `#leaps-list-container` (10 kart buraya render edilir)
- `renderAnalyticsView()` içine `renderWonderWeeksLeaps()` çağrısı ekle; onboarding bitince ve `toggleEarlyLeap/resetToAutoLeap` sonrası da çağır.
- Ana ekrana küçük "aktif atak" özet kartı (mevcut sabit "%88 • 4. Atak" kartını dinamikleştir, #1 ile birlikte).
- 6. sekme açma; 5-core nav korunur.

### 1.3 Beslenme/rutin yapılı giriş (#5)
- Rutin modeli değişecek (serbest `detail` string yerine yapılı alanlar):
  ```js
  // feeding
  { type:'feeding', method:'breast'|'bottle_formula'|'bottle_ebm'|'solid', amountMl:Number|null, durationMin:Number|null, note:'' }
  // diaper
  { type:'diaper', kind:'wet'|'dirty'|'mixed' }
  // sleep (mevcut) { startTs, endTs, durationMins }
  ```
- Ana ekran "🍼 Beslenme" / "🚼 Alt" hızlı butonları artık **mini bottom-sheet** açar (tek dokunuş + ~2 alan), "Hızlı kaydet" kısayolu kalır.
- Detaylı modaldaki sabit `value="140 ml Anne Sütü"` (`app.html:2151`) kaldırılacak → placeholder.
- Eski serbest-metin kayıtlar için tek seferlik migrasyon (best-effort parse `"140 ml"` → `amountMl`).

### 1.4 Analitik derinleştirme (#6) — ayrı milestone
- #1.3 yapılı model üstüne günlük rollup: toplam uyku, beslenme sayısı + toplam ml + ortalama aralık, alt bezi (tür kırılımı), en uzun uyku, gece uyanma.
- Haftalık trend (uyku + beslenme ml) gerçek veriden.
- Mışıl Dadı prompt'una gerçek sayılar beslenir (`calculateWakeWindow` payload'una rollup ekle).
- **Not:** bu bir özellik; v4.10.0'a temel rollup, gelişmişi v4.11.0.

### 1.5 Sürüm & isimlendirme (#8)
- **Native → WebView sürüm enjeksiyonu:** `MishilUnifiedWebView.tsx` `injectedJavaScriptBeforeContentLoaded` ile:
  ```js
  window.__MISHIL_APP__ = { version: '<Constants.expoConfig.version>', build: <buildNumber|versionCode>, platform: '<ios|android>' };
  ```
- `app.html`: Settings rozeti (`1960`) + changelog modal başlığı (`2073`) bu objeden okur (`APP_META` fallback ile).
- **Changelog içeriği dinamik:** Railway'de `GET /changelog.json` (ya da app.html'e gömülü `CHANGELOG_ENTRIES` dizisi) — `projects/mishil/CHANGELOG.md` ile senkron. Modal bu listeyi render eder.
- **İsim standardı:** tüm kullanıcı metinlerinde "Mışıl Baby". `localStorage` anahtarı `misil_onboarding_completed` → `mishil_onboarding_completed` (migrasyon: eski değeri oku, yeniye yaz). Maestro `tests/e2e-flow.spec.ts` `appId: com.mishil.app` → `com.levitas.misilbaby` (veya dosyayı sil, stale).
- Sürüm şeması: yalnızca `x.y.z (build N)` — "Build 2026.08" / "v4.3.1" ibareleri kaldırılacak.

---

## 2. Android'e özel

### 2.1 Samsung kasma (#3)
- `MishilUnifiedWebView.tsx:415` `androidLayerType="software"` → **`"hardware"`**.
  - Boş-ekran regresyon korkusu için koşullu:
    ```tsx
    androidLayerType={Platform.OS === 'android' && Number(Platform.Version) < 28 ? 'software' : 'hardware'}
    ```
    (Android <9 eski WebView'de donanım katmanı boş ekran veriyordu; 9+ sorunsuz.)
- `app.html` GPU maliyetini düşür:
  - `backdrop-filter` / `filter: blur()` animasyonlu öğeleri (nefes alan ay aurası, border-beam, blur→focus geçişleri) `@media (prefers-reduced-motion: reduce)` altında sadeleştir.
  - Sonsuz `@keyframes` sayısını azalt; `will-change` yalnızca aktif animasyonda.
  - `oklch()` renkleri hex fallback ile ver (eski WebView + bazı GPU'larda pahalı/parse-fail).
- **Test:** düşük-orta Samsung (A serisi, Exynos) + eski GPU profilinde boş-ekran kontrolü tekrar.

### 2.2 Haptik
- `navigator.vibrate` Android'de çalışıyor ama native `expo-haptics` impact stilleri (#9 fix ile) daha iyi — Android'de de köprüye dönülünce kazanç.

---

## 3. iOS'a özel

### 3.1 Haptik tamamen ölü (#9)
- `app.html`'deki **ikinci** `function hapticPulse()` (`~3515`, sadece `navigator.vibrate`) silinecek; birinci tanım (`~2276`, `ReactNativeWebView.postMessage({type:'HAPTIC'})` + `navigator.vibrate` fallback) kalacak.
- Doğrula: `MishilUnifiedWebView.tsx` `onMessage` `HAPTIC` dalı `expo-haptics` çağırıyor (var). iOS'ta artık tüm buton/etkileşim haptikleri çalışır.

### 3.2 Ses "yüklenemedi" (#4 — iOS ağırlıklı)
- iOS AVPlayer, VBR/bozuk başlıklı/çok kısa MP3'leri reddeder; Android ExoPlayer daha toleranslı.
- Şüpheli dosyalar (sunucuda `HEAD` ile ölçüldü): `shush_5s` 81 KB, `placenta_flow` 103 KB, `hairdryer_calm` 137 KB, `fan_drone` 179 KB, `mozart_432hz` 432 KB.
- **Sunucu işi:** bu 5 dosyayı (gerekirse hepsini) yeniden encode et — CBR 128–192 kbps, 44.1 kHz, geçerli ID3, ≥30 sn dikişsiz loop. Her dosyayı `ffprobe` ile doğrula (süre, bitrate, hata yok).
- **Kod (native):** `nativeAudioPlayer.playSound` decode hatasında 1 kez cache-bust (`?v=<ts>`) ile tekrar dene; 2. hatada `reason:'error'`. `AUDIO_STATE` toast'ı "ağ" vs "dosya" ayırsın.
- **Kod (app.html HTMLAudio yolu — tarayıcı önizleme):** `aud.addEventListener('error', …)` → o parçayı listede "kullanılamıyor" işaretle, sessiz kalma.

---

## 4. Karar gereken: onboarding / paywall modeli (#7)

`skipOnboarding()` şu an: flag yaz + uygulamayı aç. Paywall yok, trial yok, hiçbir özellik abonelik arkasında değil. [4.6.0] changelog'da "Ücretsiz Temel kaldırıldı" deniyordu → bu bir regresyon.

**Seçenek A — Bedava katman yok (önerilen, [4.6.0] ile uyumlu, gelir):**
- "Atla ➔" kaldırılır. Onboarding paywall zorunlu.
- `activateTrialAndStart` her zaman `MishilNative.purchasePackage()` → RevenueCat 3 günlük intro trial'ı **mağaza** başlatır (uygulama "trial başladı" toast'ı atmaz; gerçek durum `customerInfo`'dan).
- `main-app-screen` yalnızca `mishil_subscription_active === 'true'` (yalnız gerçek `SUBSCRIPTION_RESULT`/`grantProInWebView` yazar) iken görünür.
- Settings "3 Günlük Ücretsiz Deneme (Aktif)" (`1876`) → `customerInfo.entitlements.active.pro.periodType` ('trial'/'normal') + bitiş tarihinden dinamik.

**Seçenek B — Sınırlı bedava katman:**
- "Atla" → bedava mod: 3 ses, coach yok, analiz yok; Settings'ten paywall'a erişim; rozet "Ücretsiz".
- Özellik kilit matrisi + `isPro()` guard'ları app.html'e.

> Kullanıcı A/B seçmeli. Hangisi olursa olsun: "deneme başladı mı" sorusu **RevenueCat `customerInfo`** ile yanıtlanır; uygulama kendi "trial" state'i tutmaz.

---

## 5. Sürüm & sıra

| Milestone | İçerik | Not |
| :-- | :-- | :-- |
| **v4.10.0 / build 18** | #1, #2, #3, #4 (kod+sunucu), #5 (yapılı model + mini-sheet), #8, #9 | Test-blocker düzeltmeleri |
| v4.10.x | #7 (karar sonrası), #6 temel rollup | |
| v4.11.0 | #6 gelişmiş analitik, Wonder Weeks bildirimleri, kilit-ekranı medya kontrolleri | |

## 6. Doğrulama (her milestone)
- `cd projects/mishil/mobile && npx tsc --noEmit -p tsconfig.json`
- `node node_modules/jest/bin/jest.js`
- `python ../../../core/mobile_compliance_checker.py projects/mishil/mobile`
- `npm run bundle:offline` → `offlineHtml.generated.ts` commit (app.html değiştiği için ZORUNLU)
- app.html script sözdizimi: `node --check` (inline `<script>` bloğu)
- Cihaz: Samsung (A serisi) kasma yok · iOS haptik çalışıyor · 18 ses de çalıyor · yeni bebekte sıfır geçmiş veri · Gelişim sekmesi dolu · "Atla" davranışı karara uygun · Settings sürümü = `4.10.0 (18)`

## 7. Dokümantasyon
- `projects/mishil/CHANGELOG.md` + vault `CHANGELOG.md` (v7.x) + `00_HAFIZA_VE_SISTEM.md` + `01_Features/Surdurulebilir_Mobil_Muhendislik_ve_Google_Play_API.md` güncellenecek (sonuncusu şu an eski: targetSdk 35, eski fiyatlar, PIN ibaresi).
- `RELEASE_READINESS.md` §5'e bu bulgular "Faz 2 test çıktısı" olarak işlenecek.

---
_Hazırlandı: 2026-09-07 · Temel alınan sürüm: v4.9.0 build 17_
