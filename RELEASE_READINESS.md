# Mışıl Baby — Kusursuz Yayın Hazırlık Planı (v4.9.0 / build 16)

> Amaç: Google Play **ve** Apple App Store'a, "bazı telefonlarda açılmıyor" ve
> "satın alma çalışmıyor" sınıfı sürprizler olmadan çıkmak.
> Durum: kod tarafı hazır ve doğrulandı (typecheck + jest yeşil, compliance PASS).
> Kalan iş **doğrulama + derleme + mağaza gönderimi** — aşağıdaki fazlar sırayla.

---

## 0. Mevcut Durum

| Alan | Durum |
| :-- | :-- |
| WebView açılış dayanıklılığı (render-crash kurtarma, retry, watchdog, `androidLayerType: software`) | ✅ kodda |
| Abonelik gelir sızıntıları (restore/purchase sahte başarı) | ✅ kodda |
| Android `minSdk 26` / `targetSdk 36` | ✅ kodda |
| iOS `buildNumber`, `ITSAppUsesNonExemptEncryption` | ✅ kodda |
| Production build guard (mock RevenueCat anahtarıyla derleme engellenir) | ✅ kodda |
| jest yeşil (`*.test.ts`), Maestro spec ayrıldı | ✅ |
| Native arka plan ses motoru (kilitli ekranda ninni) | ✅ kodda (v4.9.0) — cihaz testi bekliyor, bkz. §5 R1 |
| RevenueCat anahtarları (Android + iOS) | ✅ ikisi de `eas.json` production env'de |
| Mağaza abonelik ürünleri + RevenueCat offering/entitlement | ⛔ **doğrulanmadı** |
| Gerçek cihaz testi (Android + iOS) | ⛔ yapılmadı |

---

## 1. Faz 0 — Ön Koşullar (derlemeden ÖNCE, hepsi bloklayıcı)

### 1.1 RevenueCat
- [x] `EXPO_PUBLIC_REVENUECAT_ANDROID` = `goog_...` — `eas.json` production env'e eklendi.
- [x] `EXPO_PUBLIC_REVENUECAT_IOS` = `appl_...` — `eas.json` production env'e eklendi.
      → her iki platform için `app.config.ts` production guard geçilir.
- [ ] RevenueCat panelinde **Entitlement** tanımlı (örn. `pro`) ve **Offering** (`default`) 3 pakete bağlı: `misil` (yıllık), `misilaylik` (aylık), `misilomurboyu` (ömür boyu).
- [ ] `hasActiveEntitlement()` genel kontrol yapıyor (`entitlements.active` / `activeSubscriptions` / tek seferlik). Entitlement adı özelse sorun yok; yine de test satın almasıyla doğrula.

> Not: RevenueCat **public SDK anahtarı** (`goog_` / `appl_`) tasarımı gereği istemciye gömülür,
> gizli değildir; `eas.json`'da tutulması güvenlik açığı değil. Yine de EAS secret daha temiz.

### 1.2 Google Play Console
- [ ] Uygulama içi ürünler oluşturuldu ve **Aktif**:
  - `misil` — Yıllık abonelik, 3 gün deneme, ₺599,99
  - `misilaylik` — Aylık abonelik, ₺149,99
  - `misilomurboyu` — Tek seferlik ürün (managed product), ₺2.499,99
- [ ] Fiyatlar `app.html` kartlarıyla **birebir** aynı (₺599.99 / ₺149.99 / ₺2.499.99).
- [ ] `eas.json > submit.production.android.serviceAccountKeyPath` (`google-play-service-account.json`) mevcut ve geçerli.
- [ ] Data safety formu dolduruldu (hesap, mikrofon, aile paylaşımı, analitik).
- [ ] Gizlilik politikası + EULA linkleri canlı (compliance checker PASS veriyor).

### 1.3 Apple App Store Connect
- [ ] App Store Connect'te uygulama kaydı açık; **gerçek** değerler `eas.json`'a girildi:
  - `submit.production.ios.ascAppId` — şu an `6470000000` (placeholder, düzeltilmeli)
  - `submit.production.ios.appleTeamId` — şu an `LEVITAS1` (placeholder, düzeltilmeli)
  - `appleId` = `mrtgurpinar@gmail.com` (doğru)
- [ ] Abonelik grubu + 3 ürün oluşturuldu, "Ready to Submit":
  - Yıllık (3 gün ücretsiz deneme introductory offer), Aylık, Ömür Boyu (Non-Consuming)
- [ ] App Privacy (nutrition labels) dolduruldu: hesap bilgisi, kullanıcı içeriği, mikrofon, tanımlayıcılar.
- [ ] Yaş sınırı / Kids kategorisi kararı: uygulama "Kids" kategorisinde **değil** (ebeveyn hedefli) → 3. taraf analitik + hesap açımı buna uygun tutulmalı.
- [ ] Tıbbi feragatname onboarding'de zorunlu (mevcut). Uygulama açıklamasında "teşhis/tedavi" iddiası yok.

### 1.4 Altyapı
- [ ] Railway `mishil-production` servisi **uykuya geçmeyen** planda (Hobby değil) — inceleme sırasında ve canlıda ilk açılışta soğuk başlangıç = retry ekranı riski.
- [ ] `mishil-production.up.railway.app/app`, `/privacy`, `/terms`, `/sounds/*`, `/api/v1/*` GET/HEAD 200.
- [ ] `function-bun-production-9541.up.railway.app/ws` ayakta (kapalıysa app çöker değil ama realtime sync yok; WS artık 6 denemede duruyor).

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

### 🟠 R2 — %100 uzak URL bağımlılığı
Railway/DNS/CDN sorununda uygulama açılmaz (artık retry ekranı var, boş ekran yok).
- Azaltım: `public/app.html`'in bir kopyasını binary'e göm, uzak 3 denemede de başarısızsa yerelden yükle (`source={{ html, baseUrl: 'https://mishil-production.up.railway.app' }}`). Fallback her derlemede tazelensin.
- Efor: ~yarım gün. Bu sürüme opsiyonel.

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

## 6. Rollback

- **Google Play:** staged rollout'ta çökme artışı → rollout'u durdur / önceki sürüme geri al (build 15 = 4.8.4).
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

_Son güncelleme: 2026-09-06 · Sürüm hedefi: 4.9.0 (build 16) · Kod durumu: hazır, doğrulama bekliyor_
