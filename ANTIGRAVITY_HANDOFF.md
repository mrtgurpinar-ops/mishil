# Antigravity Devir Teslim — Mışıl Baby

> **`[cross-lane]` Notu (2026-11-21 · `v4.55.0-intro-fix` · Railway Canlıda & 3-Ajanlı Konsensüs Onaylı · Apple `Build 71` `READY_FOR_SALE`):**
> - **Mağaza Durumu (`v4.55.0` / `Build 71`):** Apple App Store incelemesi tamamlandı ve **`READY_FOR_SALE` (Yayında)** durumuna geçti (`misil_monthly` `#6809228860` `TUR: 49.99 TRY PAY_UP_FRONT ONE_MONTH APPROVED`); Google Play Production (`versionCodes: ['71']`, `misilaylik/intro-first-month` `TR: 49.99 TRY ACTIVE`) yayında.
> - **İlk Ay `₺49,99` Görünürlük & Android `defaultOption` Baz Fiyat Kurtarması (`[cross-lane]` — `public/app.html`, `mobile/features/subscription/revenuecat.ts`, `mobile/features/webview/offlineHtml.generated.ts`, `mobile/tests/onboardingPlanBuilder.test.ts`, `mobile/tests/liveNursingAndMomBreak.test.ts`):**
>   1. `public/app.html`: Statik kart açılış varsayılanı `₺149,99/ay` olarak korundu; `applyStorePrices` çalıştığında hem `eligible` hem de yeni iOS kurulumlarında StoreKit `UNKNOWN (0)` (`unknown_new_user`) durumunda Paywall kartının ana fiyat alanında `₺49,99 / ilk ay` + `2. aydan: ₺149,99/ay` gösterimi bağlandı (`ineligible` eski abonelerde sıfır `₺49,99` kuralı korundu); eski yerel `mishil_trial_start` anahtarının mağaza satın alımı olmayan kullanıcıları `ineligible` sayması kaldırıldı; Android `Build 71` `prod.price == 49.99` (`defaultOption`) çakışmasında `BASE_MONTHLY_PPP_BY_CURRENCY` ile `149.99` baz aylık fiyat kurtarması eklendi.
>   2. `mobile/features/subscription/revenuecat.ts` & `mobile/eas.json`: Android `extractAndroidPaidIntroOption` içine `fullPricePhase` / `isBasePlan` `recurringPrice` ayrıştırması eklendi; Expo SDK 54'te iOS 27 UIKit scene-lifecycle çökmesini önlemek üzere `eas.json` `"image": "sdk-54"` korundu (Nisan 2027 `ITMS-90725` son tarihinden önce Expo SDK yükseltmesiyle birlikte Xcode 27 imajına geçilecek).
>   3. **Seviye 3 Gerçek 3-Ajanlı Konsensüs Kanıtları:** `Claude Code CLI` (`task-135` ➔ `task-166`: `CLAUDE_CONSENSUS_VERDICT: PASS` ➔ `task-205` doküman hizalaması), `Codex CLI` (`gpt-6-luna`, `task-186` ➔ `task-204`: `CODEX_CONSENSUS_VERDICT: PASS`), `10/10 suite / 75 Jest testi`, `58/58 pytest`, `mobile_compliance_checker.py` `7/7 READY_FOR_RELEASE` (`task-140`).

