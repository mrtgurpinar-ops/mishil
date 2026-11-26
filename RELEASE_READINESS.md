# Mışıl Baby — Kusursuz Yayın Hazırlık Planı (v4.58.1 Railway Canlıda • Google Play Build 75 Production COMPLETED • Apple App Store v4.58.0 Build 75 WAITING_FOR_REVIEW)

> **🧪🧭 `v4.58.1` Kurucu Kokpiti RevenueCat Paywall A/B Testi Komuta Merkezi & 10 Adımlı Onboarding (`0➔9`) Revizyonu (2026-11-26 — Railway Canlıda • 🟢 Yeni Native EAS Build Gerekmez):**
> - **A/B Testi Komuta Merkezi (`#abExperimentCommandCard` & `_build_ab_experiment_comparison`):** Sekme 2'ye otonom kazanan teşhis bandı (`#abWinnerBadge`), 3 yan yana varyant kartı (`🔥 Grup A: İlk Ay %67 İndirim ₺49,99 ➔ ₺149,99/ay`, `🎁 Grup B: İlk Ay Ücretsiz 30G ₺0 ➔ ₺149,99/ay`, `👑 Yıllık VIP Çıpa ₺599,99/Yıl`) ve 9 sütunlu A/B karşılaştırma tablosu (`#abExperimentTbody` — Tarihsel 7G Deneme & Kodlu VIP satırı dahil) eklendi; Sol Menü (`#sideKpiAbTest`), Üst Dönüşüm Hunisi (`#convAbTestPill`), Sekme 1 ve Sekme 3 alt barlarına `jumpToAbExperiment()` kısayolları bağlandı.
> - **30 Günlük Ücretsiz Deneme (`free_trial_1m`) Köprü Algılaması & 10 Adımlı Onboarding (`Adım 0➔9` + 7. Kart Öneri C):** `_is_30d_free_trial_window` ile 30G ücretsiz denemeler otomatik sınıflandırıldı; `app.html` içinde `onb_step7_quick_chip_used` ve `ab_a_*` / `ab_b_*` sinyalleri devreye alındı (`Claude Code CLI task-906: structurally consistent`, `13/13 pytest PASS`, `11/11 suite / 86 Jest PASS`).

> **🔥🎁 `v4.58.0` (`Build 75`) Evrensel A/B Paywall Teklif Motoru (`İlk Ay %67 İndirim • ₺49,99` vs `İlk Ay Ücretsiz • ₺0`) & Yeni Onboarding Sıralaması (2026-11-26):**
> - **Evrensel A/B Teklif Motoru (`revenuecat.ts`, `MishilUnifiedWebView.tsx`, `metaAppEvents.ts`, `public/app.html`):** StoreKit 2 ve Google Play Billing v7 üzerinde RevenueCat Experiments'tan gelen `paid_intro` (`İlk Ay %67 İndirim • ₺49,99`) ve `free_trial` (`İlk Ay Ücretsiz • ₺0`) tekliflerini otomatik tanıyan, 3 dilde (`TR/EN/DE`) Paywall kartlarını dinamik güncelleyen ve ücretsiz denemelerde Meta ROAS şişmesini önlemek için `StartTrial` (`amount: 0`) ateşleyen mimari devreye alındı.
> - **Yeni Onboarding Sıralaması & 7. Kart Öneri C (`MışılSpot™ Kalibrasyonu + 4 Hızlı Çip`):** `0:Karşılama ➔ 1:Profil ➔ 2:Uyku Zorluğu ➔ 3:Gelişim Atakları ➔ 4:Aşı Takvimi ➔ 5:Beslenme ➔ 6:Bez ➔ 7:MışılSpot™ Kalibrasyonu (Az önce / 1 sa önce / 2 sa önce / 3+ sa) ➔ 8:Rapor ➔ 9:Paywall` akışı tamamlandı (`11/11 suite / 86 Jest PASS`, `12/12 Pytest PASS`, `7/7 READY_FOR_RELEASE`).
> - **Google Play Console (`Build 75` / `versionCode: 75`):** EAS Build `e8e4b66f-2140-4c1e-9333-6b64b72554f1` ➔ EAS Submit `b71dd31d-01a8-4238-8831-e4138bf78fd8` ➔ `production` kanalı `status: completed` (`Committed Edit ID: 03560641672354073366`, `tr-TR / en-US / de-DE` sürüm notları canlıda).
> - **Apple App Store Connect (`v4.58.0` / `Build 75`):** EAS Build `13994620-eadc-4fea-b3ff-919c0e0aab2a` ➔ EAS Submit `f32cb7af-7ec2-4035-a7d4-59a3c5f38777` ➔ Version ID `a6044a62-3ffa-4d93-9fbe-4b86aff2fa0a`, ASC Build ID `a30a3cda-1cec-43cc-887a-15127040b5f9` (`VALID`), Review Submission ID `b783b683-58c5-47dd-8a9e-758ca437fb2d` (**`WAITING_FOR_REVIEW`**; bir önceki `v4.57.3 / Build 74` sürümü `READY_FOR_SALE` olarak onaylandı).