> **`[cross-lane]` Notu (2026-11-20 · `v4.55.0-perf` & `Build 71` Mağaza Gönderimi · Railway Canlıda):**
> - **Mağaza Durumu (`v4.55.0` / `Build 71`):** Google Play Production kanalına yüklendi ve yayınlandı (`status: completed`, `versionCodes: ['71']`, EAS Submission `b5a84135-1b2b-4810-9818-4104840501ba`, Edit `05920689398117499351` `HTTP 200`); Apple App Store Connect üzerinde `1a88331d-8665-4785-8ab4-8097f8a497e7` sürümüne bağlanıp incelemeye gönderildi (**`WAITING_FOR_REVIEW`**, Review Submission `a5d44511-b6f9-4b36-85fb-dd0a320df144`). İnceleme notlarıyla tam uyum için `APP_VERSION = '4.55.0'` sabit tutuldu.
> - **Kurucu Kokpiti Hızlandırma (`[cross-lane]` — `app/main.py`, `app/db/base.py`, `app/api/v1/endpoints/analytics.py`, `app/api/v1/endpoints/feedback.py`, `app/services/subscription.py`, `tests/test_sleep_and_analytics_remediation.py`):** MG'nin `"kokpit çok yavaş açılıyor"` -> `"uygula ve canlıya al"` talimatı üzerine Uvicorn event-loop kilidi (`async def` ➔ `def`), `%87` `GZipMiddleware` (`247.9 KB` ➔ `32.1 KB`), `_ClickSlim` / `_SignalSlim` sütun projeksiyonu, tek sorguda 8 tablo sayımı, `_LEDGER_RECONCILE_LOCK` + monotonik `_LEDGER_RECONCILE_GEN`, olay-güdümlü `10 sn` `_SUMMARY_CACHE` (`record_bridge_click`, `submit_feedback`, `process_revenuecat_webhook` vb. anında invalidation) ve bloklamayan single-flight arka plan mağaza senkronu tamamlandı. **Seviye 2 Gerçek CLI Kanıtı:** `Claude Code CLI` (`task-1444` Tur-1 ➔ `task-1497` Tur-2: `CLAUDE_REVIEW_VERDICT: PASS`) + `58/58 pytest` (`task-1487`).

> **`[handoff] [cross-lane]` Notu (2026-11-20 · `v4.54.1` · `v4.55.0 / Build 71` İle Canlıya Alındı):**
> - **Durum:** Canlı Railway ortamında şu an `v4.54.0` (`d410428`) çalışmaktadır. `v4.54.1` paketi yerel depoda eksiksiz tamamlanmış, tüm testlerden ve Seviye-3 3-ajanlı denetimden geçmiş ve yeni konuşmaya devredilmek üzere **yerel olarak commit edilmiştir (`d55789f` + bu commit — `origin/main` üzerine PUSH EDİLMEDİ)**.
> - **Tamamlanan İşler (`v4.54.1`):**
>   1. **Canlı Emzirme ➔ Canlı Etkinlikler (`Live Activities / Dynamic Island / Android Lock Screen`):**
>      - **Katman 1 (`Build 70` Anında Uyumlu — Yeni EAS Build Gerekmez):** `public/app.html` içinde `syncLiveNursingToNative` (`800ms` debounce), toplam süre, aktif meme yönü (`TR/EN/DE`), `Sol / Sağ` dağılımı (`showBabyNameOnLockScreen: false`), `3s` tavanı, Rüya Öğünü uyku geri yüklemesi, `🌙 Memede Uyudu` geçişi ve `lastNativeActivityDispatched` + `epochMatchesNursing` ön plan mutabakatı (`offlineHtml.generated.ts` `1218 KB` yenilendi).
>      - **Katman 2 (`Build 71` Kuyruğu — Native Swift/Kotlin/TS):** `MishilSleepAttributes.swift` (her iki hedefte geriye dönük `Codable` uyumlu `mode`, `isPaused`, `pausedElapsedSec`), `MishilLiveActivityLiveActivity.swift` (`🤱` Dynamic Island/Kilit Ekranı ikonu + statik `MM:SS ⏸`), `MishilLockScreenModule.swift/.kt`, `MishilLiveSleepNotifier.kt` (`setUsesChronometer(false)`), `nativeLiveSleep.ts`, `+native-intent.tsx` (`misilbaby://nursing`) ve `MishilUnifiedWebView.tsx` (`nursingLockScreenV2 = true`).
>   2. **Sabah Aile Senkronu (`07:25`) Zaman Damgası Zehirlenmesi Onarımı, Otomatik Veri İyileştirme (`Self-Healing`) & Sabah Kalibrasyonu:**
>      - `app/api/v1/endpoints/family.py` (`_serialize_routines_for_family` `_safe_epoch_ms` tip korumalı `camelCase + snake_case` çıktı, `SleepLog` çapalı otomatik iyileştirme, düzenlenmemiş ileri sıçramaları engelleyen anti-poison kalkanı ve `deleted_routine_ids` silme senkronu) + `public/app.html` (`mapServerRoutineToClientItem`, `repairCorruptedRoutineTimestamps`, `__mishilBootHealedRoutines`, `ROUTINE_ADDED` WS, `needsWakeCalibration` **`☀️ Uyanış?`** / **`☀️ Sabah Uyanışını Gir`** `openMorningWakeQuickModal` — hem `loadBabyProfile` hem `updateSubscriptionStatusUI` üzerinde).
> - **Seviye 3 Doğrulama Kanıtları (`%100 Yeşil`):**
>   - **Claude Code CLI:** `task-1152` ➔ `task-1256` (`FINAL_VERDICT: PASS`) ve `task-1367` ➔ `task-1492` (`FINAL_VERDICT: PASS`).
>   - **Codex CLI (`gpt-6-luna`):** `task-1150` ➔ `task-1257` ➔ `task-1296` (`FINAL_VERDICT: PASS`) ve `task-1378` ➔ `task-1493` ➔ `task-1519` ➔ `task-1546` (`FINAL_VERDICT: PASS`).
>   - **Testler:** `31/31 Playwright + FastAPI E2E` (`task-1545`), `55/55 pytest` (`task-1543`), `10/10 suite / 74 Jest` + `0 tsc` (`task-1544`), `missingTrTextsCount: 0`, `7/7 READY_FOR_RELEASE` (`task-1490`).
> - **Yeni Konuşmada Kalan Tek Adım (MG `"canlıya al"` dediğinde):**
>   1. Önce submodule push: `git -C projects/mishil push origin main`
>   2. Ardından ana depo push: `git push origin main`
>   3. `core/railway_service.py` ile Railway dağıtımının `SUCCESS` olduğunu ve `https://mishil-production.up.railway.app/app` üzerinde `v4.54.1` sunulduğunu doğrula (**🟢 Yeşil — Yeni Native EAS Build Gerekmez**; Katman-2 zenginleştirmesi sonraki planlı `Build 71`'i bekler).

> **`[cross-lane]` Notu (2026-11-20 · v4.54.0 · Railway Canlıda):** Çıkararak sadeleştirme (`6/10 ➔ 8.5/10`), kesin iki modlu beslenme (`⏱️ Şimdi Emzir | 📝 Geçmiş / Biberon Ekle`), dürüst eş nöbet notu (`PARTNER_WHISPER` + `fetchWithTimeout` + `family.py` `422/500` onarımları) ve `%100` izole `💛 Kendim İçin` alanı `d410428` / `408b3d4` commit'leriyle Railway canlı yayına (`b1ae9374-a251-4a50-ba31-4c56d528af8e` `SUCCESS`) alındı.

> **`[cross-lane]` Notu (2026-11-19 · v4.53.0 · Railway Canlıda):** Kullanıcı onaylı `implementation_plan.md` ve `"canlıya al"` talimatı kapsamında (1) otomatik `scrollIntoView` kullanmadan Hero kontrollerini sabit tutan `momDrawerReveal` kehribar açılış halesi, başka sekmedeyken tıklanabilir `"☕ Anne Molası hazır — Gör ➔"` bildirimi ve ilk uyku `mishil_sleep_delight_seen` yıldız kalkanı, (2) `breast` profillere özel kilit ekranına dayanıklı (`timestamp-delta` + `localStorage` + `180 dk` tavan) Tek Elle Sol/Sağ Canlı Emzirme Sayacı, son göğüs hafızası ve seans bitişinde sıfır Paywall kesintili `💾 Emzirmeyi Kaydet` / `🌙 Memede Uyudu` geçişi (`formula`/`solid` profillerde hızlı `ml` önde korunur), (3) `#mom-break-drawer` `mode: 'sleep' | 'nursing'` ortak kullanımı + `TR/EN/DE` `nursing_water` & `nursing_burp_help` eş fısıltıları, `RoutineLog.details_json` yapısal `side / leftMin / rightMin` aile senkronu ve `62` yeni `EN/DE` sözlük çifti (`missingTrTextsCount: 0`) `public/app.html`, `app/api/v1/endpoints/family.py`, `mobile/app.config.ts`, `mobile/features/webview/offlineHtml.generated.ts` ve test dosyaları üzerinde tamamlanarak `origin/main` ve Railway canlı ortamına aktarıldı. Seviye 3 gerçek 3-ajanlı denetimde **Claude Code CLI (`task-54` ➔ `task-96` ➔ `task-274`: `FINAL_VERDICT: PASS`)**, **Codex CLI (`gpt-6-luna`, `task-71` ➔ `task-97` ➔ `task-275`: `FINAL_VERDICT: PASS`)** ve **Antigravity** (`52/52 pytest`, `10/10 suite / 70 Jest`, `tsc --noEmit` 0 hata, `EXACT_OFFLINE_SYNC: true`, `7/7 READY_FOR_RELEASE`) onayları alındı.

> **`[cross-lane]` Notu (2026-11-18 · v4.52.2 · Railway Canlıda):** Kullanıcı onaylı `implementation_plan.md` ve `"canlıya al"` talimatı kapsamında `/ios` ve `/download` akıllı mağaza köprüsünde `"Mışıl Baby Açılıyor..."` ara HTML ekranı ve ikinci tıklama adımı kaldırılarak gerçek kullanıcılara `<1 ms` içinde doğrudan `HTTP 302 Found` (`iOS` ➔ `https://apps.apple.com/app/id6809223195`, `Android` ➔ `https://play.google.com/store/apps/details?id=com.levitas.misilbaby`) dönülecek, Meta inceleme botlarına (`BOT_SIGNATURES`) ise işletme/uygulama kısıtına takılmamak üzere `200 OK` resmi `public/index.html` sunulacak şekilde `app/main.py`, `app/api/v1/endpoints/analytics.py` ve `tests/test_sleep_and_analytics_remediation.py` güncellenerek `origin/main` ve Railway canlı ortamına aktarıldı. Seviye 3 gerçek 3-ajanlı denetimde **Claude Code CLI (`task-312` ➔ `task-413` ➔ `task-454`: `FINAL_VERDICT: PASS`)**, **Codex CLI (`gpt-6-luna`, `task-314` ➔ `task-410` ➔ `task-451`)** ve **Antigravity** (`51/51 pytest`, kokpit `200 OK`) ile çıplak Railway domaini `CF-Ray` / `CF-Connecting-IP` spoofing kilidi (`TRUST_CLOUDFLARE_HEADERS`), `pg_advisory_xact_lock` `db.rollback()` koruması ve `store_jumps_tracked = len(unique_human)` düzeltmeleri doğrulandı.

> **`[cross-lane]` Notu (2026-11-18 · v4.52.1 · Railway Canlıda):** Kullanıcı onaylı `implementation_plan.md` ve `"canlıya al"` talimatı kapsamında `/ios` ve `/download` akıllı mağaza köprüsünde gecikmeyi (`~1 ms` TTFB, `capture_bridge_click_context` + `BackgroundTasks` + `_SCHEMA_INITIALIZED`) ve mağazanın Instagram tarayıcısı içinde açılmasını önleyen doğrudan yerel mağaza uyandırma motoru (`itms-apps://` + `instagram://extbrowser` + `intent://` `com.android.vending`) ile kokpit sayım zırhlaması (`_BRIDGE_CLICK_LOCK` + `pg_advisory_xact_lock`, `extract_trusted_client_ip`, iPadOS `Macintosh` UA öncelik sıralaması) `app/main.py`, `app/api/v1/endpoints/analytics.py` ve `tests/test_sleep_and_analytics_remediation.py` üzerinde tamamlanarak `origin/main` ve Railway canlı ortamına aktarıldı. Seviye 2 ikili denetimde **Claude Code CLI (`task-102` ➔ `task-131` ➔ `task-161` ➔ `task-178`: `CLAUDE_VERDICT: PASS`)** ve **Antigravity** (`51/51 pytest`, `INTERSTITIAL_JS_SYNTAX_OK`) onayları alındı.

> **`[cross-lane]` Notu (2026-11-15 · v4.52.0 · Railway Canlıda):** Kullanıcı onaylı `implementation_plan.md` ve canlıya alma talimatı kapsamında **Konu 1 (Ortak Tek Bebek Aile Takibi Netliği, `max_members = 3`, PostgreSQL Kalıcılığı, `SubscriberLedger` VIP Doğrulaması, HMAC `realtime_token` WS & `Build 70` `family_vip` Uyumu)** ve **Konu 2 (`☕ Bebek Uyuyor • Anne Molası` Çekmecesi + Mışıl Dadı `💛 Kendim İçin` `audience="mom"` Öz-Şefkat Modu)** geliştirilerek `origin/main` ve Railway canlı ortamına aktarıldı (`app/db/models.py`, `app/main.py`, `app/core/config.py`, `app/api/v1/endpoints/family.py`, `baby.py`, `sleep.py`, `coach.py`, `analytics.py`, `app/services/subscription.py`, `ai_sleep_coach.py`, `services/function_bun/index.ts`, `public/app.html`, `mobile/app.config.ts`, `mobile/features/webview/offlineHtml.generated.ts`, `tests/**`). Seviye 3 gerçek 3-ajanlı denetimde **Claude Code CLI (`task-518` ➔ `task-583`: `VERDICT: ONAYLANDI (PASS)`)**, **Codex CLI (`gpt-6-luna`, `task-519` ➔ `task-584` ➔ `task-617`: `VERDICT: ONAYLANDI (PASS)`)** ve **Antigravity** (`50/50 pytest`, `9 suite / 65 Jest`, `tsc --noEmit` sıfır hata, `7/7 READY_FOR_RELEASE`) onayları alındı.

> **`[cross-lane]` Notu (2026-11-15 · v4.51.3 · `[Solo-Antigravity]` · Railway Canlıda):** Harici CLI erişimi güvenlik kancası/ortam kısıtıyla engellendiği ve kullanıcı doğrudan geliştirme + canlıya alma onayı verdiği için `public/app.html`, `mobile/app.config.ts` (`APP_VERSION = '4.51.3'`), `mobile/features/webview/offlineHtml.generated.ts` ve `mobile/tests/onboardingPlanBuilder.test.ts` dosyalarında **Mekânsal Yönelimli (Dual-Focus) Spotlight Tanıtım Turu** (sabit görünür alt menü pusulası, aktif sekme halkası + `👆` işaretçi rozeti, `📍 Nereden Ulaşılır?` adres şeridi, alt-sekme birleşik spotları, sağ üst `🌙 / ⚙️` vurgusu ve alt menü ikonlarına dokunarak ilerleme) tamamlanarak `origin/main` ve Railway canlı ortamına aktarıldı (`9 suite / 64 Jest`, `tsc --noEmit` sıfır hata, `EXACT_OFFLINE_SYNC=true`).

---

# Antigravity Devir Teslim — Mışıl Baby v4.10.0 (build 18)

> Bu belge, Claude Code oturumunda tamamlanan işleri ve **Antigravity'nin bitirmesi
> gereken kalan işleri** listeler. Kaynak plan: `projects/mishil/BUGFIX_PLAN_v4.10.0.md`.
> Tarih: 2026-09-07.

---

## 1. Tamamlanan (commit'li, PUSH EDİLMEDİ)

`projects/mishil` submodule — `main`, origin'in 2 commit önünde:
| commit | içerik |
| :-- | :-- |
| `b491ea8` | `BUGFIX_PLAN_v4.10.0.md` — 9 bulgu + iOS/Android ayrı çözüm planı |
| `25af952` | v4.10.0 build 18 kod düzeltmeleri (aşağıda) |

Parent `antigravity_core` — `main`, origin'in 2 commit önünde: `532eade`, `d61d29e` (submodule pointer).

### `25af952` neleri düzeltti
- **`loadBabyProfile()` + `saveBabyProfile()` yazıldı** — ikisi de hiç tanımlı değildi,
  çağrıldıkları her yerde `ReferenceError` atıp render'ı durduruyordu (sabit "Mina" HTML'i
  bu yüzden kalıyordu). `public/app.html`.