> **🚀📦 `v4.57.3` (`Build 74`) Çift Platform Mağaza & Railway Canlı Teslimat Özeti (2026-11-26):**
> - **Railway Canlı WebView (`v4.57.3`):** 5 Aşamalı Satış Hunisi Optimizasyonu, Tek Odaklı Karşılama Ekranı (`#quiz-step-0` `#btn-welcome-start-plan`), Adım 1 Tek Seferlik Zorunlu Bebek Adı (`#onb-baby-name-input`), Kaydırmasız Tek Ekran (`~460px`) Birleşik Rapor Kartı (`#quiz-step-8` `#report-unified-summary-card` + `#btn-report-unlock-plan`) ve Sıfır-Cringe Konsept D Paywall (`İlk ay denemeniz için ₺49,99 • Sonrasında ayda bir kahve fiyatına (₺149,99/ay)`) canlıda.
> - **Google Play Console (`Build 74` / `versionCode: 74`):** EAS Build `b0592a0a-c245-43a9-a893-8c4cb73b9d32` ➔ EAS Submit `372b49c9-4612-45c3-882f-4e2abcb83c54` ➔ `production` kanalı `status: completed` (`Committed Edit ID: 14994238185154928324`, `tr-TR / en-US / de-DE` sürüm notları ve tüm telefon/tablet/featureGraphic görsel yuvaları eksiksiz).
> - **Apple App Store Connect (`v4.57.3` / `Build 74`):** EAS Build `2316f0f9-817f-4ea0-89bb-a421ddfd3a61` ➔ EAS Submit `57f5388d-ee96-4568-838f-72b9ac780abb` ➔ Version ID `6c74420c-8298-475e-9728-3965247b90a1`, ASC Build ID `04b378ee-4532-4e91-8fcd-ee6ce3de022e` (`VALID`), Review Submission ID `fb1b3965-9321-46b5-8cc4-e20e1af4de74` (**`WAITING_FOR_REVIEW`**).