- Tüm `|| 'Mina'` / `|| '2026-04-11'` fallback'leri kaldırıldı → `getBaby()` tek kaynak,
  profil yoksa `null` + boş durum. Onboarding/Ayarlar inputları ön-dolu değil, doğrulamalı.
- Haftalık uyku grafiği gerçek son-7-gün kayıtlarından (`renderWeeklyChart`).
- Wonder Weeks / Gelişim Atakları alanı Analiz sekmesine geri eklendi + renderlara bağlandı.
- Sürüm notları dinamik: native `injectedJavaScriptBeforeContentLoaded` → `window.__MISHIL_APP__`;
  `CHANGELOG_ENTRIES` + `renderChangelog()`. `misil_onboarding_completed` → `mishil_onboarding_completed`
  (otomatik migrasyon).
- `hapticPulse()` çift tanımından ikincisi silindi (iOS haptik ölüydü).
- Bedava katman kaldırıldı: onboarding "Atla ➔" silindi; abonelik zorunlu; profil yoksa
  onboarding tekrar açılır. (Plan #7, Seçenek A.)
- Beslenme/bez yapılı model (`method` / `amountMl` / `durationMin` / `note`; diaper `kind`);
  ana ekran hızlı butonları detay ekranını açıyor.
- Samsung kasma: `MishilUnifiedWebView.tsx` `androidLayerType` koşullu (Android <9 `software`,
  9+ `hardware`); `.ambient-pulse` `blur(56px)`+`scale()` → `blur(40px)`+`opacity`;
  `@media (prefers-reduced-motion)` bloğu.
- Ses decode hatası: `nativeAudioPlayer.ts` 1 kez cache-bust ile tekrar dener; `app.html`
  başarısız parçayı "KULLANILAMIYOR" işaretler.
- `app.config.ts`: `APP_VERSION='4.10.0'`, `BUILD_NUMBER=18`. `offlineHtml.generated.ts` yenilendi.

Doğrulama (yeşil): app.html inline script `node --check` OK · `tsc --noEmit` OK ·
`jest` 4/4 · `mobile_compliance_checker.py` READY_FOR_RELEASE (price lint WARN — tasarım gereği).

---

## 2. KALAN İŞLER (Antigravity)

### 2.1 Push (ilk iş)
```
git -C projects/mishil push origin main      # b491ea8, 25af952
git push origin main                          # 532eade, d61d29e
```
Not: submodule working tree'de Antigravity'nin store ekran görüntüleri (`kullanici/app_store/*`,
`kullanici/google_play/*`) ve parent'ta `00_HAFIZA_VE_SISTEM.md` + vault `CHANGELOG.md`
değişiklikleri var — bunlar Claude'un işi değil, ayrı ele alınmalı.

### 2.2 #4 — Ses dosyalarını yeniden encode et (SUNUCU)
5 dosya şüpheli kısa/bozuk (kod tarafı retry + "KULLANILAMIYOR" hazır ama asıl sorun dosyalar):
| dosya | mevcut boyut |
| :-- | :-- |
| `shush_5s.mp3` | ~79 KB (~5 sn) |
| `placenta_flow.mp3` | ~100 KB |
| `hairdryer_calm.mp3` | ~133 KB |
| `fan_drone.mp3` | ~175 KB |
| `mozart_432hz.mp3` | ~422 KB |
- Hedef: CBR 128–192 kbps, 44.1 kHz, geçerli ID3, **≥30 sn dikişsiz (seamless) loop**.
- Yerler: `projects/mishil/mobile/web-preview/sounds/` **ve** Railway `mishil-production` `/sounds/`.
- Her dosyayı `ffprobe` ile doğrula (süre, bitrate, hata yok). Railway'e deploy et.
- Sonra `mishil-production.up.railway.app/sounds/<id>.mp3` HEAD → 200 + makul `Content-Length`.

### 2.3 #6 — Derin analitik rollup (v4.10.x, kendi milestone'u)
`25af952` yapılı rutin modelini kurdu. Bunun üzerine `renderAnalyticsView`'e:
- Günlük: toplam uyku, beslenme sayısı + toplam ml + ortalama aralık, bez (tür kırılımı),
  en uzun uyku, gece uyanma sayısı.
- Haftalık trend: uyku + beslenme ml (gerçek veriden).
- Mışıl Dadı payload'una (`/api/v1/coach/stream` `body`) rollup sayıları eklensin.
- Eski serbest-metin `detail` kayıtları için best-effort migrasyon (`"140 ml"` → `amountMl`).

### 2.4 Doküman senkronu
- **`RELEASE_READINESS.md` §5** — build 18 cihaz test bulgularını "Faz 2 çıktısı" olarak işle;
  altbilgi `4.9.0 (build 16)` → `4.10.0 (build 18)`.
- **`01_Features/Surdurulebilir_Mobil_Muhendislik_ve_Google_Play_API.md`** — ESKİ, düzelt:
  `targetSdkVersion >= 35` → `36`; fiyatlar `₺599,99 / ₺149,99 / ₺2.499,99` (+ ömür boyu);
  "PIN bypass akışı" ibaresini kaldır (v4.8.1'de silindi); "v4.8.0 / Sürüm 11" → v4.10.0 / build 18.
- **Vault `CHANGELOG.md` (v7.x)** — v4.8.4, v4.9.0, v4.9.1, v4.10.0 girişleri eksik.
- **`00_HAFIZA_VE_SISTEM.md`** — Mışıl Baby satırı `v4.9.0 (Build 16)` → `v4.10.0 (Build 18)`.

### 2.5 Build 18 + dağıtım (onay şart)
```
cd projects/mishil/mobile
eas build --platform android --profile production   # build 18 .aab
eas build --platform ios --profile production       # build 18 .ipa
```
- Android → Google Play Internal testing; iOS → TestFlight.
- Not: `app.html` her değiştiğinde `npm run bundle:offline` çalıştırıp
  `features/webview/offlineHtml.generated.ts` commit'lenmeli (EAS'te `../public` yok).

### 2.6 Faz 2 — cihaz testi (build 18'e özel doğrulamalar)
- [ ] **Yeni kurulum:** onboarding'de ad + doğum tarihi zorunlu; atlanamıyor; kaydetmeden ilerlenemiyor.
- [ ] **Sıfır sahte veri:** yeni bebekte ana ekran/analiz "—" veya boş durum; "Mina" / "4 Ay 12 Günlük" HİÇBİR yerde yok.
- [ ] **Eski test kurulumu** ("Atla" ile geçmiş): uygulama açılışta onboarding'i tekrar gösteriyor.
- [ ] **Gelişim Atakları:** Analiz sekmesinde "🌱 Gelişim Atakları" bölümü + 10 kart görünüyor, aktif atak doğru.
- [ ] **Samsung (A serisi / Exynos):** kaydırma/animasyon akıcı; boş ekran yok.
- [ ] **iOS:** her butonda haptik hissediliyor.
- [ ] **iOS kilitli ekran:** ninni çalmaya devam ediyor (R1).
- [ ] **Sesler:** 18 parça da çalıyor; bozuksa "KULLANILAMIYOR" görünüyor (sessiz kalma yok).
- [ ] **Beslenme:** "🍼 Beslenme" → detay ekranı; tür + ml/süre + not girilebiliyor; kayıt detayla listeleniyor.
- [ ] **Abonelik:** "Atla" yok; `activateTrialAndStart` → gerçek satın alma ekranı; iptal → uygulama açılmıyor.
- [ ] **Ayarlar > Sürüm:** `Mışıl Baby v4.10.0 (build 18)`; "Neler Yeni" modalı v4.10.0'ı en üstte gösteriyor.
- [ ] **Ayarlar > Bebek Profili:** ad/tarih düzenlenip "Kaydet" → ana ekran anında güncelleniyor (eskiden buton çalışmıyordu).
- [ ] Konsol/logcat'te `ReferenceError` yok.

### 2.7 Regresyon riski
`loadBabyProfile` / `saveBabyProfile` artık tanımlı ve `generateSleepReport`, `toggleLiveSleep`,
`toggleEarlyLeap`, `resetToAutoLeap`, `switchUserRole`, init dahil ~8 yerden çağrılıyor.
Bunların hepsi hatasız çalışmalı — özellikle onboarding → satın alma → uygulama açılışı akışı.

---

## 3. "Yaptıklarım kaydediliyor mu?" — Evet
- Kod: git commit'leri (yukarıda, `b491ea8` `25af952` / `532eade` `d61d29e`) — yerel, push bekliyor.
- Plan: `projects/mishil/BUGFIX_PLAN_v4.10.0.md` (commit'li).
- Sürüm notları: `projects/mishil/CHANGELOG.md` `[4.10.0]` girişi (commit'li).
- Bu devir belgesi: `projects/mishil/ANTIGRAVITY_HANDOFF.md`.
- Claude oturum hafızası: `~/.claude/projects/.../memory/*.md` — yalnızca Claude'un sonraki
  oturumlarında görünür, Antigravity'ye değil. Antigravity için tek kaynak: bu repo dosyaları.