> **🔔📌 `Build 73` & `Build 74` Native Derleme Kuyruğu Hatırlatıcısı (Teslim Edildi — 2026-11-26):**
> - **10'lu Yaşa/Güne/Duruma Duyarlı Akıllı Bildirim Rotasyon Motoru (`mobile/features/notifications/careNotificationEngine.ts`, `mobile/components/MishilUnifiedWebView.tsx`, `mobile/features/webview/offlineHtml.generated.ts`):**
>   - `v4.56.12` (`afb190e`) ile git deposuna (`origin/main`) ve WebView (`app.html`) ayarlarına eklendi.
>   - Native TypeScript (`expo-notifications` OS takvim planlayıcısı) katmanında çalıştığı için, Apple `v4.56.0 (Build 72)` incelemesi tamamlandıktan sonra alınacak **`Build 73` (iOS + Android)** native EAS derlemesiyle telefonların işletim sistemi bildirim kuyruğuna (`ROUTINE_SLEEP_VARIANTS` 10'lu rotasyon + `isLiveSleepingToday` + `completedVaccineMonths` + `routineFrequency`) gömülecektir.

> **🚀💎 `v4.55.0` (`Build 71`) Sıfır Freemium (Hard Paywall) & İlk Ay `₺49,99` Ücretli Başlangıç Paketi (2026-11-20 — Railway Canlıda + Mağaza Aktif + Build 71 EAS Kuyruğunda):**
> - **Model Geçişi:** Freemium (`FREE_SOUND_PREVIEW_TOTAL_MS = 0`, `SOFT_VIP_DURATION_MS = 0`, `#onboarding-skip-wrap` kapatıldı) ve 7 Gün Ücretsiz Deneme (`Bugün ₺0`) `TR / EN / DE` 3 dilde ve 174 ülkede tamamen emekli edildi.
> - **Yeni Tarife & Apple 3.1.2c 3-Durumlu Uygunluk:** Aylık VIP (`misil_monthly` `#6809228860` / `misilaylik`) **İlk Ay `₺49,99` ➔ 2. aydan itibaren `₺149,99/ay`** (`eligible` doğrulanmış mağaza teklifi / `unknown_new_user` koşullu not / `ineligible` doğrudan `₺149,99/ay`); Yıllık VIP (`misil_annual` `#6809228257` / `misil`) **`₺599,99/yıl`** (`%67` tasarruf, denemesiz doğrudan yıllık).
> - **Apple 2.1b Unified Submission & Canlı Geçiş Sırası (MG Onayı Sonrası):**
>   1. `python projects/mishil/scripts/sync_ppp_store_pricing.py --apply` (Google Play `freeytrial`/`3daystrial` kapatma + 174 ülke `intro-first-month` `P1M`; Apple ASC `FREE_TRIAL` silme + `PAY_UP_FRONT` `ONE_MONTH` `49.99 TRY` / PPP girişleri).
>   2. `Build 71` EAS derlemesi (`iOS + Android`) ve App Store Connect'te **Uygulama İkili Dosyası (`Build 71`) + `misil_monthly` + `misil_annual` Birleşik İnceleme Gönderimi (`Unified Submission`)** + Google Play App Access PIN (`MISIL-REV-9842` — `v4.55.0 (Build 71)` 5x dokunuş).
>   3. Mağaza teklifleriyle senkron Railway canlı dağıtımı (`git push`).

> **🚀 `v4.51.1` (`Build 70`) Canlı Yayın & Çift Platform EAS Dağıtım Paketi (2026-11-13):**
> - **Kilit Ekranı Deep-Link (`misilbaby://sleep`, `Build 70`):** `mobile/app/+native-intent.tsx`, `sleep.tsx`, `+not-found.tsx`, `_layout.tsx`, `MishilUnifiedWebView.tsx` (`ExpoLinking` + `Linking` + `focusSleepViewInWebView`) ve Android `MishilLiveSleepNotifier.kt` / `MishilMediaPlaybackService.kt` (`FLAG_ACTIVITY_SINGLE_TOP | FLAG_ACTIVITY_CLEAR_TOP`) ile `Unmatched Route` ekranı tamamen kapatıldı.
> - **WebView Çok Günlü Tarih, `"Dün"` 48s Penceresi & Onboarding Rutin Kalıcılığı (`public/app.html` + `offlineHtml.generated.ts`):** `2880 dk` `"Dün"` uyanış penceresi + `"Şimdi"` kahraman etiketi, `skipOnboardingToApp` rutin kalıcılığı (Freemium kilidi korunarak), `#routine-modal-date` tarih seçici (`resolveSleepTimestamps` açık `"Bugün"` sabitleme + `effectiveStart/End` senkronu dahil), gün gruplu Analiz aktivite çizelgesi ve `activeDaysCount` haftalık uyku ortalaması tamamlandı (`Claude Code CLI task-362 -> task-410: CLAUDE_VERDICT: PASS`, `9 suite / 61 Jest testi`, `tsc --noEmit` sıfır hata, `7/7 READY_FOR_RELEASE`).

> **📌 `Build 69` (`v4.51.0`) Native Teslimat Özeti (2026-11-12 — Canlıya & EAS Derlemesine Alındı):**
> Aşağıdaki 3 native kabuk (`mobile/`) + WebView geliştirmesi `v4.51.0 (Build 69)` paketinde birleştirilmiştir:
>
> | # | Tarih | Geliştirme / Düzeltme | Etkilenen Native Dosyalar | Durum |
> | :-: | :-- | :-- | :-- | :-- |
> | **1** | 2026-11-12 | **`expo-secure-store` Keychain Cihaz Kota Kalıcılığı:** Uygulama silinip yeniden yüklendiğinde veya Apple `5.1.1(v)` kişisel veri silme (`CLEAR_PERSONAL_DATA`) çalıştığında anonim ücretsiz hak bitlerini (`mishil_device_quotas_v1`, `quotasHydrated`, `deviceQuotaMutex`) iOS Keychain / Android EncryptedSharedPreferences üzerinde koruma | `mobile/lib/storage.ts`, `mobile/components/MishilUnifiedWebView.tsx` | 🚀 `v4.51.0 (Build 69)` Paketinde |
> | **2** | 2026-11-12 | **İlk Açılış Yükleme Ekranı `"Mışıl Baby"` Marka & Dil Algılama Düzeltmesi:** WebView `renderLoading` ekranındaki `"Loading Mishil Baby..."` ➔ `"Loading Mışıl Baby..."` düzeltmesi, Hermes üzerinde Türkçe cihazların ilk açılışta İngilizce algılanmasını önleyen `NativeModules` (`SettingsManager` / `I18nManager`) OS dili okuma katmanı, IAP bildirimleri, `expo-av` mikrofon izni ve İngilizce aşı bildirimlerindeki `"Mishil"` ➔ `"Mışıl Baby"` hizalaması | `mobile/components/MishilUnifiedWebView.tsx`, `mobile/app.config.ts`, `mobile/features/notifications/careNotificationEngine.ts` | 🚀 `v4.51.0 (Build 69)` Paketinde |
> | **3** | 2026-11-12 | **Kilit Ekranı Canlı Uyku Takibi (`Live Activities` / `Dynamic Island` / `StandBy` / Android 16 `Live Updates`) & Çalan Ses Kontrol Kartı (`Now Playing` / `MediaSession`):** Huckleberry + Dark Noise/Calm + Hatch Rest uluslararası standardında (1) iOS `ActivityKit` Widget Extension (`MishilLiveActivity`, OLED `#0B0F1A` + `#E8A855` kehribar, AOD `@Environment(\.isLuminanceReduced)`, sıfır-push `Text(timerInterval:)`, 7. saatte ön plan tazeleme + 8–12 saat kilit ekranı sürekliliği, tek dokunuşlu `misilbaby://sleep` güvenli yönlendirme) ve Android Ongoing Chronometer + Android 16 API 36 `POST_PROMOTED_NOTIFICATIONS` canlı durum çubuğu çipi, (2) iOS `AVQueuePlayer` + `AVPlayerLooper` + `MPNowPlayingInfoCenter` + `MPRemoteCommandCenter` ve Android `MediaSessionCompat` + `NotificationCompat.MediaStyle` (`FOREGROUND_SERVICE_MEDIA_PLAYBACK`) kilit ekranı `Oynat/Duraklat/Durdur` kartı + monotonik saatle 60 sn kümülatif Freemium ses önizleme kotası (`enqueueAudioOp` / `audioOpMutex` / `sessionBaseByTrack`) | `mobile/modules/mishil-lockscreen/**`, `mobile/targets/MishilLiveActivity/**`, `mobile/plugins/withMishilLiveActivity.js`, `mobile/features/audio/nativeAudioPlayer.ts`, `mobile/features/sleep/nativeLiveSleep.ts`, `mobile/components/MishilUnifiedWebView.tsx`, `mobile/app.config.ts`, `public/app.html`, `mobile/features/webview/offlineHtml.generated.ts` | 🚀 `v4.51.0 (Build 69)` Paketinde |

> Amaç: Google Play **ve** Apple App Store'a, "bazı telefonlarda açılmıyor" ve
> "satın alma çalışmıyor" sınıfı sürprizler olmadan çıkmak.
> Durum: Android Build 63 (`.aab`) Google Play Production kanalına ve yeni mağaza vitrinine API ile yüklendi;
> iOS v1.0 yayında, v1.1 (Build 57) Apple Review aşamasında!

---

## 0. Mevcut Durum (v4.44.1 Build 63)

| Alan | Durum |
| :-- | :-- |
| WebView açılış dayanıklılığı (render-crash kurtarma, retry, watchdog, `androidLayerType: software`) | ✅ kodda & canlıda |
| Wonder Weeks (10 Zihinsel Sıçrama) & Mışıl Spot™ Sirkadiyen Sayaç | ✅ kodda & mağazada |
| 30 Stüdyo Master Parça & Akustik Crossfade Mikser (CBR 192k) | ✅ kodda & pakette |
| Klinik Akustik Ağlama Analizi (13-Bant MFCC Spektrogram) | ✅ kodda |
| Şefkatli Mışıl Dadı AI Koçu & Biyometrik Rollup | ✅ kodda |
| Android `minSdk 26` / `targetSdk 36` / 16KB Bellek (Build 63) | ✅ Build 63 AAB üretildi, yerel arşive indirildi & Google Play Production'a API ile yüklendi |
| iOS `buildNumber 57`, `ITSAppUsesNonExemptEncryption` | ✅ v1.0 Yayında, v1.1 (Build 57) **Apple Review'da (`WAITING_FOR_REVIEW`)** |
| Production build guard (mock RevenueCat anahtarıyla derleme engellenir) | ✅ geçildi |
| jest yeşil (`*.test.ts` - 3 suite / 10 test), compliance PASS | ✅ yeşil (100%) |
| Native arka plan ses motoru + `CareNotificationEngine` + Haptics 2.0 | ✅ pakete gömüldü |
| Offline fallback (`offlineHtml.generated.ts` - v4.44.1) | ✅ pakete gömüldü |
| RevenueCat `pro` entitlement + `default` offering | ✅ panelde bağlı, kod hizalandı |
| Canlı uçlar (`/app`, `/privacy`, `/terms`, `/ios`, `/android`, `/sounds`, `/coach/chat`) | ✅ 200 OK — canlıda doğrulandı |
| Google Play Production & Mağaza Vitrini (API Otomasyonu) | ✅ Build 63 & Yeni Poster/Açıklamalar API ile yüklendi (`google-play-service-account.json` aktif) |
| Apple App Store Connect Dağıtımı | ✅ **Onaylandı & Yayına Alındı (Approved & Released 🎉)** |

---

## 1. Faz 0 — Ön Koşullar (derlemeden ÖNCE, hepsi bloklayıcı)

### 1.1 RevenueCat
- [x] `EXPO_PUBLIC_REVENUECAT_ANDROID` = `goog_...` — `eas.json` production env'e eklendi.
- [x] `EXPO_PUBLIC_REVENUECAT_IOS` = `appl_...` — `eas.json` production env'e eklendi.
      → her iki platform için `app.config.ts` production guard geçilir.
- [x] RevenueCat panelinde **`pro` Entitlement** + **`default` Offering** 3 pakete bağlı
      (`$rc_annual` / `$rc_monthly` / `$rc_lifetime`). Kod hizalandı (`FALLBACK_OFFERINGS`
      identifier'ları + `hasActiveEntitlement` önce `pro`'yu kontrol ediyor).
- [ ] Sandbox test satın almasıyla `entitlements.active.pro` doğrulanacak (Faz 2).

> Not: RevenueCat **public SDK anahtarı** (`goog_` / `appl_`) tasarımı gereği istemciye gömülür,
> gizli değildir; `eas.json`'da tutulması güvenlik açığı değil. Yine de EAS secret daha temiz.

### 1.2 Google Play Console
- [x] Uygulama içi ürünler + temel planlar **Etkin (Active)**.
- [x] Fiyatların `app.html` kartlarıyla **birebir** aynı olduğu teyit edildi (₺599.99 / ₺149.99 / ₺2.499.99).
- [ ] **`google-play-service-account.json`** dosyası `projects/mishil/mobile/` içine konacak.
      Play Console → Setup → API access → service account → JSON key indir. Gitignore korumada.
      Alternatif: `eas credentials` ile EAS'e yüklemek (dosyasız). **Sadece `eas submit` için.**
- [ ] Data safety formu dolduruldu (hesap, mikrofon, aile paylaşımı, analitik).
- [x] Gizlilik politikası + EULA linkleri canlı (`/privacy` + `/terms` → 200, probe edildi).

### 1.3 Apple App Store Connect
- [x] `appleTeamId: "V6QVVU79GZ"` (gerçek) + App Identifier tanımlı.
- [x] `ascAppId` sahte değeri `eas.json`'dan kaldırıldı — `eas submit` bundle id +
      Apple hesabından otomatik çözer. (İstenirse App Store Connect > App Information >
      Apple ID değeri elle de eklenebilir.)
- [ ] Abonelik grubu + 3 ürün "Ready to Submit":
  - Yıllık (3 gün ücretsiz deneme introductory offer), Aylık, Ömür Boyu (Non-Consuming)
- [ ] App Privacy (nutrition labels) dolduruldu: hesap bilgisi, kullanıcı içeriği, mikrofon, tanımlayıcılar.
- [ ] Yaş sınırı / Kids kategorisi kararı: uygulama "Kids" kategorisinde **değil** (ebeveyn hedefli).
- [ ] Tıbbi feragatname onboarding'de zorunlu (mevcut). Uygulama açıklamasında "teşhis/tedavi" iddiası yok.

### 1.4 Altyapı
- [x] Railway `mishil-production` kesintisiz / uykusuz — Status 200 OK.
- [x] Canlı uçlar probe edildi: `/app` 200 (155 KB, PIN yok, native ses köprüsü kodu canlıda),
      `/sounds/brahms_lullaby.mp3` 200 `audio/mpeg`, `/privacy` 200, `/terms` 200.
- [x] `/api/v1/*` uçları (Mışıl Dadı `/api/v1/coach/chat`) canlıda test edildi ve Status 200 OK ile doğrulandı.
- [ ] `function-bun-production-9541.up.railway.app/ws` bağlantısı (zaman aşımı veriyor, uygulama 6 denemede graceful duruyor).

---

## 2. Faz 1 — Derleme

```bash
cd projects/mishil/mobile

# git push (submodule + parent) — commit'ler hazır
git -C .. push origin main
git -C ../../.. push origin main

# Android
eas build --platform android --profile production   # build 16 (.aab)

# iOS  (EXPO_PUBLIC_REVENUECAT_IOS eklendikten sonra)
eas build --platform ios --profile production        # build 16 (.ipa)
```

- [ ] Her iki derleme de **hatasız** bitti (RevenueCat guard geçildi = secret'lar tanımlı demek).
- [ ] `.aab` ve `.ipa` indirildi / EAS'te saklandı.
- [ ] iOS derlemesinde `react-native-purchases` privacy manifest'i pakete dahil (EAS logu / Xcode organizer).

---

## 3. Faz 2 — Gerçek Cihaz Test Matrisi

### 3.1 Android (öncelik: daha önce açılmayan profiller)
| Profil | Neyi doğrular |
| :-- | :-- |
| 2–3 GB RAM, Android 8–10, Mali GPU | Render-crash kurtarma, `androidLayerType: software`, boş ekran yok |
| Android 8.0 (minSdk sınırı) | Uygulama açılıyor, TLS el sıkışması OK |
| Android 14–16 | targetSdk 36 davranışı, izinler |
| Zayıf şebeke / uçak modu aç-kapa | Retry ekranı + "Tekrar Dene" butonu + otomatik 3 deneme |
| Uçak modunda başlat | Hata ekranı görünüyor (boş ekran değil), sonra bağlanınca düzeliyor |
| Xiaomi/Samsung agresif pil yöneticisi | Ses 30–60 dk arka planda kesilmiyor |

### 3.2 iOS
| Profil | Neyi doğrular |
| :-- | :-- |
| En eski desteklenen iPhone (iOS 15+) | Açılış, WKWebView render |
| **Ekran kilitliyken ninni** | Native ses motoru (v4.9.0) — arka plan sesi devam ediyor mu? (bkz. §5 R1 kontrol listesi) |
| Düşük bellek | `onContentProcessDidTerminate` → otomatik reload |
| Zayıf şebeke | Retry akışı |

### 3.3 Her iki platform — fonksiyonel
- [ ] İlk açılış: şifre ekranı YOK, doğrudan ana ekran / ninni.
- [ ] Onboarding → tıbbi feragat kutusu olmadan ilerlenemiyor.
- [ ] **Test satın alması** (sandbox): Yıllık / Aylık / Ömür Boyu → gerçekten ücret akışı → Pro açılıyor.
- [ ] Satın almayı **iptal et** → Pro açılmıyor, sessiz geçiyor.
- [ ] **"Satın Alımları Geri Yükle"** hiç satın almamış hesapta → "aktif abonelik bulunamadı", Pro açılmıyor.
- [ ] Geçerli abonelikte "Geri Yükle" → Pro geri geliyor.
- [ ] Mikrofon izni: ağlama analizi kaydı çalışıyor.
- [ ] Haptik geri bildirim çalışıyor.
- [ ] Hesap silme akışı çalışıyor.
- [ ] Ses çalarken uygulamayı arka plana al / geri getir → ses kesilmiyor, mini player senkron.

---

## 4. Faz 3 — Mağaza Gönderimi (kademeli)

### Google Play
1. [ ] `.aab` → **Internal testing** track → yukarıdaki cihazlarda doğrula.
2. [ ] Sürüm notları (TR + EN), yeni ekran görüntüleri gerekiyorsa güncelle.
3. [ ] **Closed testing** (mevcut `track: closed`) → 3–5 gün, çökme oranı Play Console Vitals'ta izlenir.
4. [ ] ANR / Crash rate < %1 ise **Production**'a **kademeli** (staged rollout %10 → %50 → %100).

### Apple App Store
1. [ ] `.ipa` → **TestFlight** (internal) → §3.2 + §3.3 doğrula.
2. [ ] TestFlight external (opsiyonel, birkaç tester).
3. [ ] App Review'a gönder:
   - Review notu: test hesabı + "uygulama tamamen `mishil-production.up.railway.app` üzerinden çalışır, sunucu ayakta".
   - Sandbox test kullanıcısı bilgisi.
   - Abonelik ekranı yolu (adım adım).
4. [ ] Onay sonrası **manuel yayın** (otomatik değil) — Railway/altyapı hazır olduğunda.

---

## 5. Bilinen Riskler ve Azaltımlar

### 🟢 R1 — iOS/Android WebView'de arka plan ses — **ÇÖZÜLDÜ (v4.9.0), cihaz testi bekliyor**
WKWebView `<audio>` ve Web Audio API ekran kilitlenince sesi durduruyordu (sentez sesler kesin).
- **Çözüm (uygulandı):** ses çalma native tarafa taşındı — `features/audio/nativeAudioPlayer.ts`,
  `expo-av` + `Audio.setAudioModeAsync({ playsInSilentModeIOS, staysActiveInBackground, … })`.
  WebView yalnızca UI; `AUDIO_PLAY/STOP/TIMER/VOLUME` köprü mesajları. `MishilNative.audioBridge`
  kill-switch var.
- **Kalan doğrulama (Faz 2, gerçek cihaz):**
  - [ ] iOS: kilitli ekranda her ses tipi (MP3 + eskiden sentez olan) çalmaya devam ediyor
  - [ ] iOS: gelen arama / başka uygulama sesi kesince davranış makul (DoNotMix)
  - [ ] Android 8-10 + agresif pil yöneticili cihaz (Xiaomi/Samsung): 30-60 dk oturum kesilmiyor
  - [ ] Sessiz moddayken (iOS sessize alma anahtarı) ninni yine çalıyor
  - [ ] Timer native tarafta tetikleniyor, uygulama arka plandayken de sesi durduruyor
- **Kalan sınır:** tüm gece oturumlarında OEM pil katli riski (tam çözüm: foreground service /
  Expo SDK 52 `expo-audio`); kilit ekranı oynatma kontrolleri henüz yok.

### 🟢 R2 — %100 uzak URL bağımlılığı — **AZALTILDI (v4.9.0), cihaz testi bekliyor**
- **Çözüm (uygulandı):** `public/app.html` binary'e gömülüyor (`scripts/bundle-offline-html.js` →
  `features/webview/offlineHtml.generated.ts`, commit'li). Uzak sürüm 3 otomatik denemede de
  yüklenemezse gömülü çevrimdışı sürüm açılıyor; üstte "📴 Çevrimdışı sürüm" bandı, 20 sn'de bir
  uzak sürüme yeniden bağlanma denemesi, bağlantı dönünce otomatik geçiş.
- **Kalan doğrulama (Faz 2):**
  - [ ] Uçak modunda başlat → gömülü sürüm açılıyor, banner görünüyor
  - [ ] Şebeke geri gelince ~20 sn içinde uzak sürüme otomatik dönüyor
  - [ ] Banner'a dokunma manuel yeniden bağlanma yapıyor
  - [ ] Gömülü sürümde şebeke varken sesler/fontlar `baseUrl` ile yükleniyor (iOS + Android)
- **Sürüm bakımı:** `app.html` değişince `npm run bundle:offline` çalıştırılıp generated dosya
  commit'lenmeli (yerelde `postinstall` otomatik yapar).

### 🟠 R3 — `compileSdk/targetSdk 36` + Expo SDK 51
Resmî desteklenen kombinasyon değil (Expo 51 → SDK 34/35). Build geçse bile bazı OS sürümlerinde runtime riski.
- Azaltım: §3.1 cihaz matrisi bunu kapsıyor. Kalıcı çözüm: Expo SDK 52+ yükseltmesi (ayrı iş).

### 🟡 R4 — Sabit fiyatlar `app.html` içinde
9 yerde hardcoded (`compliance_checker` artık WARN veriyor). Mağaza fiyatı değişirse app güncellemesi gerekir.
- Azaltım: fiyatları `MishilNative` üzerinden `getOfferings()` sonucundan bas (yeni geliştirme, küçük).

### 🟡 R5 — Medikal/klinik dil
"Klinik gelişim skoru", "pediatrik danışman", ağlama analizi yüzdeleri. Apple 1.4.1 / 5.2.
- Azaltım: tıbbi feragat zorunlu (mevcut). Mağaza açıklamasında teşhis/tedavi iddiası olmasın; "bilgilendirme amaçlıdır" vurgusu.

---

### 🟢 R6 — v4.10.0 (Build 18) İyileştirmeleri & Devir Teslim
- `loadBabyProfile()` ve `saveBabyProfile()` sıfırdan yazılarak `ReferenceError` çökmesi giderildi.
- Gelişim Atakları (Wonder Weeks 10 Zihinsel Sıçrama) hem Ana Sayfa Bento Kartı hem Analiz sekmesine bağlandı.
- Günlük biyometrik analitik rollup (#6) ve Mışıl Dadı AI payload entegrasyonu tamamlandı.
- 18 stüdyo ses dosyasının tamamı CBR 192kbps, >=30sn seamless loop olarak onarıldı (#4).
- Gömülü çevrimdışı fallback (`offlineHtml.generated.ts`) ve TypeScript/Jest/Compliance testleri %100 yeşil.

---

## 6. Rollback

- **Google Play:** staged rollout'ta çökme artışı → rollout'u durdur / önceki sürüme geri al (build 16 = 4.9.0).
- **Apple:** onaylı yeni sürümü "Developer removed from sale" değil, **Phased release'i durdur**; kritikse önceki sürümü tekrar yayınla (App Store bir önceki build'i saklar).
- **Sunucu (app.html):** tekil kaynak olduğu için `git revert` + Railway redeploy anında tüm cihazlara yansır — mobil sürümden bağımsız hızlı kaçış yolu.

---

## 7. "Kusursuz" Çıkış Kriterleri

Production'a çıkış için hepsi ✅ olmalı:
- [ ] Faz 0 tüm maddeler (iOS RevenueCat anahtarı dahil)
- [ ] Android: §3.1'deki profillerde açılış + retry + arka plan ses testi geçti
- [ ] iOS: TestFlight'ta açılış + **R1 cihaz testi geçti** (§5 R1 kontrol listesi — kilitli ekranda ninni)
- [ ] Her iki platformda 3 paket için sandbox satın alma + iptal + restore testi geçti
- [ ] Closed test / TestFlight'ta 48–72 saat, crash rate < %1
- [ ] Railway uykusuz planda, tüm uçlar 200
- [ ] Sürüm notları + gizlilik/EULA linkleri güncel

---

_Son güncelleme: 2026-09-07 · Sürüm hedefi: 4.10.0 (build 18) · Kod durumu: hazır, Faz 2 cihaz doğrulaması & mağaza teslimi_
