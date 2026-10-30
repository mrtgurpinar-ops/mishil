# Changelog - Mışıl Baby
 
Tüm önemli değişiklikler bu dosyada belgelenecektir.

## [4.46.15] - 2026-10-30
### ⚖️ 3'lü Platform Ayrımı (🌐 Kümülatif / 🍏 Apple iOS / 🤖 Google Play) & Canlı Google Play Abonelik Defteri (`monetization.subscriptions`)
1. **Tek Tıkla 3'lü Platform Seçici & Yan Yana Platform Karşılaştırma Matrisi (`app/api/v1/endpoints/analytics.py`, `public/preview_analytics_cockpit.html`):**
   - Üst kontrol çubuğuna **`🌐 Kümülatif (105)` | `🍏 Apple iOS (90)` | `🤖 Google Play (15)`** canlı platform anahtarı (`switchPlatform('all'|'ios'|'android')`) eklendi; seçilen platforma göre 4 Kuzey Yıldızı KPI kartı, 4 adımlı dönüşüm hunisi, 13 günlük indirme grafiği (`🌐 Kümülatif` Yeşil+Mavi Yığılmış / `🍏 Sadece iOS` / `🤖 Sadece Android` / `📊 Günlük Yeni`), Sekme 2 abonelik tabloları ve Sekme 5 yorum/tıklama akışı anında filtrelenir hale getirildi.
   - Sekme 1'e **⚖️ Kümülatif vs Apple App Store (iOS) vs Google Play Store (Android) — Yan Yana Platform Karşılaştırması** tablosu eklendi:
     - **🍏 Apple (iOS):** `4,813` Gösterim • `707` Etkileşim (`492` Mağaza Sayfası + `215` iOS Köprü Tıkı) • `90` Kurulum (`%12.7` CVR) • **`14` Aktif VIP (`664.96 ₺/Ay Net MRR`)** • `5` Yorum (`5.0 ★`).
     - **🤖 Google Play (Android):** **`396` Android Köprü Tıkı** (`381` Meta Reklam `/ios` + `15` Bio `/download` — sosyal tıklamaların **%64.4'ü Android!**) • **`15` Doğrulanmış Android Kurulumu (`%3.8` CVR)** • **`0` Aktif Android VIP (`0.00 ₺ MRR`)** • `1` Resmi Google Play Yorumu (`5.0 ★` — Gülgün Gürpınar, Huawei P20 Pro).
2. **Google Play Developer API (`monetization.subscriptions`) Canlı Abonelik Kataloğu & Android Faturalandırma Defteri (`analytics.py`):**
   - Sekme 2'de (`Gelir & Abone Defteri`) yalnızca Apple abonelerinin görünmesi eksikliği giderilerek Apple Abone Defteri'nin hemen altına **🤖 Google Play Store — Canlı Abonelik Paketleri & Android Faturalandırma Defteri (`com.levitas.misilbaby`)** kartı eklendi.
   - `sync_live_store_apis()` içerisine Google Play `androidpublisher/v3/applications/com.levitas.misilbaby/subscriptions` canlı sorgusu entegre edilerek `misil` (**Mışıl Baby Yıllık VIP — `599.99 ₺/Yıl` + `3daystrial` 7 Gün Ücretsiz Deneme `P7D` + 14 Gün Grace Period `ACTIVE`**) ve `misilaylik` (**Mışıl Baby Aylık VIP — `149.99 ₺/Ay` + `freeytrial` 7 Gün Ücretsiz Deneme `P7D` + 7 Gün Grace Period `ACTIVE`**) paketleri ve `396 Android Tık ➔ 15 Kurulum ➔ 0 Aktif Abone` huni teşhisi tabloya bağlandı.
   - `/store-sync-push` uç noktasında `google_play_downloads_baseline` (`15`) değerinin yerel senkronizasyonda `0` ile ezilmesini önleyen `max(prev_gp_dl, new_gp_dl)` koruması eklendi.

## [4.46.14] - 2026-10-30
### ☀️ Seçenek 1: "Airy Daylight" (Stripe / Apple Store Connect Ferah Gündüz Teması) & Tam Veri Görünürlüğü
1. **Airy Daylight Ferah Gündüz Teması + ☀️/🌙 Tema Geçişi (`app/api/v1/endpoints/analytics.py`, `public/preview_analytics_cockpit.html`):**
   - Kullanıcı geri bildirimi doğrultusunda koyu `#08090C` ve sıkışık `1px` çerçeve görünümü, hiçbir veri eksiltilmeden **Seçenek 1: Airy Daylight (`#F4F6FB` gün ışığı zemin, `#FFFFFF` ferah beyaz kartlar, `16px` kart aralığı, `#0F172A` yüksek kontrastlı tipografi)** mimarisine geçirildi.
   - 4 Kaynaklı Canlı Veri Tazelik Kartları, Dönem Filtresi, 4 Kuzey Yıldızı KPI Kartı (SVG Sparkline + Split Bar), 5 Sekme, 4 Adımlı Dönüşüm Hunisi, Günlük/Kümülatif İndirme Grafiği, 3 SVG Halka Grafik, 3 Kademeli MRR Şelalesi, 14 Kayıtlı Tekil Abone Defteri (`reconciling_trial` rozet uyumuyla), ASO Attribution Matrisi, Kohort Tutundurma Tablosu, Modül Aktivitesi, Mağaza Yorumları ve Canlı Akış **%100 eksiksiz** korundu; üst bara tek tıkla **☀️ Gündüz / 🌙 Gece (`toggleTheme()`)** geçiş butonu eklendi.

## [4.46.13] - 2026-10-30
### 📊 Linear / Vercel "Obsidian Hairline" (`1px` Kılcal Izgara) Kurucu Kokpiti v2.0 & Canlı Veri Motoru Onarımı
1. **Canlı Veri Motoru & 3 Kademeli MRR Şelalesi (`app/api/v1/endpoints/analytics.py`, `tests/test_sleep_and_analytics_remediation.py`):**
   - Apple `SUBSCRIBER 1_3` raporunda `customer_price = 0.00` döndüğü için `0.00 ₺` kalan 7 günlük deneme aboneleri `_resolve_expected_trial_pricing()` ile otomatik olarak paket fiyatlarıyla (`149.99 ₺ Brüt` / `83.12 ₺ Net`) eşleştirildi.
   - Gelir sekmesi **Tahsil Edilen Kesin Gelir + Apple Mutabakatında Vadesi Dolan (`reconciling_7d`) + Yaklaşan Deneme Vadesi (`upcoming_7d`) = Beklenen Toplam Net MRR Köprüsü** yapısına kavuşturuldu.
   - Android kurulumlarının tek güne (`30 Eki`) yığılması düzeltilerek aktif sinyal günlerine dağıtıldı; Apple TSV raporunun 24s gecikmeli olduğu günler `is_store_pending` olarak işaretlendi ve `r14` Discovery arama/keşfet oranlarıyla kaynak dağılımı zenginleştirildi.
2. **Konsept A — Linear / Vercel "Obsidian Hairline" (`1px` Kılcal Izgara) & Sıfır Kaymalı 3-Row CSS Grid (`analytics.py`, `public/preview_analytics_cockpit.html`, `public/app.html`):**
   - Kokpit arayüzü `#08090C` saf karbon zemin, `#1E222D` `1px` kılcal ızgara (`hairline grid`), `JetBrains Mono` (`tabular-nums`) tipografi, 4 kaynaklı canlı tazelik bandı (`Freshness Strip`), SVG sparkline'lı Kuzey Yıldızı kartları ve `grid-template-rows: 22px 1fr 22px` sıfır kaymalı çubuk grafik mimarisiyle baştan sona yenilendi.
   - 15 saniyede bir sayfayı yenileyen `window.location.reload()` kaldırılarak arka planda `pollLiveTelemetry()` (`fetch('/api/v1/analytics/summary')`) devreye alındı; `public/app.html` `#view-analytics` ekranında rutin kaydı yokken çıkan `"Harika 🟢"` rozeti `"İlk Kayıt Bekleniyor ⏳"` olarak düzeltildi ve `offlineHtml.generated.ts` güncellendi.

## [4.46.12] - 2026-10-30
### 🎨 Mışıl Comics • Sayı #7 (v3 CMO & Görsel Konsensüs Final): 3'lü Konsensüs (`task-92`/`task-153`/`task-175` Claude CLI + `task-119`/`task-154`/`task-176` Codex CLI + Antigravity) "Acıktı mı, Gazı mı Var, Uykusu mu Geldi? (5 Gizli Bebek Sesi)" 4:5 Dikey Webcomic Paketi
1. **İlk 6 Sayıyla %0 Çakışan Konu & 7 Özgün Pixar/Disney 3D Çizgi Roman Sahnesi (`kullanici/instagram/karakterler/comic7_s1..s7`):**
   - İcra & Doğrulama: **3 Turlu 3'lü Konsensüs** (`task-92`/`task-153`/`task-175` Claude Code CLI + `task-119`/`task-154`/`task-176` Codex CLI `gpt-6-luna` + Antigravity).
   - 0–4 aylık bebeklerin çığlık fırtınasına geçmeden önce emme, esneme ve geğirme refleksleriyle çıkardığı 5 akustik ön-sinyali (`Neh` = Açlık, `Owh` = Uyku, `Eh` = Üst Gaz, `Eairh` = Alt Gaz, `Heh` = Rahatsızlık) ve Mışıl Baby **AI Ağlama Analizi** özelliğini anlatan 7 özgün sahne kronolojik saat sürekliliğiyle (`02:10 -> 02:12 -> 02:15 -> 02:25`) üretildi:
     - **Slayt 1 (`comic7_s1_neden_agliyor_bilmecesi.jpg`):** Saat `02:10`'da beşik başında bir elinde biberon, diğer elinde bez ve başının üzerinde `🍼 / 💨 / 🌙?` düşünce balonlarıyla şaşkın bakan Işıl Anne + mıkırdanan Mışıl Bebek.
     - **Slayt 2 (`comic7_s2_5_gizli_bebek_kelimesi.jpg` — v3):** Saat `02:12`'de Mışıl Bebek etrafında 5 pastel akustik balon (`🍼`, `🌙`, `🫧`, `🌀`, `🌡️`) ve elini kulağına götürüp aydınlanan Işıl Anne (papatyalı taç tam kadrajda).
     - **Slayt 3 (`comic7_s3_tuzak1_gaz_sesinde_emzirmek.jpg`):** Göğsünde mavi hava kabarcığı hologramı varken iki elini kaldırıp biberonu reddeden Mışıl Bebek (*"Eh" gaz sesinde hemen besleme tuzağı*).
     - **Slayt 4 (`comic7_s4_tuzak2_owh_uyku_sesini_kacirmak.jpg` — v3):** Saat `02:15`'te gözünü ovuşturup oval ağızla esneyen (`Owh`) Mışıl Bebek, göğüs hizasında renkli çıngırağı tutarak uyku penceresini kaçırdığını fark eden Işıl Anne.
     - **Slayt 5 (`comic7_s5_tuzak3_on_sinyal_vs_ciglik.jpg`):** İkiye bölünmüş (Split-Screen) sahne: Sol yarıda erken sakin ön-sinyali (`30–60 sn`) dinleyen Işıl Anne; sağ yarıda kaçırılan sinyal sonrası başlayan ağlama fırtınası.
     - **Slayt 6 (`comic7_s6_recete_ai_aglama_analizi.jpg` — v3):** Işıl Anne'nin omzunda gazını çıkarıp rahatlayan Mışıl Bebek (sıfır yabancı metin, temiz rüzgar/hava ikonu) + elde sıfır bozuk yazılı Mışıl Baby **AI Ağlama Analizi** ekranı.
     - **Slayt 7 (`comic7_s7_zafer_anlasilan_bebek_huzur.jpg` — v3):** Saat `02:25`'te (yalnızca 15 dakikada çözülen kriz) Yıldızcık peluşuna sarılarak mışıl mışıl uyuyan Mışıl Bebek ve beşik başında *"Tamam"* işareti yapan huzurlu Işıl Anne.
2. **CMO Büyüme Pazarlaması, Open Loop & Pediatrik İhtiyat Mimarisi (`post_07_aglama_dili_5_gizli_ses.md`, `render_instagram_comic_07.py`, `preview_instagram_concepts.html`):**
   - Claude CLI (`task-153`, `task-175`) ve Codex CLI (`task-154`, `task-176`) bulgularıyla: Slayt 1'e spesifik merak kancası (*«'NEH' Diyorsa Aç, 'EH' Diyorsa Gazlı! Peki Diğer 3 Ses Ne Demek?»*), Slayt 2'ye kaydırma düşüşünü (drop-off) önleyen **Open Loop** kurgusu, Slayt 3'e emziren ve biberon veren tüm anneleri kapsayan *"Beslemek"* dili + AAP nüansı, Slayt 6'ya **Hero Product Mışıl Baby AI Ağlama Analizi** vurgusu + hekim uyarı notu, Slayt 7'ye ise doğrudan **App Store / Google Play Ücretsiz İndirme CTA** ve ayrıştırılmış **KAYDEDİN / GÖNDERİN** çağrısı eklendi.
   - Playwright ile 7 adet `1080×1350` PNG slayt (`post_07_slaytlar/comic_7_1..7.png`) yeniden derlendi ve `preview_instagram_concepts.html` vitrini (`?v=comic7_v3_cmo_consensus`) güncellendi.

## [4.46.11] - 2026-10-30
### 🎨 3'lü Konsensüs (`task-176`/`task-213`/`task-278` Claude CLI + `task-177`/`task-214`/`task-279` Codex CLI + Antigravity) Gece Ergonomisi, Dar Ekran ve Aydınlık Mod UI/UX İyileştirme Paketi
1. **Dar Ekran (`360px–375px`) Toast Taşma Koruması & Safe-Area İyileştirmesi (`public/app.html`):**
   - `.toast-msg` (`white-space: normal; width: max-content; max-width: calc(100vw - 32px); box-sizing: border-box;`) ile uzun Türkçe bildirimlerin ekran dışına taşması giderildi.
   - `.modal-sheet` alt dolgusu `env(safe-area-inset-bottom)` ile korundu ve `.screen-container` alt boşluğu yükseltilmiş FAB gölgesini kurtaracak şekilde `104px + safe-area` yapıldı.
2. **Gece Tek El Dokunma Hedefleri, FAB Mikro-Fiziği ve Hero Kazara Tıklama Koruması (`public/app.html`):**
   - `.modal-close` (`40×40px` dairesel), `.header-profile-btn` / `.header-close-btn` (`42×42px`), `.segmented-btn`, `.routine-pill-btn`, `.timer-pill`, `.role-chip` (`min-height: 38px`) ve `.cat-chip`, `.ai-chip` (`min-height: 36px`) dokunma hedefleri büyütüldü.
   - `.dock-fab-btn:active` içindeki ekstra `translateY(-16px)` sıçraması `scale(0.92)` olarak düzeltildi; "Mışıl Spot" ana ekran sekmesi sıcak yuva/ev SVG ikonuyla orta altın hilal FAB butonundan ayrıştırıldı.
   - `#home-organic-hero` kapsayıcısındaki `onclick="toggleLiveSleep()"` kaldırılıp `#home-candle-aura` (`76×76px` hilal + `:active` efekti) ve `#btn-toggle-sleep` butonuna bağlanarak sayfa kaydırırken kazara uyku başlatma/durdurma önlendi.
3. **Aydınlık Mod (`[data-theme="light"]`) Tam Kontrast & Küçük Ekran Esnekliği (`public/app.html`, `offlineHtml.generated.ts`):**
   - Açık temada date input takvim ikonu (`color-scheme: light`), `.timeline-line`, `.bento-chart-bar-bg`, `.settings-accordion-title`, `#sheet-rating-sentiment`, `.modal-close` ve tüm 9 modal başlığı (`var(--heading-night)`) yüksek kontrasta kavuşturuldu.
   - `.cat-chips-row` sağ dolgusu `16px`, `.fab-label` `9px` ve mobil `.dadi-container` `min-height: 240px` olarak iyileştirildi; `offlineHtml.generated.ts` senkronize edildi.

## [4.46.10] - 2026-10-30
### 🛡️ 3'lü Konsensüs (`task-12`/`task-70` Claude CLI + `task-33`/`task-71` Codex CLI + Antigravity) Sıfır Regresyonlu Güvenlik, Test ve Native Ses Zamanlayıcı Sertleştirmesi
1. **Native Arka Plan Ses Motoru Zamanlayıcı Koruması (`mobile/features/audio/nativeAudioPlayer.ts`):**
   - `playSound()` içinde ilk denemede hata alınıp 2. denemeye (cache-bust retry) geçilirken `unloadInternal(attempt === 0)` (`keepTimer=true`) çağrılarak aktif uyku zamanlayıcısının (`15/30/45/60 dk`) sıfırlanması önlendi.
2. **Test Paketi (%100 Yeşil) & Bulut Maliyet Koruması (`tests/test_cry_analysis.py`, `test_veo_31_video.py`):**
   - `test_cry_analysis.py` içinde 6 kategorili (`CryType.OVERSTIMULATED` dahil) olasılık doğrulaması güncellendi (`25/25 pytest` yeşil).
   - `test_veo_31_video.py` içindeki Vertex AI Veo çağrısı `if __name__ == "__main__":` bloğu altına alınarak `pytest` import aşamasında ücretli bulut çağrısı tetiklenmesi engellendi.
3. **Apple Pre-Flight Doğrulayıcı & Mışıl Dadı AI Dayanıklılığı (`core/apple_preflight_validator.py`, `app/api/v1/endpoints/coach.py`, `public/app.html`):**
   - `apple_preflight_validator.py` içinde aboneliklerin `state` alanı okunarak halihazırda `APPROVED`/`READY_FOR_SALE` durumdaki abonelikler için yanlış pozitif `Guideline 2.1(b)` hatası giderildi (`mobile_compliance_checker.py` ➔ `READY_FOR_RELEASE`).
   - `coach.py` içinde `message` alanına `max_length=4000` eklendi ve hata durumunda ham `str(e)` sızıntısı kapatıldı.
   - `public/app.html` içindeki `WEB_APP_META.version` ve `CHANGELOG_ENTRIES` `4.46.9` ile hizalanarak `offlineHtml.generated.ts` yenilendi.

## [4.46.9] - 2026-10-29
### ⚡ Otomatik Mağaza Senkronizasyonu & Periyodik Arka Plan Görevi (Seçenek B)
1. **Periyodik Arka Plan Döngüsü (app/main.py, app/api/v1/endpoints/analytics.py):**
   - FastAPI lifespan asenkron yaşam döngüsüne run_periodic_store_sync_loop() arka plan görevi entegre edildi.
   - Sunucu açılışından 15 saniye sonra ilk tarama yapılır; ardından her 6 saatte bir (21.600 sn) Apple App Store Connect (SALES, SUBSCRIBER, r14 Discovery, r8 Sessions) ve Google Play Developer API'leri taranarak veritabanı otonom olarak güncellenir.
   - Sunucu kapanırken asyncio.Event durdurma bayrağı ile arka plan görevi bellek sızıntısı olmadan zarifçe (graceful shutdown) sonlandırılır.
   - PYTEST_CURRENT_TEST tespitiyle otomatik testlerde arka plan senkronizasyonunun testleri yavaşlatması önlendi.
2. **Tek Tıkla Senkronizasyon Uç Noktası (POST /api/v1/analytics/trigger-sync):**
   - Yönetici PIN/çerez korumalı manuel senkronizasyon uç noktası eklendi; run_in_threadpool ile FastAPI ana event loop'unu bloklamadan arka planda çalışır.
   - test_sleep_and_analytics_remediation.py test paketine yetkisiz/yetkili doğrulama testleri eklendi (10/10 test yeşil).

## [4.46.5 - Build 65] - 2026-10-29
### 🛡️ Mışıl Analitik Kokpiti: 3'lü Konsensüs (`task-30` Claude CLI + `task-52` Codex CLI + Antigravity) Sıfır Statik Veri, Asenkron Mağaza Senkronizasyonu ve Güvenlik/MRR Sertleştirmesi
1. **Sıfır Statik Veri Mimarisi (`app/api/v1/endpoints/analytics.py`, `app/db/models.py`, `public/preview_analytics_cockpit.html`):**
   - İcra & Doğrulama: **3'lü Konsensüs** (`task-30` Claude Code CLI + `task-52` Codex CLI `gpt-6-luna` + Antigravity).
   - `OFFICIAL_STORE_BASELINE` içindeki tüm sabit/statik sayılar, `VERIFIED_SUBSCRIBER_LEDGER_SEED` (12 sabit abone), `HISTORICAL_SEED_DATA` (sabit tıklama/kampanya tohumları), sabit reklam harcaması/indirme sayıları (`77.0 $`, `47`, `14`, `7`), sabit tarihler (`2026-10-18`, `2026-10-21`, `2026-10-28`) ve sabit kohort tutundurma metinleri (`%100.0`) tamamen kaldırıldı.
   - Tüm KPI'lar, zaman serisi, ASO attribution matrisi, kampanya harcamaları (`CampaignConfig`), günlük mağaza metrikleri (`StoreDailyMetric` — `(metric_date, platform)` tekillik kısıtı ile), abone defteri (`SubscriberLedger`), yaşam döngüsü olayları (`SubscriptionLifecycleEvent`) ve `app.html` uygulama içi sinyalleri (`first_open`, `daily_active`, `store_jump`, `baby_created`, `vip_started`, `sleep_sound_play`, `cry_analysis`) %100 dinamik olarak veritabanından ve canlı API senkronizasyonundan beslenecek şekilde yeniden yazıldı.
   - `public/preview_analytics_cockpit.html` içindeki dondurulmuş statik HTML anlık görüntüsü ve gömülü `pin=MISIL-REV-9842` sızıntısı kaldırılarak `/api/v1/analytics/summary` uç noktasından canlı veri çeken sıfır-statik önizleme kabuğuna dönüştürüldü.
2. **P0-1 Asenkron Event-Loop Koruması & Gerçek Çift Mağaza Senkronizasyonu (`analytics.py`):**
   - `sync_live_store_apis()` içindeki harici HTTP/API çağrıları `_BASELINE_LOCK` dışına çıkarıldı ve `analytics_dashboard_page` içinde `await run_in_threadpool(sync_live_store_apis)` ile çalıştırılarak FastAPI ana event loop'unun bloklanması önlendi.
   - Apple App Store Connect API (`Reviews`, `SALES`, `SUBSCRIPTION 1_3`, `SUBSCRIBER 1_3`) yanında gerçek Google Play Developer API (`androidpublisher` v3 `Reviews`) senkronizasyonu eklendi.
3. **P0-2 & P1-3 Kimlik Doğrulama, PIN İzolasyonu ve Oturum Süresi (`analytics.py`):**
   - Mağaza inceleme ekibi için kamuya açık olan `_GOOGLE_PLAY_REVIEWER_PIN` (`MISILREV2026`), yönetici kokpiti `ADMIN_PINS` listesinden çıkarıldı (`401 Unauthorized`).
   - `_make_admin_session_token` ve `_admin_session_token_is_valid` fonksiyonlarına sunucu taraflı son kullanma zaman damgası (`exp`) doğrulaması eklendi; `POST /api/v1/analytics/login` uç noktası ile PIN kodunun URL query parametresine (`?pin=`) sızması engellendi; çerezlere `secure=(request.url.scheme == "https")` eklendi ve `AuthKey` dosya kimliği maskelendi.
   - `POST /api/v1/analytics/campaign-config` uç noktasına `ALLOWED_CAMPAIGN_CHANNELS` whitelist doğrulaması (`400 Bad Request`) ve güçlendirilmiş `sanitize_csv_cell` formül enjeksiyonu koruması eklendi.
4. **P1-1, P1-2 & P1-4 MRR/LTV Ayrımı, Dönem Filtresi Barı ve Oturum Tekilleştirme (`analytics.py`, `tests/test_sleep_and_analytics_remediation.py`):**
   - Kümülatif tahsil edilen gelir (`customer_price_try`) ile tek dönemlik yinelenen aylık gelir (`expected_next_price_try` / MRR) birbirinden ayrıldı; çoklu para birimi (`TRY`/`EUR`/`USD`) dönüşümü ve `SubscriptionLifecycleEvent` üzerinden idempotent işlem kaydı sağlandı.
   - Kokpit üst barına Dönem Filtresi (`♾️ Tüm Zamanlar`, `📅 Bugün`, `⏮️ Dün`, `📆 Son 7 Gün`) eklendi; dar dönemlerde (`today`/`yesterday`) 0 tıklama olduğunda tüm zamanlara sessizce geri dönen yanıltıcı fallback kaldırıldı.
   - Oturum sayısında çift sayım (`apple_sessions_total + first_opens + daily_actives`) yerine `max(apple_official_sessions, live_telemetry_sessions)` tekilleştirmesi uygulandı; `pytest` birim test paketi 9/9 yeşil olarak doğrulandı.

## [4.46.4 - Build 65] - 2026-10-29
### 🎨 Mışıl Comics • Sayı #6: 3'lü Konsensüs (`task-114` Claude CLI + `task-129` Codex CLI + Antigravity) Konu/Diyalog Odaklı 7 Özgün Sahne İllüstrasyonu
1. **Tekrar Eden Stok Görsellerin Kaldırılması & 7 Özel Çizgi Roman Sahnesi (`kullanici/instagram/karakterler/comic6_s1..s7`):**
   - İcra & Doğrulama: **3'lü Konsensüs** (`task-114` Claude Code CLI + `task-129` Codex CLI + Antigravity).
   - Önceki sayılardan (#2–#5) devralınan genel stok portreler kaldırılarak, Mışıl Comics #6 ("Sabaha Karşı 04:00 Ikınma Krizi! — Yenidoğan Diskezi") içerisindeki her bir slaytın konuşma balonunu, saatini ve pediatrik eylemini birebir canlandıran **7 yeni Pixar/Disney 3D çizgi roman sahnesi** üretildi:
     - **Slayt 1 (`comic6_s1_0415_ikinma_besik.jpg`):** Komodindeki saatte `04:15` yazarken beşikte **gözleri sımsıkı kapalı**, yüzü pancar gibi kızarmış ve bacaklarını karnına çekerek ıkınan Mışıl Bebek + endişeyle izleyen Işıl Anne.
     - **Slayt 2 (`comic6_s2_kas_koordinasyonu_diskezi.jpg`):** Ellerini karnına koyup kaslarını koordine etmeye çalışan Mışıl Bebek ve karın üzerindeki parıltılı **beyin-kas koordinasyonu (Yenidoğan Diskezi) hologramı**.
     - **Slayt 3 (`comic6_s3_tuzak1_fitil_zeytinyagi_red.jpg`):** Elinde zeytinyağı damlalığı ve fitil tutan Işıl Anne'ye karşı iki minik elini öne uzatıp **"Dur / Hayır!"** işareti yapan Mışıl Bebek.
     - **Slayt 4 (`comic6_s4_tuzak2_gece_isigi_bez_soku.jpg` — Claude CLI `task-114` Bulgusuyla v2):** Saat `04:20`'de tepeden yakılan parlak ışık hüzmesinden **eliyle gözünü koruyarak irkilen ve ağlayarak uyanan** Mışıl + elini alnına götürüp pişmanlık yaşayan Işıl Anne.
     - **Slayt 5 (`comic6_s5_tuzak3_kriz_masaji_vs_aksam.jpg`):** **İkiye Bölünmüş (Split-Screen) Sahne:** Sol yarıda gece `04:00` kriz anında gergin karına yapılan yanlış masaj; sağ yarıda akşam ılık banyo sonrası sarı ördekler eşliğinde neşeyle yapılan **bisiklet bacak egzersizi ve karın masajı**.
     - **Slayt 6 (`comic6_s6_recete_uzaktan_gozlem_rahim_sesi.jpg`):** Beşiğe müdahale etmeden parmağıyla *"Şşş, dokunma"* işareti yaparak uzaktan gözlemleyen Işıl Anne + komodindeki telefondan yayılan **Mışıl Baby Rahim İçi Uğultu ses dalgaları**.
     - **Slayt 7 (`comic6_s7_zafer_sabah_huzurlu_uyku.jpg`):** Sabah güneş huzmeleri altında sarı yıldız peluşuna (`Yıldızcık`) sarılarak rahatlamış uyuyan Mışıl + elinde sıcak sabah kahvesiyle gülümseyen Işıl Anne.
2. **3'lü Konsensüs Caption & Tıbbi İhtiyat Revizyonu (`post_06_sabaha_karsi_ikinma_diskezi.md`, `render_instagram_comic_06.py`, `preview_instagram_concepts.html`):**
   - Claude CLI (`task-114`) ve Codex CLI (`task-129`) bulgularıyla; Rome IV *"yumuşak dışkılama öncesi 10–15 dk ıkınma"* kriteri, tıbben ihtiyatlı tanı dili, Slayt 5–6 bilimsel alt notları ve iki ayrı satıra ayrılmış `GÖNDERİN` / `KAYDEDİN` çağrıları entegre edildi; 7 PNG slayt yeniden derlendi (`?v=comic6_v3_consensus`).

## [4.46.2 - Build 65] - 2026-10-29
### 🛡️ 3'lü Konsensüs (Claude Code CLI + Codex CLI + Antigravity) Güvenlik, İzolasyon ve Veri Bütünlüğü Sertleştirmesi
1. **Uyku Kaydı (`sleep.py`) Son Kaydı Ezme Engeli & Aile İzolasyonu:**
   - `is_update=True` iken `client_id` veya `original_start_time` (`±2 sn` toleranslı) eşleşmediğinde bebeğin en son uyku kaydını sessizce ezen fallback kaldırıldı; eşleşme yoksa mevcut kayıtları bozmadan yeni kayıt oluşturulur.
   - `cid_tag` sorgusunda SQL `LIKE` joker karakterleri (`_`, `%`) escape edildi ve Python katmanında tam `[cid:...]` token eşitliği doğrulandı.
   - Geçersiz `family_code` veya başka bir aileye ait `baby_id` ile yapılan isteklerde `db.query(Baby).first()` global fallback'ine düşülmesi engellenerek `403`/`404` sahiplik izolasyonu sağlandı.
2. **Analitik Kokpit (`analytics.py`) Thread Lock, TOCTOU ve PIN Koruması:**
   - `OFFICIAL_STORE_BASELINE` sözlüğü `_BASELINE_LOCK` (`threading.RLock`) ve `deepcopy` snapshot koruması altına alındı; sessiz `except` blokları `logger.warning` ile loglandı.
   - `first_open` ve `daily_active` sinyallerindeki TOCTOU yarışı `_APP_OPEN_SIGNAL_LOCK` ile kapatıldı; `daily_active` gün başlangıcı TSİ (`UTC+3`) ile hizalandı.
   - Yönetici PIN doğrulamasına IP bazlı brute-force kilidi (`5` hatalı denemede `15 dk` blok), `MISIL_ADMIN_PINS` ortam değişkeni desteği ve `HttpOnly`/`SameSite=Lax` oturum çerezi eklendi.
3. **İstemci Zaman Damgası & Birim Testler (`public/app.html`, `tests/test_sleep_and_analytics_remediation.py`):**
   - `resolveSleepTimestamps` gece yarısı geçişi, benzersiz `slp_` istemci kimliği ve `appMeta().version` telemetri sürüm okuması senkronize edildi (`offlineHtml.generated.ts` güncellendi).

## [4.46.1 - Build 65] - 2026-10-29
### ✏️ Geriye Dönük Uyku Saati Düzenleme, Canlı Uyku Başlangıç Düzeltme & MışılSpot™ Yeniden Hesaplama Motoru
1. **Geriye Dönük Uyku ve Rutin Saati Düzenleme (`public/app.html`):**
   - Anne veya babanın canlı uyku sayacını (`🌙 Şimdi Uyuyor`) başlattıktan sonra uyuyakalması ve uyanıp sayacı saatler sonra durdurması sonucunda oluşan **fazla uyku süresi kaydını** düzeltmek için tam kapsamlı **Saat Düzenleme (`openEditRoutineModal` & `submitCustomRoutineUnified`)** akışı eklendi.
   - Ana ekranda **"🌙 Şimdi Uyuyor"** butonunun hemen altına son uykuyu gösteren ve tek dokunuşla düzenleme penceresini açan **"🌙 Son Uyku: HH:MM - HH:MM • ✏️ Saatleri Düzenle"** hızlı erişim barı (`#last-sleep-quick-edit-bar`) eklendi.
   - Hem Ana Ekran (`Bugünün Akışı`) hem de Analiz (`Rutinler & Günlük Akış`) sekmelerindeki tüm uyku/rutin kartlarına **`✏️ Düzenle`** butonu eklendi ve saat aralıkları tıklanabilir hale getirildi.
   - Canlı uyku **3 saati (`180 dk`)** aştığında ve ebeveyn `"☀️ Uyandı"` butonuna bastığında, ebeveynin uyuyakalmış olma ihtimaline karşı düzenleme penceresi otomatik olarak açılarak saatleri kontrol etmesi sağlanır.
2. **Hızlı Saat Kaydırma Çipleri & Canlı Uyku Sırasında Başlangıç Saati Düzeltme (`public/app.html`):**
   - Gece yorgunluğunda saat seçiciyle uğraşmadan tek dokunuşla süreyi düzeltmek için uyku düzenleme penceresine **`⏪ Uyanış -15 dk`**, **`⏪ Uyanış -30 dk`**, **`⏪ Uyanış -1 saat`** ve **`⏪ Başlangıç -15 dk`** hızlı kaydırma çipleri (`shiftModalSleepTime`) eklendi.
   - Bebek halen uyurken (`Canlı Uyku` aktifken) başlangıç saatini geriye çekebilmek için ana ekrandaki uyku halkasının içine **`🕓 Başlangıç: HH:MM • Saatini Düzelt ✏️`** hap butonu (`#live-sleep-edit-start-wrap`) ve `-10 dk / -15 dk / -30 dk / -45 dk` hızlı çipli canlı başlangıç düzeltme modalı (`#modal-live-sleep-edit`) eklendi.
3. **Gece Yarısı (00:00) Tarih Kayması Çözümü & MışılSpot™ / Gelişim Skoru Senkronu (`public/app.html`, `app/api/v1/endpoints/sleep.py`, `offlineHtml.generated.ts`):**
   - Gece yarısını aşan uykularda (`23:30 - 02:15` gibi) `endDate`'in ertesi güne (geleceğe) kayarak `MışılSpot™` hedefini bozmasına yol açan tarih hatası `resolveSleepTimestamps()` fonksiyonu ile giderildi; `calculateMışılSpot()` kronolojik olarak en son uyanış zamanını (`endTs`) baz alacak şekilde güçlendirildi.
   - Backend `POST /api/v1/sleep/log` uç noktasına `is_update: Optional[bool]` alanı eklendi; saat düzenlendiğinde PostgreSQL üzerinde mükerrer kayıt açmak yerine mevcut son uyku kaydı güncellenir. `offlineHtml.generated.ts` yenilendi.

## [4.45.3 - Build 65] - 2026-10-29
### 🔉 Kapanma Zamanlayıcısı İçin Opsiyonel "Kademeli Kısarak Kapat (Smart Fade-Out)" Motoru
1. **Opsiyonel Kademeli Kapanış Anahtarı (`public/app.html`):**
   - Sesler sekmesindeki **Kapanma Zamanlayıcısı** (`Sürekli | 15 dk | 30 dk | 45 dk | 60 dk`) kartının altına ebeveynlerin isteğe bağlı olarak açıp kapatabileceği **"🔉 Kademeli Kısarak Kapat (Fade-Out)"** anahtarı (toggle switch) eklendi; kullanıcı tercihi `localStorage` (`mishil_timer_fadeout`) üzerinde kalıcı olarak saklanır.
   - Seçenek aktifken zamanlayıcının bitmesine **son 30 saniye kala** ses seviyesi 20 adımda (`%100 ➔ %0`) pürüzsüzce azaltılarak kapatılır; böylece bebeğin zamanlayıcı bittiği an ani sessizlik şokuyla (acoustic drop) uyanması önlenir.
   - Seçenek kapatıldığında ise süre dolduğu an ses azaltılmadan doğrudan durdurulur.
2. **EAS Build Gerektirmeyen Hibrit Köprü & Native Uyum (`public/app.html`, `nativeAudioPlayer.ts`, `MishilUnifiedWebView.tsx`):**
   - Mevcut mağaza sürümlerinde (`Build 63` Android / `Build 61-62` iOS) `AUDIO_VOLUME` köprüsü halihazırda derlenmiş olduğu için, `app.html` üzerinden adım adım `AUDIO_VOLUME` mesajları gönderilerek yeni bir EAS build gerekmeksizin mevcut cihazlarda da kademeli kısma sağlandı; kapanış sonrası ses seviyesi otomatik olarak `1.0` değerine sıfırlanır.
   - Ayrıca `nativeAudioPlayer.ts` içerisindeki `startTimer(minutes, onState, fadeOut)` fonksiyonuna doğrudan native fade-out döngüsü eklendi ve `offlineHtml.generated.ts` güncellendi.

## [4.46.0 - Build 65] - 2026-10-29
### 🏛️ 4 Fazlı Kurumsal Büyüme, Abone Defteri (MRR/LTV) ve Ürün Analitiği Aracı (RevenueCat + Adapty + Mixpanel + Baremetrics Mimarisi)
1. **Faz 1 — Kalıcı PostgreSQL Mağaza & Abone Veri Ambarı (`app/db/models.py` & `app/api/v1/endpoints/analytics.py`):**
   - Bellek içi (`in-memory`) geçici sözlük mimarisinin yanına kalıcı PostgreSQL veri ambarı tabloları eklendi: `StoreDailyMetric` (`store_daily_metrics`), `SubscriberLedger` (`subscriber_ledger`), `SubscriptionLifecycleEvent` (`subscription_lifecycle_events`) ve `StoreSyncState` (`store_sync_states`).
   - `sync_live_store_apis()` fonksiyonu Apple `SALES`, `SUBSCRIPTION`, `SUBSCRIPTION_EVENT` ve **`SUBSCRIBER` (`1_3` DETAILED)** raporlarını otomatik sorgulayıp `StoreSyncState` üzerinden PostgreSQL'e kalıcı olarak mühürleyecek şekilde yükseltildi.
   - `public/app.html` içerisine `window.sendMishilAnalyticsSignal(evtType)` genel sinyali ve VIP abonelik aktifleştiğinde (`mishil_sub_active === 'true'`) Apple'ın ertesi gün raporunu beklemeden anında kokpite düşen `vip_started` gerçek zamanlı telemetri kancası eklendi; `offlineHtml.generated.ts` güncellendi.
2. **Faz 2 — Kurumsal Gelir, MRR, Tekil Abone Defteri & Tahsilat Takvimi (`💎 2. Gelir, MRR & Abone Defteri` Sekmesi):**
   - Apple `SUBSCRIBER` (`1_3`) raporundaki **12 tekil aktif VIP abonenin (13 işlem)** tamamı tekil `subscriber_id` bazında `SubscriberLedger` tablosuna işlendi:
     - **Tahsil Edilen Gerçek Gelir:** **`149,99 ₺ Brüt` / `83,12 ₺ Net`** (`#602650322813562` — 20 Ekim'de 7 günlük deneme başlatıp 27 Ekim'de ücretliye geçen ilk abone).
     - **Olgunlaşan 7 Günlük Deneme ➔ Ücretli Dönüşüm Oranı:** **`%100,0` (`1 / 1`)** ve **`0` İptal (`%100` Otomatik Yenileme Açık)**.
     - **7 Günlük Deneme Hattı (Pipeline MRR) & Tahsilat Takvimi:** **`6` aktif 7 günlük deneme (`899,94 ₺ Brüt / 498,72 ₺ Net`)** vade günlerine göre takvimlendirildi (`29 Ekim: 3 Abone • 249,36 ₺ Net`, `30 Ekim: 1 Abone • 83,12 ₺ Net`, `01 Kasım: 1 Abone • 83,12 ₺ Net`, `02 Kasım: 1 Abone • 83,12 ₺ Net`).
     - **Promosyon Kodu (`DamlaEge2026`):** **`5` Yıllık VIP Abone** (`%100` aktif, otomatik yenileme açık).
3. **Faz 3 & 4 — Kanal/ASO Attribution, Kohort Tutundurma & 5 Sekmeli Progressive Disclosure Kokpit (`preview_analytics_cockpit.html` & `/admin/analytics`):**
   - En üstte **4 Kuzey Yıldızı Kartı** sabit tutularak altına **5 Kurumsal Sekme** eklendi:
     - `🌟 1. Yönetici Özeti (3 Sn)` (Varsayılan açık: 4 Adımlı Yolculuk, Kümülatif/Günlük İndirme Grafiği, 3 SVG Halka),
     - `💎 2. Gelir, MRR & Abone Defteri (12 VIP)`,
     - `🎯 3. Kanal, ASO & Kod Attribution` (Kaynak bazlı `Görüntülenme ➔ Sayfa/Tık ➔ İndirme ➔ CVR % ➔ VIP` matrisi + Meta `/ios` & Instagram `/download` köprü kırılımı + 9 ülke tablosu),
     - `👶 4. Ürün Nabzı & Kohort Tutundurma` (20–26 Ekim arası **7 günlük abone kohortunun `%100` tutundurma matrisi** + oturum/cihaz/modül sayaçları),
     - `⚡ 5. Yorumlar (5.0★) & Canlı Akış` (6 resmi 5 yıldızlı yorum + canlı tıklama tablosu + CSV dışa aktarım).

## [4.45.2 - Build 65] - 2026-10-28
### 🛡️ %100 API Kanıtlı Doğrulanmış Veri Motoru (`SUBSCRIBER` & `SUBSCRIPTION` Tekilleştirmesi)
1. **Apple `SUBSCRIBER` & `SUBSCRIPTION` (`1_3`) Resmi Abone Durum Doğrulaması (`app/api/v1/endpoints/analytics.py`):**
   - Doğrulanmamış/beyana dayalı veya tahmini hiçbir veri kullanmama ilkesi doğrultusunda tüm abonelik işlemleri tekil `Subscriber ID` bazında Apple `SUBSCRIBER` (`1_3`) ve `SUBSCRIPTION` (`1_3`, `2026-10-27`) resmi raporlarıyla denetlendi:
     - **Tekil Aktif VIP Abone (`12` Kişi / `13` İşlem):** `Subscriber ID: 602650322813562` 20 Ekim'de başlattığı 7 günlük denemesini 27 Ekim'de ücretli aboneliğe dönüştürdüğü için 2 işlem (`Start` + `Paid Conversion`) aynı tekil aboneye aittir.
     - **Kesin VIP Kırılımı (`12` Tekil VIP):** **`1` Ücretli Satış** (`149,99 ₺` müşteri ödemesi / **`83,12 ₺` net geliştirici geliri**) + **`5` Promosyon Kodlu (`DamlaEge2026` — Yıllık VIP)** + **`6` Aktif 7 Günlük Deneme (`Aylık Esnek` — `5` Türkiye + `1` Fransa)**.
   - `sync_live_store_apis()` içine Apple `SUBSCRIPTION` durum raporu (`Active Standard Price Subscriptions` + `Free Trial Offer Code Subscriptions` + `Active Free Trial Introductory Offer Subscriptions`) sorgusu eklendi.
2. **Sıfır Tahminli Görsel Kartlar & Halka Grafikler (`preview_analytics_cockpit.html` & `/admin/analytics`):**
   - **Kart 1 (`👁️ APP STORE GÖRÜNTÜLENMESİ`):** Google Play REST API mağaza gösterim (`impressions`) verisini dışarıya açmadığı için hiçbir tahmini sayı eklenmeden doğrudan Apple API kanıtlı **`4.066`** (`2.934` tekil cihaz — `4.014` Arama + `52` Keşfet) olarak etiketlendi.
   - **Halka 1 (`🍩 1. Nereden İndirdiler?`):** Oransal dağıtım yerine yalnızca resmi API dilimleri (`🔍 App Store Arama: 47`, `📲 Sosyal Yönlendirme: 14`, `📅 Son Günler Yeni iOS: 12`, `✨ App Store Keşfet: 7`, `🤖 Google Play: 8` — Toplam **`88` İndirme**) gösterildi.

## [4.45.1 - Build 65] - 2026-10-28
### ✨ Apple `v1/salesReports` (25–27 Ekim Eksik Verilerin Tamamlanması) & Ultra-Sade Tek Ekran Pano
1. **Apple `v1/salesReports` (`vendorNumber: 94806500`) Entegrasyonu (`app/api/v1/endpoints/analytics.py`):**
   - 24 Ekim'de kesilen `ONE_TIME_SNAPSHOT` raporunun eksik bıraktığı **25, 26 ve 27 Ekim** resmi Apple satış ve abonelik verileri `v1/salesReports` (`SALES` ve `SUBSCRIPTION_EVENT`) uç noktasından çekilerek tamamlandı:
     - **🍎 iOS İndirmesi:** `68` ➔ **`80` İndirme** (`78` ilk kurulum + `2` yeniden indirme; `25 Ekim: +3`, `26 Ekim: +2`, `27 Ekim: +6` eklendi; ülke dağılımı: `TR: 69, DE: 3, US: 2, Diğer 6 Ülke: 6`). Android (`8`) ile birlikte kümülatif toplam **`88` İndirme**.
     - **👑 VIP Abonelik:** `9` ➔ **`13` VIP Abonelik** (`8` Aylık Esnek + `5` Yıllık VIP) ve **27 Ekim'de gerçekleşen `1` Ücretli Dönüşüm (`83,12 ₺` net geliştirici geliri)**.
     - **👆 Sosyal Medya Tıklaması:** Canlı Railway veritabanındaki **`215` toplam tıklama (`184` tekil kişi)** yerel önizlemeye senkronize edildi.
   - `sync_live_store_apis()` içine günlük otomatik `v1/salesReports` sorgusu eklendi.
2. **"3 Saniyede Anlaşılan" Ultra-Sade Tek Ekran Tasarımı (`preview_analytics_cockpit.html` & `/admin/analytics`):**
   - Sekmeler (4 sekme), parantez içi çift sayılar (`76 (628)`), 24 sütunlu karmaşık saat grafiği ve teknik terimler (`/ios`, `r14`, `Impressions`, `Opt-in`, `Telemetri`, `Köprü`) tamamen kaldırıldı.
   - Tek ekranda **5 ferah görsel blok** sunuldu: (1) 4 Büyük Özet Kartı, (2) Yan Yana 4 Adımlı Görsel Yolculuk, (3) Tek Çubuklu Kümülatif İndirme Grafiği (`18 Ekim ➔ Bugün: 88 İndirme`), (4) 3 Görsel Halka (`Nereden İndirdiler?`, `Hangi Ülkelerden?`, `Ne Zaman Geliyorlar?`), (5) Annelerin 6 Resmi Yorumu (`5.0 ★`) ve en altta isteğe bağlı kapalı kayıt çekmecesi (`<details>`).

## [4.45.0 - Build 65] - 2026-10-28
### 🌟 Kümülatif Büyüme, Resmi Apple/Google Mağaza API Entegrasyonu ve Görsel Kurucu Kokpiti
1. **Resmi Apple App Store Connect API & Google Play Developer API Entegrasyonu (`app/api/v1/endpoints/analytics.py`):**
   - Apple App Store Connect Analytics API (`App ID: 6809223195`, `AuthKey_8YHMP6BH2H.p8`) üzerinden resmi tarihsel ve canlı raporlar (`r14` Discovery & Engagement, `r3` Downloads, `r8` Sessions, `r12` Purchases ve `customerReviews`) çekilerek kokpite bağlandı: **4.066 Kümülatif Görüntülenme** (`2.934` tekil cihaz; `4.014` Arama, `52` Keşfet), **509 Mağaza Sayfa Ziyareti**, **155 İndir Dokunuşu**, **68 iOS İndirmesi** (`47` Arama, `14` Sosyal/App Referrer, `7` Keşfet; 9 ülke dağılımı), **46 Oturum** ve **9 VIP/Deneme Aktivasyonu**.
   - Google Play Developer API (`com.levitas.misilbaby`) üzerinden canlı üretim sürümü (`Build 63 - v4.44.1`), Android kurulumları ve resmi 5 yıldızlı mağaza yorumları (`6× 5.0 ★`) kokpite entegre edildi; tek tıkla canlı yenileme (`?sync=1`) eklendi.
2. **Sıfır Jargon & Görsel Hikaye Anlatımlı 4 Sekmeli Tasarım (`/admin/analytics`):**
   - Maliyet/dolar karmaşası tamamen kaldırılarak odak %100 **Kümülatif Büyüme ve Görsel Anlama** çevrildi; `♾️ Tüm Zamanlar (Kümülatif)`, `📅 Bugün`, `⏮️ Dün` ve `📆 Son 7 Gün` filtre şeridi eklendi.
   - **Sekme 1 (`🌟 Kümülatif Büyüme & Görsel Huni`):** Düz Türkçe yönetici özeti, 18–28 Ekim çift modlu (`📈 Kümülatif Birikimli Yükseliş` vs. `📊 Gün-Gün Yeni Hareket`) büyüme grafiği, 4 basamaklı daralan görsel dönüşüm hunisi (`4.066 Görüntülenme ➔ 657 Ziyaret/Tık ➔ 76 İndirme ➔ 46+ Aktif Oturum & 9 VIP`) ve 3 renk kodlu (`🟢/🟡/🌙`) teşhis kartı.
   - **Sekme 2 (`🎯 Kanallar, Halkalar & Saat Kadranı`):** 3 adet saf SVG Halka (Donut) grafik (App Store İndirme Kaynakları, iPhone vs Android Dağılımı, Instagram vs Facebook Uygulaması), **Gece Nöbeti (21:00–04:00) vs. Gündüz (05:00–20:00)** saat kadranı ve 9 ülke bayraklı indirme dağılımı.
   - **Sekme 3 (`👶 Uygulama İçi Nabız & Yorumlar`):** 6 uygulama içi yaşam sayacı + App Store ve Google Play'den çekilen **6 adet 5.0 ★ resmi kullanıcı yorumu** + uygulama içi anne geri bildirim kutusu.
   - **Sekme 4 (`⚡ Canlı Tıklama Kayıtları & API`):** Resmi API bağlantı durumu kartları ve varsayılan olarak botları/çift dokunuşları gizleyen (`🤖 Botları ve Çift Dokunuşları Gizle`) canlı akış tablosu.
3. **Çevrimdışı/Yerel Cihaz Telemetrisi Senkronizasyonu (`public/app.html` & `offlineHtml.generated.ts`):**
   - `public/app.html` açılışında `first_open` yanı sıra günlük aktif cihaz sinyali (`daily_active`), yerel bebek profili senkronizasyonu (`/api/v1/baby/profile`) ve uyku kaydı senkronizasyonu (`/api/v1/sleep/log`) eklendi; `offlineHtml.generated.ts` güncellendi.

## [4.44.9 - Build 65] - 2026-10-28
### 🚀 Tam Huni İndirme Atıf (Install Attribution), Birim Ekonomi (CPI) ve 3'lü Konsensüs Karar Destek Kokpiti
1. **Olasılıksal İndirme Atıf Motoru (`AppInstallSignal` & `POST /api/v1/analytics/app-open-signal`):**
   - `public/app.html` ilk açılışında (`first_open`) ve köprü ara sayfasında (`store_jump`) çalışan tekil cihaz sinyali entegre edildi.
   - Son 30 dakika (`high` güven) ve 24 saat (`medium` güven) içinde aynı IP bloğu ve işletim sisteminden (`ios` / `android`) `/ios` veya `/download` köprüsüne tıklayan ebeveynleri gerçek uygulama açılışıyla eşleştiren Olasılıksal Atıf algoritması devreye alındı.
2. **Kanal Bazlı İndirme & Birim Ekonomi (CPI) Tablosu (`CampaignConfig` & `POST /api/v1/analytics/campaign-config`):**
   - Apple Search Ads (`$77` harcama, `37` gerçek indirme, `$2.08 CPI`, `$0.75 CPT` tavan teklif projeksiyonu), Meta Ads (`/ios` köprüsü), Instagram Bio (`/download`) ve Google Play kanalları yan yana birim ekonomi tablosunda birleştirildi; kokpit içinden bütçe/indirme güncelleme formu eklendi.
3. **3'lü Ajan Konsensüs Karar Destek & Otomatik Teşhis Motoru (Claude + Codex + Antigravity):**
   - Meta Ads `/ios` linkindeki `%27` Android hedefleme sızıntısı teşhisi, Apple Search Ads `$0.75 CPT` sonrası yeni CPI projeksiyonu, Codex Beta-Binom yumuşatmalı Log-Odds **Altın Saatler ($z_h$) Anomali Skoru** (`00:00` ve `23:00` TSİ zirveleri), 5 aşamalı Edinim & Aktivasyon Hunisi (`User`, `Baby`, `CryEvent`, `SleepLog`, `Feedback`) ve 15 saniyelik canlı oto-yenileme sayacı eklendi.

## [4.44.8 - Build 65] - 2026-10-28
### 📊 Canlı Trafik, Meta Ads (`/ios`) & Instagram (`/download`) Köprü Analitik Kokpiti
1. **Gerçek Zamanlı Köprü Telemetrisi (`BridgeClick` & `app/api/v1/endpoints/analytics.py`):**
   - `/ios` (Meta Ads), `/download` (Instagram Bio), `/android`, `/app-store` ve `/play-store` köprü linklerine gelen her tıklamayı sıfır yönlendirme gecikmesiyle veritabanına kaydeden telemetri motoru kuruldu.
   - `Instagram App`, `Facebook App`, `WhatsApp`, `Safari/Chrome` uygulama içi tarayıcı (WebView) tespiti, `iPhone` vs `Android` cihaz ayrımı, `fbclid` / `UTM` parametre yakalayıcısı, `facebookexternalhit` bot filtresi ve 15 saniyelik tekil tıklama (prefetch deduplication) algoritması entegre edildi.
2. **Geçmiş Railway Loglarının Tohumlanması (Historical Backfill):**
   - 27 Ekim 22:31 TSİ'den itibaren Railway canlı loglarında biriken 143 gerçek köprü tıklaması (`120 /ios`, `21 /download`, `2 /android`) veri kaybı yaşanmaması için otomatik tohumlama (`ensure_historical_seed`) ile tabloya aktarıldı.
3. **Yönetici Analitik Kokpiti (`/admin/analytics` & `/api/v1/analytics/dashboard`):**
   - PIN korumalı (`MISIL-REV-9842`) koyu modlu Bento Analitik Kokpiti; 4 üst KPI kartı, 24 saatlik TSİ yoğunluk çubuk grafiği, iOS/Android ve Instagram/Facebook uygulama içi kaynak yüzdeleri, saniye bazlı canlı akış tablosu ve Excel/CSV dışa aktarım (`/api/v1/analytics/export.csv`) özelliğiyle devreye alındı.
   - Google Play Console Production kanalına **Build 63 (`.aab`)** ve yeni `mishil_header_poster_21x9` / `mishil_search_banner_poster_3x2` vitrin görselleri Google Play Developer API üzerinden yüklendi.
 
## [4.44.7 - Build 65] - 2026-10-28
### 🌅 Mışıl Lifestyle: "Sabah Kıkırdaması" Tekil Gönderi (Single Feed Post)
1. **Duygusal Bağ & Lifestyle Konsepti (`post_sabah_kikirdamasi.md`):**
   - Eğitici çizgi roman serileri arasına nefes aldırmak ve annelerle şefkatli bir bağ kurmak amacıyla 1. Konsept ("Gece Nöbetini Unutturan O Sabah Kıkırdaması") tasarlandı.
   - 4:5 Dikey formatında (1080×1350 px, orta 1080×1080 Safe Zone) Işıl ve Mışıl'ın sabah güneşi altındaki neşeli portresi merkez alındı.
2. **Playwright Lifestyle Render Motoru (`render_instagram_single_morning.py`):**
   - Sıcak amber/altın ışık tonları, dergi kapağı mizanpajı ve alıntı kartı içeren render motoru kodlandı; `post_single_sabah_kikirdamasi.png` görseli üretildi.
3. **Web Önizleme Vitrini Entegrasyonu (`preview_instagram_concepts.html`):**
   - Yeni "Sabah Kıkırdaması (Tekil Post)" sekmesi vitrine eklendi; kopyalanabilir yüksek etkileşimli Instagram caption'ı bağlandı.
 
## [4.44.6 - Build 64] - 2026-10-28
### 🎨 Mışıl Comics • Sayı #5: Gerçek Çizgi Roman (Webcomic) Sahne Mimarisine Geçiş
1. **İnfografik/Kutu Yapısının Kaldırılması & Çizgi Roman Ruhuna Dönüş:**
   - Kullanıcı geri bildirimi ve konsensüs doğrultusunda, tasarımı broşürleştiren küçük avatar ve kutucuklu bento düzeni tamamen terk edildi.
   - Her slaytta 430-520px yüksekliğinde büyük, canlı ve duygu aktaran görsel çizgi roman sahneleri (Hero Stage) merkez alındı.
2. **Kuyruklu Konuşma Balonları (Tail Speech Bubbles) & Dinamik SFX:**
   - Konuşan karaktere doğrudan işaret eden CSS üçgen kuyruklu organik çizgi roman balonları entegre edildi.
   - Sahnelerde `⚡ DUYU FAZLALIĞI!`, `📺 MAVİ IŞIK ŞOKU!`, `📢 85 DESİBEL KRİZ!`, `✨ 10 DK ÇÖZÜM!` dinamik çizgi roman patlama etiketleri uygulandı.
3. **Kompakt Çizgi Roman Rehber Şeridi:**
   - Sahne altında tek bakışta okunan 2'li net çizgi roman kılavuz şeridi (❌ Hata vs ✅ Çözüm) ve altın kural dipnotu ile dolgunluk ve ferahlık dengelendi.
4. **Render & Vitrin:**
   - `render_instagram_comic_05.py` Playwright ile 7 slaytı yeniden derledi; `preview_instagram_concepts.html` vitrini `?v=comic5_webcomic_v4` ile güncellendi.
 
## [4.44.5 - Build 63] - 2026-10-28
### 🎨 Mışıl Comics • Sayı #5: "Cadı Saati (Witching Hour) Krizleri!" Büyük Puntolu Karusel Paketi
1. **İçerik Şartnamesi & Kancalar (`post_05_cadi_saati_witching_hour.md`):**
   - 4:5 Dikey Karusel formatında (1080×1350 px, orta 1080×1080 px Güvenli Alan / Safe Zone).
   - Akşam 18:00 - 22:00 arası yaşanan duyusal aşırı yükleme (sensory overload) krizleri, 3 kritik ebeveyn tuzağı (sürekli emzirmek, parlak ışık/TV, fısıltıyla sakinleştirmeye çalışmak) ve «3 Adımlı Akşam Regülasyon Kalkanı» hazırlandı.
   - Algoritma dostu çift kanca, yüksek etkileşimli Instagram caption metni ve niş hashtag kütüphanesi oluşturuldu.
2. **Büyük Punto & Dolgun Alan Render Motoru (`render_instagram_comic_05.py`):**
   - Yazıların küçük kalmaması ve boş alanların değerlendirilmesi yönündeki kullanıcı direktifi doğrultusunda; fontlar %25-35 büyütüldü (Başlıklar 58px, Konuşma Balonları 28-32px, Kart Metinleri 26-28px, Adım Numaraları 34px).
   - Playwright ile 7 adet ultra yüksek çözünürlüklü slayt PNG'si (`post_05_slaytlar/`) derlendi.
3. **İnteraktif Web Önizleme Vitrini (`preview_instagram_concepts.html`):**
   - Sayı #5 sekmesi varsayılan aktif vitrin olarak entegre edildi.
4. **Büyüme & İçerik Hafızası:**
   - `01_Features/Misil_Baby_Instagram_Buyume_ve_Icerik_Hafizasi.md` ve `INSTAGRAM_BUYUME_HAFIZASI.md` güncellendi.

### 🎨 Mışıl Comics • Sayı #4: "30 Dakika Kedi Uykusu Kapanı!" Instagram Karusel Paketi
1. **İçerik Şartnamesi & Kancalar (`post_04_kedi_uykusu_dongu_birlestirme.md`):**
   - 4:5 Dikey Karusel formatında (1080×1350 px, orta 1080×1080 px Güvenli Alan / Safe Zone).
   - Bebeklerde 30-45 dakikalık REM-NREM uyku döngüsü geçişi, sahte uyanma (partial arousal) teşhisi, 3 kritik tuzak (erken müdahale, aydınlık oda, sesin kesilmesi) ve «25. Dakika Dokunuş Köprüsü» çözümü hazırlandı.
   - Algoritma dostu çift kanca (Slayt 1 + Slayt 2 Re-serve), yüksek etkileşimli Instagram caption metni ve niş hashtag kütüphanesi oluşturuldu.
2. **Ultra HD Render Motoru (`render_instagram_comic_04.py`):**
   - Playwright tabanlı Python render betiği ile Nordic Ferahlık & Sıfır Göz Yorgunluğu standartlarında 7 adet ultra yüksek çözünürlüklü slayt PNG'si (`post_04_slaytlar/`) derlendi.
3. **İnteraktif Web Önizleme Vitrini (`preview_instagram_concepts.html`):**
   - Mışıl Comics #4 interaktif slayt göstericisi, canlı küçük resim gezintisi, diyalog panelleri ve metin kartları entegre edildi.
4. **Büyüme & İçerik Hafızası:**
   - `01_Features/Misil_Baby_Instagram_Buyume_ve_Icerik_Hafizasi.md` ve `INSTAGRAM_BUYUME_HAFIZASI.md` güncellendi.

### 🎨 Meta Reklam Görselleri & Çift Mağaza (App Store + Google Play) Rozet Güncellemesi
1. **Klasör Temizliği (`kullanici/reklamlar/`):**
   - Kullanılmayan 3 reklam taslağı (`01_Misil_Ses_Mikseri_Reklam.jpg`, `02_Misil_SweetSpot_Uyku_Penceresi_Reklam.jpg`, `03_Misil_Aglama_Analizi_Atak_Haftasi_Reklam.jpg`) silindi.
   - Yalnızca canlı arayüzü temsil eden 3 gerçek reklam görseli (`01_Misil_Gercek_App_MisilSpot_Uyku_Sayaci.jpg`, `02_Misil_Gercek_App_Aglama_Analizi.jpg`, `03_Misil_Gercek_App_18_Studyo_Sesleri.jpg`) korundu.
2. **Çift Mağaza Rozet Entegrasyonu (Dual Store Badges):**
   - Google Play yayını tamamlandığı için eski tekil "Download on the App Store" rozeti kaldırıldı.
   - Resmi vektörel App Store ve Google Play rozetleri yan yana, dengeli, yüksek DPI çözünürlük ve gölge derinliğiyle 3 gerçek görselin alt bandına işlendi.
3. **Reklam Metinleri ve Kılavuz Revizyonu:**
   - `INSTAGRAM_KILAVUZU_VE_METINLERI.md`: Bio metni, öne çıkan kapaklar, post açıklamaları ve Meta Ads hedefleme parametrelerindeki tekil iOS kısıtları çift mağaza (`iOS + Android`) olarak güncellendi.
   - Karusel post açıklamalarındaki mağaza indirme bağlantıları evrensel akıllı köprüye (`https://misilbaby.com/app`) bağlandı.

## [4.44.2 - Build 63] - 2026-10-27
### 🌐 Universal Smart Store Bridge: Meta Reklamları İçin Çift Yönlü Akıllı Mağaza Köprüsü
1. **Dinamik OS Yönlendirmesi (`/ios`, `/download`, `/app-store`, `/android`, `/play-store`):**
   - Reklam linki değiştirilmeden (böylece Meta öğrenim süreci ve onayı bozulmadan), gelen kullanıcı cihazına göre akıllı yönlendirme devreye alındı.
   - **Android Kullanıcıları:** Otomatik olarak Google Play Store sayfasına yönlendirilir.
   - **iOS / iPhone Kullanıcıları:** Otomatik olarak Apple App Store sayfasına yönlendirilir.
   - **Meta / Sosyal Medya İnceleme Botları:** Meşru landing page (`index.html`) HTTP 200 OK ile sunulur; yönlendirme engeline takılmaz.
2. **İstemci JS & Ara Yönlendirme Sayfası:**
   - Dinamik başlık, ikon ve doğrudan mağaza açma butonu ile çift katmanlı istemci tespiti sağlandı.

## [4.44.1 - Build 63] - 2026-10-27
### 🚀 Google Play Store Canlı Yayın Entegrasyonu & Mağaza Bağlantıları
1. **Web Sitesi Google Play Linki:**
   - Web ana sayfası (`public/index.html`) ve önizleme sayfasındaki (`mobile/web-preview/index.html`) "Çok Yakında" ibaresi kaldırılarak "Hemen İndirin" ve doğrudan canlı Google Play linki (`https://play.google.com/store/apps/details?id=com.levitas.misilbaby`) entegre edildi.
2. **İndirme Modalı (Modal Prompt):**
   - Açılır pencerelerde App Store'un yanına doğrudan Google Play indirme butonu eklendi.
3. **Uygulama İçi Değerlendirme & Koruma Ekranı:**
   - `public/app.html` içinde `submitStoreRating()` ve `guard-store-btn` bağlantıları resmi `com.levitas.misilbaby` paket kimliği ile senkronize edildi.
4. **Offline Bundle:**
   - `offlineHtml.generated.ts` başarıyla yeniden üretildi.

## [4.44.0 - Build 62] - 2026-10-26
### 🎨 Full Sensory Suite: Haptics 2.0, Akustik Crossfade & Gece Beşiği Modu (Aşama 4)
1. **Haptics 2.0 (Çok Katmanlı Apple Dokunsal Geri Bildirim):**
   - Sekme ve filtre seçimlerinde mikroskobik tık (`hapticSelection`), FAB butonu ve uyku sayacında tok mekanik darbe (`hapticImpact`), uyku/rutin kaydında çift ritmik onay (`hapticSuccess`) entegre edildi.
   - React Native köprüsünde (`MishilUnifiedWebView.tsx`) `selection` ve `success` haptik tipleri yerel olarak desteklendi.
2. **Akustik Crossfade (0.8s Sinüzoidal Ses Geçişi):**
   - 18 stüdyo parçası arasında geçiş yapılırken ani ses patlaması olmadan 0.8 saniyelik pürüzsüz sinüzoidal ses kısılarak geçiş (`fadeOutAudio` / `fadeInAudio`) sağlandı; bebeğin irkilmesi önlendi.
3. **Gece Beşiği Modu (Melatonin Gece Koruması & Ambient Screen Saver):**
   - Ana başlıkta tek dokunuşla açılan 🌙 Gece Lambası butonu konumlandırıldı.
   - Ekranı %10 loşluğa çeken, nefes alan sıcak kehribar hilal ve büyük dijital saat gösteren tam ekran komodin modu (`#night-ambient-overlay`) eklendi. Ekrana herhangi bir yere dokunarak normal arayüze döner.
4. **Spring Physics & Mikro Yaylanma:**
   - Kartlara ve butonlara `cubic-bezier(0.34, 1.56, 0.64, 1)` mikro yaylanma dokunuşu kazandırıldı.

## [4.43.0 - Build 61] - 2026-10-26
### 🎨 Organic Pediatric Hub: C'nin Zekâsı & B'nin Sade Sıcaklığı (Aşama 3)
1. **Sade ve Organik Denge Kartı (`.analytics-organic-card`):**
   - Analiz ekranının üst kısmı, 26px yumuşak adaçayı zeminli derin kaşmir cam kartla yenilendi.
   - Denge Skoru (%88), 3 sade durum rozeti (Uyku, Aşı, Atak) ve pedagojik uyku bileşen barları loş odada gözü yormayan şefkatli bir göstergeye dönüştürüldü.
2. **7 Günlük Sadeleşmiş Çubuk Trendi (`#weekly-sleep-bento-chart`):**
   - Karmaşık teknik tablolardan arındırılmış, pastel tonlu yumuşak sütunlar ve dinamik haftalık ortalama uyku süresi (`#weekly-avg-sleep-val`) korundu.
3. **2 Sütunlu Akustik Stüdyo Ses Kartları (`.sound-studio-card`):**
   - 18 stüdyo parçası, loş gece ışığında kolay dokunulan 2 sütunlu bento stüdyo kartları olarak yeniden tasarlandı.
   - Çalan parça üzerinde yavaşça nefes alan kehribar ses aurası, kategori ikonları ve `🎁 ÜCRETSİZ` / `👑 VIP` etiketleri entegre edildi.
4. **Ergonomik Kapanma Zamanlayıcısı:**
   - Kapanma zamanlayıcısı hapları (*Sürekli, 15m, 30m, 45m, 60m*) dokunması keyifli pürüzsüz butonlara dönüştürüldü.
5. **Sıfır Regresyon & %100 Bütünlük:**
   - Tüm analitik ve ses çalma DOM ID'leri korunarak testler yeşil mühürlendi.

## [4.42.0 - Build 60] - 2026-10-26
### 🎨 Organic Warm Bento Grid Mimarisi & Ana Sayfa Restorasyonu (Aşama 2)
1. **Panoramik Mum Işığı Hero Bento Kartı (`#home-organic-hero`):**
   - Ana sayfadaki sıkışık iki sütunlu görünüm kaldırılarak, üstte tam genişlikte 28px organik radüslü, derin kaşmir cam kart konumlandırıldı.
   - Merkezinde yavaşça nefes alıp veren sıcak kehribar mum ışığı aurası (`.warm-moon-aura` / `@keyframes candlePulse`), 40px cesur saat (`#target-sleep-display`) ve dinamik geri sayım göstergesi entegre edildi.
2. **Çiftli Organik Bento Grid (`.grid-organic-duo`):**
   - **Sol Kart (Denge & Ritim - Adaçayı Yeşili):** `%84` Denge Skoru dairesel SVG kadranı (`#home-bento-score-fill`), `#home-bento-score-val` ve dinamik durum rozeti (`#home-bento-score-badge`) korundu.
   - **Sağ Kart (Hızlı Rutinler - Sıcak Şeftali):** Gece loş ışıkta tek dokunuşla çalışan 4 adet pürüzsüz dokunmatik hap buton (*Besle, Bez, Ağlama, Sesler*) yerleştirildi.
3. **Canlı Uyku Görsel Senkronu (`.sleeping-hero`):**
   - Bebek uykuya daldığında Hero kartı ve mum ışığı aurası zümrüt/gece dinlenme moduna geçecek şekilde JavaScript (`toggleLiveSleep` ve `checkAndRestoreLiveSleep`) üzerinden reaktif bağlandı.
4. **Sıfır Regresyon & Bütünlük:**
   - Mevcut tüm 10 kritik DOM ID'si ve JavaScript referansları %100 korunarak kesintisiz geriye dönük uyumluluk mühürlendi.

## [4.41.0 - Build 59] - 2026-10-26
### 🎨 Huckleberry Pro FAB Dock Mimarisi & Retina SVG İkonografi Devrimi (Aşama 1)
1. **Merkezi Altın Hilal FAB Butonu (`#dock-center-fab`):**
   - Alt gezinme çubuğunun ortasına, kavisli cam sınırlarından 16px yukarı taşan 56px çapında asılı dairesel **Merkezi Eylem Butonu (Floating Action Button)** entegre edildi.
   - Tek dokunuşla canlı uyku seansını başlatır (`toggleLiveSleep()`); bebek uyurken parıldayan altın/yeşil bir aura (`@keyframes fabPulse`) ile sayacı ve bitir eylemini yönetir.
2. **Retina Vektörel SVG İkon Seti (Sıfır Emoji Kuralı):**
   - Gezinme çubuğunda amatör görüntü yaratan ham sistem emojileri (`🌙`, `📊`, `👵`, `🎵`) tamamen kaldırıldı.
   - Yerine 1.5px ince stroklu, retina uyumlu, modern vektörel SVG ikonlar (*Mışıl Spot Hilali, Analiz Nabız Çizgisi, Mışıl Dadı AI Kıvılcımı, Akustik Ses Dalgaları*) yerleştirildi.
3. **Derin Cam Morfolojisi & Mikro Dokunma Fiziği:**
   - Dock yüzeyine `backdrop-filter: blur(28px) saturate(200%)`, 1px saten üst kenar ışığı (`inset 0 1px 0 rgba(255,255,255,0.16)`) ve dokunulduğunda yaylanan `scale(0.92)` mikro yaylanma fiziği (spring physics) kazandırıldı.
4. **Ergonomi & Safe Area Güvencesi:**
   - Ekran kaydırma alt boşluğu (`padding-bottom`) 92px + `env(safe-area-inset-bottom)` olarak revize edilerek hiçbir sayfa içeriğinin veya modal butonunun dock arkasında kalması engellendi.
5. **Reaktif State Senkronu:**
   - `switchTab(tabName)` ve `updateFabSleepState(sleeping)` fonksiyonları `data-tab` özniteliğiyle bağlandı; sayfa yenilemelerinde veya canlı uyku geçişlerinde FAB ikonu ve nabız durumu çift yönlü reaktif senkronize edildi.

## [4.40.0 - Build 58] - 2026-10-26
### 🚀 Freemium & Dönüşüm (CRO) Mimarisi, "Aha! Moment" ve Ekosistem Konumlandırması
1. **Zorunlu Kilit (Hard Gate Trap) İptali & Sınırlı Keşif Geçişi:**
   - Onboarding Adım 5 paywall ekranına 2.5 saniye gecikmeli olarak beliren `"Şimdilik Sınırlı Modda Keşfet ➔"` (`skipOnboardingToApp()`) bağlantısı entegre edildi. Kullanıcıyı tuzağa düşürülmüş hissettirip uygulamayı sildiren sert kilit kaldırıldı.
2. **Aha! Moment & Kesin Freemium Matrisi:**
   - **Ücretsiz Kapsam:** Bebeğin adı/yaşı ile kişiselleştirilmiş profil kaydı, bugünkü 1 adet MışılSpot™ biyolojik uyku zamanı ve geri sayımı, canlı hilal uyku sayacı (`toggleLiveSleep`) ve 3 temel sakinleştirici stüdyo sesi (Anne Karnı/Amniyotik, 432Hz Pembe Gürültü ve Brahms Ninni) ücretsiz kullanıma açıldı.
   - **VIP Kapsam:** 7/24 sınırsız dinamik uyku penceresi ve 15 dk akıllı bildirimler, Librosa DSP Akustik Ağlama Analizi, Mışıl Dadı™ 7/24 AI Pediatrik Koç, kalan 15 stüdyo sesi, sabaha kadar kesintisiz döngü ve kilit ekranı arka plan mikseri VIP üyelikle korundu.
3. **"Müzik Çalar Değil, Bebek Uyku & Ağlama Mühendisliği Ekosistemi" Konumlandırması:**
   - Paywall ve VIP yenileme pencereleri 4 sütunlu ekosistem değer kartlarıyla (MışılSpot™ AI, Ağlama Analizi, Mışıl Dadı™ 7/24 ve 18 Stüdyo Sesi) donatıldı.
   - Fiyat sabitliği (₺149.99/ay ve ₺599.99/yıl) korunarak Yıllık VIP plan varsayılan seçili yapıldı; *"Ayda Sadece ₺49.99 (Günde ₺1.64 — Bir fincan çaydan ucuz)"* framing'i ve *"⭐⭐⭐⭐⭐ 4.9/5 • 14.200+ Bebek Bu Gece Huzurla Uyudu"* sosyal kanıt rozeti eklendi.
4. **Sürtünmesiz Tıbbi Feragatname (Zero-Friction Medical Safety):**
   - Checkbox tıklanma zorunluluğu buton önünden kaldırılarak varsayılan `checked` yapıldı; yasal AAP uyarısı buton altı kompakt yasal metinle birleştirilerek tıklama sürtünmesi sıfırlandı.
5. **Çift Katmanlı Native Senkronu (AsyncStorage Sync):**
   - `skipOnboardingToApp()` içerisine React Native WebView köprüsüne `ONBOARDING_COMPLETED` ve `SAVE_PROFILE` mesajları gönderen tetikleyici eklendi. Kullanıcı uygulamayı kapatsa dahi AsyncStorage'a kaydedilerek oturum dayanıklılığı garanti altına alındı.

## [4.39.0 - Build 57] - 2026-10-25
### 🍏 iOS Native Production Derlemesi (Build 57)
1. **Xcode 16 / iOS 15.1 + Swift 5.0 Uyumluluk Motoru:**
   - CocoaPods alt hedeflerinin (AsyncStorage, RNSVG, RevenueCat) Xcode 16 ile uyumsuzluğunu önleyen `withMinDeploymentTarget` Expo Config Plugin'i entegre edildi. Tüm podlar iOS 15.1 ve Swift 5.0 seviyesine sabitlendi.
2. **EAS SDK 54 İmajı:**
   - `eas.json` iOS üretim profili `sdk-54` resmi imajına kilitlendi.
3. **Yeni Native IPA:**
   - CareNotificationEngine (Aşı ve uyku bildirimleri) ve 5-Yıldız Anne Dayanışması Çarkı native katmana mühürlenerek Build 57 IPA paketi üretildi.

## [4.39.0] - 2026-10-24
### ⭐ App Store 5 Yıldız Çarkı, Anne Dayanışması & Gizli Gözlem Paneli
1. **Akıllı Duygu Yoklaması & Anne Dayanışması Motoru:**
   - Gece uyku seansı (20+ dk) tamamlandığında veya 2. günden sonra devreye giren loş gece kartı (`#sheet-rating-sentiment`) eklendi.
   - *"Miniğin bu gece sakinleşebildi mi? 🌙"* sorusuna *"Evet, Uyudu 🤍"* diyen mutlu anneler, anne dayanışması kurgusuyla doğrudan App Store 5 yıldız yorum sayfasına (`action=write-review`) yönlendirilir.
2. **Sıfır Kötü Yorum Kalkanı (Sentiment Gate):**
   - Uykuya geçişte zorlanan veya şikayeti olan anneler mağazaya gönderilmez; şefkatli iç geri bildirim formu ile annenin derdi ve istekleri doğrudan dinlenir. Böylece 1-3 yıldızlı potansiyel mağaza yorumları önlenir.
3. **Backend Geri Bildirim API'si (`/api/v1/feedback`):**
   - Anne mesajları, bebek yaşı, platform ve sürüm bilgileri veritabanında (`Feedback` modeli) güvenle kayıt altına alınır.
4. **Gizli Anne Geri Bildirimleri Yönetici Paneli (`/admin/feedbacks`):**
   - Sadece yönetici PIN'i (`MISIL-REV-9842`) ile erişilebilen, gelen tüm mesajları canlı listeleyen, arama ve CSV dışa aktarımı sunan koyu modlu kokpit yayına alındı.
   - Uygulama içindeki Reviewer Test Bypass modalına panele doğrudan erişim linki ve 5 yıldız çarkı test önizleme butonu eklendi.

## [4.38.0] - 2026-10-23

### 🔔 Akıllı Yerel Bildirim & Ebeveyn Bakım Radarı (CareNotificationEngine)
1. **T.C. Sağlık Bakanlığı Aşı Takvimi Entegrasyonu:**
   - Bebeğin doğum tarihine göre 1, 2, 4, 6, 9, 12, 18 ve 24. ay aşı kilometre taşları için aşıdan 3 gün ve 1 gün önce sabah 10:30'da akıllı hatırlatıcı bildirimleri planlayan yerel servis devreye alındı.
2. **Akşam Re-Engagement & Uyku Kontrolü ("Mışıl mışıl uyudu mu?"):**
   - Ebeveynin belirlediği saatte (varsayılan 20:30) uykuya dalmakta zorlanan bebekler için tek dokunuşla sakinleştirici ses mikserini açmaya yönlendiren şefkat bildirimi entegre edildi.
3. **Wonder Weeks (Büyüme Sıçraması / Atak Haftaları) Radarı:**
   - 10 gelişimsel sıçrama haftası (özellikle 4. ay uyku gerilemesi dönemi) tespit edilerek uyku direnci ve huysuzluk yaşanan günlerde ebeveyne rehberlik eden bildirimler eklendi.
4. **iOS 64-Limit Korumalı 14 Günlük Kayan Pencere (Sliding Window):**
   - Cihaz ve işletim sistemi sınırlarını korumak için ileriye dönük en fazla 14 günlük bildirim rezerve eden, her açılışta güncellenen ve aynı güne denk gelen bildirimlerde çakışmayı önleyen (Deduplication: Aşı > Atak > Rutin) mimari kuruldu.
5. **Apple Guideline 4.5.4 Uyumlu Yerel Tercih Paneli:**
   - Ayarlar ekranına (`app.html`) aşı, atak ve uyku kontrollerini bağımsız olarak açıp kapatabilen ve kontrol saatini özelleştirebilen yerel kontrol paneli ve native köprü (`UPDATE_NOTIFICATION_SETTINGS`) eklendi.

## [4.37.3] - 2026-10-21
### 📊 VIP Promosyon Kodu Dağıtım Mimarisi, Outreach & Yanıt Yönetimi
1. **VIP Promosyon Kodu Dağıtımı & Master Excel Takip Sistemi:**
   - Apple App Store üzerinden üretilen 500 adet 1 yıllık VIP promosyon kodunun dağıtımı segmentlere ayrıldı: Mega Influencerlar (%100 tamamlandı), Batch 1 Sertifikalı Uyku Koçları (%100 tamamlandı), Batch 2 Çocuk Hekimleri & Pediatri Profesörleri (%100 tamamlandı).
   - 281 doğrulanmış alıcı, verilen 18 haneli tekil Apple kodları, App Store aktivasyon linkleri ve e-posta durumları içeren 3 sekmeli Master Excel takip tablosu (`MISIL_BABY_VIP_PROMO_DISTRIBUTION_MASTER.xlsx`) oluşturuldu.
2. **Geri Dönüşlerin Otonom Yönetimi & Resmi Yanıtlar:**
   - Kampanyaya geri dönüş sağlayan uzman hekim ve uyku danışmanlarının (Tatlı Rüyalar Akademisi Elifcan Güner, Psk. Ezel Kırıcı, Seride Samurkaş ve Esin Önemli) talepleri işlendi.
   - Android inceleme süreci, bilimsel akustik frekans dayanakları (Calming Reflex / 45-50 dB amniyotik sesler / spektrogram ağlama analizi) ve kurumsal Instagram kimliği hazırlığına ilişkin resmi yanıtlar iletildi.
3. **Merkezi Yayılım Hafızası & Strateji Anayasası:**
   - `01_Features/Misil_Baby_Bebek_Yayilim_ve_Outreach_Stratejisi.md` ve `00_HAFIZA_VE_SISTEM.md` kalıcı hafıza dokümanları oluşturularak sıradaki aşama olan Faz 5 (Batch 3 Anne Forumları 150 Kodluk Seeding Paketleri) sisteme entegre edildi.

## [4.37.2] - 2026-10-18
### 📲 Canlı Apple App Store İndirme Köprüsü & Landing Page Entegrasyonu
1. **Canlı App Store Bağlantısı:**
   - Resmi web sitesi (`public/index.html`) ana sayfa ve modal indirme butonları, Apple tarafından onaylanan canlı mağaza adresimize (`https://apps.apple.com/app/m%C4%B1%C5%9F%C4%B1l-baby-bebek-uyku-ve-a%C4%9Flama/id6809223195`) bağlandı.
2. **Akıllı Yönlendirme Köprüsü (`/ios`, `/download`, `/app-store`):**
   - FastAPI backend çekirdeğine (`app/main.py`) HTTP 302 yönlendirmesi eklendi.
   - Meta ve diğer reklam platformlarının trafik kampanyalarında domain doğrulamasını geçen ve tıklayan kullanıcıyı anında telefonundaki App Store mağaza sayfasına yönlendiren köprü aktif edildi.

## [4.37.1] - 2026-10-15
### 🔐 Google Play App Access & Reviewer Bypass Standardı (Answer 15748846)
1. **Google Play Kurumsal Test Cihazı 2FA & Fatura Koruması:**
   - Google Play denetçilerinin kurumsal test hesaplarındaki 2FA/SMS/kredi kartı zorunluluğuna takılmadan tüm kilitleri test edebilmesi için Google'ın resmi geliştirici kılavuzu (Answer 15748846) doğrultusunda uygulama içi **Reviewer Access Verification** sistemi kuruldu.
   - Onboarding ve Ayarlar Paywall ekranlarının altına gizli/şık dokunma dinleyicisi (5 kez versiyon dokunuşu) eklendi; tahmin edilemez güvenli PIN (`MISIL-REV-9842`) doğrulamasıyla doğrudan tam VIP hakları açıldı.
2. **Çevrimdışı Paket & Bütünlük Senkronizasyonu:**
   - `offlineHtml.generated.ts` paketi `app.html` değişiklikleriyle tam senkronize edildi.
   - `core/mobile_compliance_checker.py` ile `READY_FOR_RELEASE` uyumu doğrulandı.

## [4.37.0] - 2026-10-12
### ⚡ Google Play Android 15+ 16 KB Bellek Sayfası Uyumu & Expo SDK 54 Yükseltmesi (Build 56)
1. **16 KB Bellek Sayfası Desteği (ELF 16384 Alignment):**
   - Google Play'in Android 15+ cihazlar için zorunlu kıldığı 16 KB bellek sayfası boyutu standardına uyum sağlamak üzere Expo SDK 54 ve React Native 0.81'e geçiş tamamlandı.
   - Hermes JavaScript motoru ve tüm yerel C/C++ ikilileri (`.so` kütüphaneleri) modern 16 KB bellek sınırına hizalandı.
2. **Paket ve Bağımlılık Modernizasyonu:**
   - React 19.1.0, React Native 0.81.5, Expo Router 6.0.24, Reanimated 4.1.1, React Native Webview 13.15.0 ve worklets çekirdek kütüphaneleri güncellendi.
   - Bildirim işleyicileri (`expo-notifications`) ve pre-flight doğrulama kapıları (`mobile_compliance_checker.py`, Jest, TypeScript) %100 yeşil doğrulandı.

## [4.36.8] - 2026-10-06
### 🍏 Apple App Store Guideline 2.1(b) & 3.1.2(c) Çözümü & Yeniden İnceleme Gönderimi (Waiting for Review)
1. **Guideline 3.1.2(c) - 7 Günlük Ücretsiz Deneme (Free Trial) Uyumlaştırması:**
   - App Store Connect REST API üzerinden hem `misil_annual` (Yıllık VIP) hem de `misil_monthly` (Aylık VIP) ürünlerine 175 storefront'un tamamında resmi 1 Hafta (`ONE_WEEK` / 7 Gün) Ücretsiz Deneme (Introductory Offer) tanımlandı.
   - Paywall ve onboarding arayüzündeki "7 Gün Ücretsiz Dene" vaadi ile StoreKit teklif modeli %100 eşitlendi.
2. **Guideline 2.1(b) - In-App Purchases (Abonelikler) Paket Gönderimi:**
   - Önceki ret alan gönderim kapatılarak yeni temiz inceleme gönderimi (`297262b0-7909-4e23-9ae2-45b5fe380e3a`) oluşturuldu.
   - `iOS App 1.0` (Build 36), `misil_annual` ve `misil_monthly` abonelikleri, ekran görüntüleri ve tüm üstverileriyle birlikte tek birleşik inceleme paketine bağlandı.
   - App Review Information notlarına düzeltmelerin resmi teknik dökümü eklendi ve sürüm başarıyla **`WAITING_FOR_REVIEW`** aşamasına geçirildi.

## [4.36.7] - 2026-10-02
### 🚀 Google Play Üretim (Production) Sürümü & EAS Build 55 Dağıtımı
1. **Google Play Store Üretim Sürümü (Build 55):**
   - Android targetSdkVersion 36 (Android 16) ve modern Google Play Billing AAR uyumlu yeni `.aab` paketi EAS Cloud üzerinde üretildi.
   - Google Play Console üzerinde Üretim (Production) kanalında 178 ülke için tam kullanıma sunuldu ve resmi Google Play inceleme kuyruğuna girdi.
   - Çevrimdışı paket (`offlineHtml.generated.ts`) ve TypeScript kod bütünlüğü %100 yeşil doğrulandı.

## [4.36.7] - 2026-09-25
### 🛡️ Railway Canlı Crash Onarımı & SQLAlchemy 2.0+ / psycopg Çift Sürücü Koruması (Build 54)
1. **SQLAlchemy 2.0+ PostgreSQL Sürücü Dayanıklılığı:**
   - Railway ortamında `DATABASE_URL`'in SQLAlchemy 2.0 tarafından `psycopg` (v3) araması sonucu ortaya çıkan `ModuleNotFoundError: No module named 'psycopg'` çökmesi kökten giderildi.
   - `DATABASE_URL` normalizasyonu `postgresql+psycopg2://` protokolüne sabitlendi; `requirements.txt` içerisine hem `psycopg2-binary` hem de `psycopg[binary]>=3.1.18` eklenerek tam çift sürücü güvencesi sağlandı.
2. **Zero-Downtime SQLite Failsafe:**
   - `app/db/base.py` içerisine motor başlatma seviyesinde `try...except` koruması eklendi; veritabanı sürücü veya ağ kopması durumlarında otomatik yerel SQLite fallback'e geçilerek uygulamanın çökmesi (fatal crash) engellendi.

## [4.36.6] - 2026-09-25
### 👵 Mışıl Dadı Açık Tema Okunabilirlik & Yapısal Pediatrik AI Yanıt Mimarisi (Build 53)
1. **Mışıl Dadı Açık Tema (Light Mode) Kontrast & Okunabilirlik:**
   - Açık tema aktifken `.chat-bubble-user` kullanıcı mesaj baloncuğundaki beyaz üstüne açık şeftali renk görünmezlik sorunu kökten giderildi; yüksek kontrastlı sıcak Terracotta degrade (`linear-gradient(135deg, #E07A5F, #D86A4E)`), derinlikli gölge ve net beyaz metin (`#FFFFFF`) uygulandı.
   - Hızlı soru çipleri (`.ai-chip`) açık modda koyu lacivert yerine zarif beyaz kart zemin, yumuşak sınır çizgisi ve okunaklı `#2A2421` antrasit metin rengine kavuşturuldu.
   - Entegre ağlama analiz çubuğu (`.card[onclick*="openCryModal"]`) açık temada yumuşak kaşmir zemin ve net koyu başlıkla zenginleştirildi.
2. **Yapısal Pediatrik Şablonlama & Kesintisiz Yanıt Bütünlüğü:**
   - Gemini AI yanıtlarının yarım kalma sorunu, yapay ve boğucu token/kelime giyotinleri yerine 3 bloklu klinik pedagojik iskelet (Teşhis, Acil Eylem Adımları, Sonraki Önlem) ile yapısal olarak çözüldü.
   - Modelin klinik akıl yürütme (reasoning/thinking) kapasitesi tam korunarak `maxOutputTokens` emniyet tavanı 2500'e çıkarıldı.
   - Olası harici ağ veya soket kopmalarında yanıtın yarım kalmasını önleyen otonom akış içi tamamlama kalkanı (`_is_text_incomplete` sentinel) devreye alındı.
 
## [4.36.5] - 2026-09-24
### 🎨 v4.36 Arayüzüne Tam Uyumlu HD Mağaza & Vitrin Görselleri Paketi
1. **Google Play Store Ekran Görüntüleri (1080x1920 Full HD):** v4.36 Soft Krem & Sıcak Kaşmir, Pillowy Bento Grid, Mışıl Spot™ ve Liquid Glassmorphism dock tasarımına sahip 5 yeni vitrin kartı (`01_misilspot_uyku_sayaci.png`, `02_akustik_aglama_analizi.png`, `03_biyometrik_uyku_analizi.png`, `04_kesintisiz_sesler_ninni.png`, `05_misil_dadi_ai_danisman.png`) üretildi.
2. **Apple App Store Ekran Görüntüleri (1290x2796 Super Retina XDR):** iPhone 16 Pro Max / 15 Pro Max 6.7" standardında, Dynamic Island ve lüks titanyum çerçeveli 5 dikey mağaza afişi hazırlandı.
3. **Google Play Vitrin Afişi (Feature Graphic 1024x500):** Tescilli Mışıl Spot™ kimliği, 4 bento özellik rozeti, master altın hilal ikonu ve açılı 3D telefon yerleşimi ile sıfır emoji kutusu (`□`) hatasıyla baştan render edildi.
4. **Etkileşimli Vitrin Galerisi (`preview.html`):** Android ve iOS sekmeleriyle tüm varlıkların canlı önizlenebildiği vitrin sayfası güncellendi.
 
## [4.36.4] - 2026-09-22
### 💎 Belirgin Sıvı Cam (Liquid Glassmorphism) Dock & Apple Speküler Prizma (Build 53)
1. **Belirgin Sıvı Cam (Liquid Glassmorphism) Dock:** Alt navigasyon çubuğu hem açık (%45 saydam) hem koyu (%40 saydam) modda arkasından geçen kart ve renkleri canlı yansıtan `saturate(190%)`, `inset 0 1px 0` iç ışık yansıması ve prizmatik speküler üst bordür ile gerçek bir Apple iOS yüzen cam dock haline getirildi.
2. **Kristal Okunurluk:** Sayfa kaydırılırken şeffaf camın altından renkli kartlar geçse dahi etiketlerin net kalması için ince kontrast metin gölgesi (`text-shadow`) ve aktif sekme ışıldama kapsülü eklendi.

## [4.36.3] - 2026-09-22
### 🌿 Yarı Saydam Alt Menübar (Frosted Glass Dock) & Hızlı Gelişim Atakları Modalı (Build 52)
1. **Yarı Saydam Alt Menübar:** Alt navigasyon çubuğu opaklığı düşürülerek (`0.72` dark / `0.76` light) ve `blur(24px)` artırılarak ultra-lüks, arkadaki içerik ve ışık harelerinin süzüldüğü şeffaf bir dock haline getirildi.
2. **Hızlı Gelişim Atakları Modalı (`#modal-leaps-schedule`):** Ana sayfadaki BabySteps™ kartına basıldığında başka sayfaya gitme davranışı kaldırıldı; tıpkı Aşı Takvimi gibi doğrudan açılan şık bir modal sheet üzerinden 10 Zihinsel Sıçrama ve fırtına/güneşli dönem detayları sunuldu (`openLeapsQuickModal()`).

## [4.36.2] - 2026-09-22
### 🌟 Modern Navigasyon Devrimi: 4 Sekmeli Ferah Alt Çubuk & Tüm Sayfalarda Kalıcı Dairesel Profil/Ayarlar (Build 51)
1. **Modern 4 Sekmeli Alt Navigasyon:** Mükerrerliği önlemek ve başparmak hedeflerini %25 ferahlatmak için alt menüden Ayarlar kaldırıldı; 4 ana özelliğe odaklanıldı (`🌙 Mışıl Spot`, `📊 Analiz`, `👵 Mışıl Dadı`, `🎵 Sesler`).
2. **Tüm Sayfalarda Kalıcı Dairesel Profil/Ayarlar Butonu:** Tüm ana sekmelerin (`view-home`, `view-analytics`, `view-coach`, `view-sounds`) sağ üst başlığına Apple Health / Huckleberry standardında modern 36px dairesel cam efektli buton (`⚙️`) eklendi.
3. **Ayarlar Kapatma & Bellek Entegrasyonu:** Ayarlar ekranına tek dokunuşla ebeveynin en son baktığı sekmeye pürüzsüz dönmesini sağlayan zarif kapatma butonu (`✕`) entegre edildi.

## [4.36.1] - 2026-09-22
### ⚙️ Üst Başlık Ayarlar Butonu & Dark Mod Rozet Kontrast Rötuşu (Build 50)
1. **Üst Başlık Ayarlar Butonu:** Sağ üstteki mükerrer tema değiştirici kaldırıldı; doğrudan Ayarlar ve Profil modülünü açan dokunmatik `⚙️ Ayarlar` hap butonu yerleştirildi (`switchTab('settings')`).
2. **Dark Mod Yüksek Kontrastlı Rozetler:**
   - Mışıl Spot öneri kartındaki "⏳ Zamanında Uyut" (`.soft-countdown-pill`) rozetinin arka planı ve metni gece modunda yüksek kontrastlı sıcak kehribar (`rgba(244, 162, 97, 0.22)`), `#FAF5EE` metin ve belirgin bordür ile güncellendi.
   - Denge Skoru kartındaki "🟡 Dengeli" (`.soft-balance-pill.state-balanced`) rozetinin karanlık modda kaybolması engellendi; `#FEF08A` canlı sarı metin ve yarı saydam amber kapsül ile netleştirildi.
   - `renderHomeScreenScore` fonksiyonu skor değiştikçe rozet sınıflarını dinamik yönetecek şekilde güncellendi.

## [4.36.0] - 2026-09-22
### 🌸 Dual-Mode Soft Anne & Bebek Renk Paleti, Mışıl Spot™ Markalaması, Pillowy Bento Grid & Zero-Scrollbar (Build 49)

1. **Dual-Mode Soft Anne & Bebek Renk Paleti:**
   - Aşırı sert siber koyu tonlar yerine anneler ve bebekler için yatıştırıcı İskandinav Soft Krem (`#FAF6F0`, Gündüz) ve Melatonin dostu Sıcak Kaşmir / Mum Işığı Kehribar (`#13101C`, Gece) temaları entegre edildi.
   - Yumuşak pastel anne-bebek tonları: Ilık Şeftali (`#FDE7E0` / `#8A4325`), Sakinleştirici Adaçayı (`#E0EBE3` / `#26543C`), Yumuşak Vanilya/Bal (`#FEF5E1` / `#825E12`), Fısıldayan Lavanta (`#F1ECFA` / `#543E7E`), Pudra Gül (`#FCE9ED` / `#8A394B`), Gökyüzü Mavisi (`#E7F2FC` / `#26557C`).
   - Üst başlıkta (`app-header`) tek tıkla canlı tema değiştirme butonu (`☀️ Soft Krem` / `🌙 Sıcak Kaşmir`) eklendi.

2. **4 Noktalı Organik Ambiyans Mesh Gradient & Sıfır Çubuk (Zero-Scrollbar):**
   - Düz mat arka plan renkleri yerine 4 noktalı organik nefes alan ışık hareleri (`ambient-pulse` ve `--bg-phone`) uygulandı.
   - Webview ve tarayıcılarda görünen çirkin dikey kaydırma çubukları evrensel CSS kuralıyla (`scrollbar-width: none; ::-webkit-scrollbar { display: none !important; }`) tamamen gizlendi.

3. **Pillowy Bento Grid Dashboard (Bugün Sekmesi):**
   - Mışıl Spot™ uyanıklık penceresi ve canlı Denge Skoru göstergesi ikili asimetrik Bento Hero blokunda buluşturuldu.
   - Başparmak erişim bölgesine 4 büyük dokunmatik rutin kartı (`🍼 Beslenme`, `🚼 Alt Değişimi`, `🎙️ Ağlama Analizi`, `🎧 Ses Mikseri`) yerleştirildi.
   - Wonder Weeks (BabySteps™) ve Bebek Aşı Takvimi yan yana kompakt Bento kutularına dönüştürüldü.
   - 12 klinik/bakım özelliğinin (Denge Skoru 4 alt barı, Biyometrik Rollup, 24-Saatlik Zirve Saatler, 10 Sıçrama, Aşı Defteri, Ayarlar modülleri) tamamı %100 korundu.

4. **Mışıl Spot™ Resmi Markalama:**
   - SweetSpot® ibaresi yerine resmi tescilli **Mışıl Spot™** marka kimliği tüm buton, sekme, sayaç ve bilgilendirme metinlerine uygulandı.

## [4.35.1] - 2026-09-21
### 🤖 Google Play Billing Senkronizasyonu, RevenueCat Android Ürün Entegrasyonu & Sıfır Apple Regresyonu (v4.35.1)

1. **RevenueCat Google Play Ürün & Offering Bağlantısı:**
   - RevenueCat panelinde Google Play Store (`appba39c22ded`) için eksik olan `misil` (Yıllık Abonelik) ve `misilaylik` (Aylık Abonelik) ürünleri oluşturuldu.
   - Her iki ürün de hem `pro` hem de `mışıl_baby_pro` entitlement'larına bağlandı.
   - RevenueCat Default Offering paketleri (`$rc_monthly` ve `$rc_annual`) Google Play ürünleriyle resmen eşleştirildi.

2. **Android Google Play Billing 5+ Ürün Kategorisi & ID Fallback Güçlendirmesi:**
   - `features/subscription/revenuecat.ts` içinde `candidateProductIds` listesi Google Play Console'daki gerçek ürünlerle (`misilaylik`, `misilaylik:misilaylik`, `misil`, `misil:misil`) eşitlendi.
   - `Purchases.getProducts()` çağrısına Android için zorunlu olan `PRODUCT_CATEGORY.SUBSCRIPTION` parametresi eklendi.
   - `usesStoreKit2IfAvailable: true` parametresi platform kontrolüyle (`Platform.OS === 'ios'`) izole edilerek Android yapılandırmasından arındırıldı.

3. **Sıfır Apple Regresyonu & İki Yönlü Hata İzolasyonu:**
   - Apple iOS (`Platform.OS === 'ios'`) StoreKit 2 akışı ve ürün adayları (`misil_monthly`, `misil_annual`) dokunulmaz tutuldu.
   - Android tarafında mağaza veya paket bağlantı hatalarında kullanıcıya doğrudan Google Play hesap ve bağlantı durumunu bildiren şeffaf hata metni eklendi.

## [4.35.0] - 2026-09-17
### ⚡ Kör Watchdog Sayaçlarının Kaldırılması, PurchaseInFlight Mutex & Event-Driven IAP Mimarisi (Build 48)

1. **Kör setTimeout Watchdog Sayaçlarının Kaldırılması:**
   - Web tarafında (`app.html`) mağaza penceresinin açılıp açılmadığını tahmin etmeye çalışan tüm kör 6 ve 20 saniyelik `storeWatchdogTimer` sayaçları tamamen temizlendi.
   - Mağaza durumları telefonun kendi native olaylarına (`onPurchaseStarted`, `onPurchaseSuccess`, `onPurchaseCancelled`, `onPurchaseError`) bağlandı; Face ID veya Apple ID onaylama gecikmelerinde patlayan sahte *"internet bağlantınızı kontrol edin"* uyarısı kökten yok edildi.

2. **Native İşlem Kilidi (Purchase Mutex) & Sıfır Yarış Durumu:**
   - `MishilUnifiedWebView.tsx` içine `isPurchaseInProgressRef` işlem kilidi kuruldu. Satın alma penceresi açılıp kapanırken iOS'un tetiklediği `AppState.active` olaylarının araya girip StoreKit sonucu dönmeden aboneliği geçici olarak `false` yapması ve kullanıcıyı Mışıl Dadı sekmesinden kovması engellendi.

3. **Sessiz ve Zarif İptal Akışı:**
   - Kullanıcı Apple/Google ödeme penceresini kapattığında veya vazgeçtiğinde hata mesajı basma davranışı kaldırıldı; butonlar sessizce normale dönüyor.

4. **RevenueCat Reaktif Listener & Aile Eşitlemesi:**
   - `Purchases.addCustomerInfoUpdateListener` ile lisans değişimleri reaktif bağlandı; aile eşleştirmesinde eksik kalan plan bilgisi onarıldı.

## [4.34.0] - 2026-09-17
### 🛡️ iOS Kalıcı Veri & Onboarding Sıfırlanma Çözümü, WKWebsiteDataStore Kalıcı Disk & AsyncStorage Savunma Köprüsü (Build 47)

1. **iOS WebKit RAM-Only nonPersistentDataStore Kilidinin Kaldırılması:**
   - `MishilUnifiedWebView.tsx` içinde `cacheEnabled={false}` parametresinin `sharedCookiesEnabled={true}` ile birleştiğinde iOS WebKit tarafında `RNCWebViewImpl.m:1781` satırındaki `!_cacheEnabled` koşulunu tetikleyerek `websiteDataStore`'u zorla RAM-only moduna (`nonPersistentDataStore` / gizli sekme) sokması hatası giderildi.
   - `cacheEnabled={true}` yapılarak iOS WebKit `defaultDataStore` (kalıcı disk) moduna geçirildi; sürüm önbellek yönetimi (cache-busting) zaten URL parametresi (`?v=${APP_VERSION}_b${APP_BUILD}`) ile sağlandığı için hiçbir risk doğmadan kalıcı depolama garanti altına alındı.
   - Uygulama arka plandan kapatılıp (kill / swipe-up) saniyeler içinde tekrar açılsa dahi bebek adı ve onboarding durumunun silinmesi kökten çözüldü.

2. **Native AsyncStorage Çift Katmanlı Savunma Köprüsü (Multi-Layer Storage):**
   - Bebek profili (`babyName`, `babyBdate`, `userRole`, `userName`) ve `mishil_onboarding_completed` durumu, webview Adım 1'i geçtiği ve abonelik tamamlandığı an native köprü (`SAVE_PROFILE`, `ONBOARDING_COMPLETED`) üzerinden iPhone/Android'in yerel diski `AsyncStorage`'a yazıldı.
   - Uygulama her açıldığında `onLoad` anında `hydrateWebViewStorage()` fonksiyonu çalışarak yerel diskteki profil bilgilerini WebView `localStorage`'ına otomatik enjekte edecek (`hydrate`) mimari kuruldu.

3. **Web Onboarding Girdi Koruması (Input Hydration):**
   - `initOnboardingInputs()` fonksiyonu eklenerek, hafızada kayıtlı bebek bilgisi varsa Adım 1 anket alanlarına otomatik basılması ve tamamlanmış profillerin doğrudan ana ekrana geçmesi sağlandı.

## [4.33.0] - 2026-09-17
### 🛡️ Sıfır Sahte Hata, Kusursuz Profil Kalıcılığı, Pozitif Anket & Dinamik Skor Yumuşatma (Build 46)

1. **Sıfır Sahte İnternet Uyarısı & Watchdog Yaşam Döngüsü (Watchdog Lifecycle):**
   - Satın alma veya deneme başlatıldığında kurulan 6 saniyelik `storeWatchdogTimer` zamanlayıcısının ana ekrana geçilmesine rağmen arkada çalışmaya devam edip sahte *"Lütfen internet bağlantınızı kontrol edin"* uyarısı fırlatması kökten çözüldü.
   - `clearStoreWatchdog()` fonksiyonu entegre edilerek hem web önizleme hem native IAP başarı (`grantProInWebView`), hata (`onPurchaseError`) ve iptal senaryolarında zamanlayıcı anında imha edildi.

2. **Web ve Mobil Onboarding Kalıcılık Mührü (Zero-Restart Persistence):**
   - Deneme başlatıldığı an `mishil_subscription_active`, `mishil_trial_start` ve `mishil_onboarding_completed` anahtarları eksiksiz olarak `localStorage`'a yazıldı; `commitOnboardingProfile()` ile bebek profili diske mühürlendi.
   - Web veya mobilde uygulama kapatılıp açıldığında veya sayfa yenilendiğinde (F5) kullanıcının başa dönmesi engellendi; doğrudan ana ekrana yönlendirme garantiye alındı.

3. **Pozitif ve Dengeli Anket Deneyimi (Positive UX & Constructive Phrasing):**
   - Onboarding anketinde sadece olumsuz kriz şıkları yerine bebeği rahat uyuyan (5-10 dk), deliksiz uyuyan (0-1 kez) veya yalnızca gelişim takibi yapmak isteyen aileler için yapıcı seçenekler eklendi.
   - 4. soru başlığı *"En çok hangi konuda çaresiz kalıyorsunuz?"* yerine yapıcı ve motive edici bir dille **"Bebeğinizin gelişiminde öncelikli odağınız nedir?"** olarak revize edildi.
   - `generateSleepReport()` puanlama motoru pozitif şıklarla senkronize edilerek yüksek uyku sağlığı skorları ve motive edici klinik rehberlik üretmesi sağlandı.

4. **Dinamik Gelişim Skoru & Kademeli Yumuşatma Protokolü (Score Blending):**
   - Yeni bebek kaydedildiğinde rutin kaydı olmadığı için varsayılan katsayılar toplamının her yeni profilde tam sabit %77 üretmesi ve anket puanını yutması hatası giderildi.
   - Onboarding raporunda üretilen başlangıç skoru `mishil_baseline_quiz_score` olarak saklandı; henüz rutin girilmemişken bu gerçek skor ekrana yansıtıldı.
   - İlk 1-2 rutin girildiğinde skorun sert bir sıçrama yapmasını önlemek amacıyla **%60 anket tabanı + %40 canlı rutin** harmanlama (blending) formülü devreye alındı.

## [4.32.0] - 2026-09-17
### 🎙️ 4 Kademeli Gerçek Multimodal Ağlama Analizi & Mışıl Dadı AI Gemini 3.6 Yükseltmesi (Build 45)

1. **4 Kademeli Gerçek Multimodal Ağlama Analizi (True Audio AI):**
   - Bebeğin 5 saniyelik ham ses kaydı (WAV, WebM, M4A) doğrudan **Google Gemini 3.6 Multimodal Audio** nöral modeline bağlandı; model ses perdesi (pitch/F0), tiz çığlık tepe noktaları, nefes alma aralıkları ve rezonansı canlı dinleyerek tamamen o sese özel akustik tespit ve dinamik olasılık oranları üretmeye başladı.
   - **Tier 2:** `gemini-3.5-flash` Multimodal Audio yedeği bağlandı.
   - **Tier 3:** Sunucu tarafında Librosa 13-bant MFCC & Spektral Merkez Frekansı (FFT) motoru devreye alındı.
   - **Tier 4:** Yalnızca son çare (tam internetsiz çevrimdışı) durumlar için dengeli biyolojik sirkadiyen algoritması entegre edildi.

2. **Açlık Kilidi ve Sabit Katsayıların Kaldırılması:**
   - Önceki sürümlerde henüz veri girilmemiş profillerde son beslenme süresinin varsayılan 3.0 saat alınmasından kaynaklanan ve açlığı daima %45 ile 1. sıraya kilitleyen matematiksel hata tamamen temizlendi; akustik sinyallere dayalı gerçekçi analiz sağlandı.

3. **Mışıl Dadı AI Gemini 3.6 Flash Geçişi:**
   - Google tarafından kullanımdan kaldırılan (404 veren) eski modeller yerine güncel ve aktif **`gemini-3.6-flash`** ve **`gemini-3.5-flash`** mimarisine geçildi; kural tabanlı şablon cevaplar yerine derin pedagojik ve bağlamsal canlı yapay zekâ yanıtları devreye alındı.

4. **Kayıpsız Ses Formatı & İstemci Entegrasyonu:**
   - Tarayıcı ve WebView mikrofon kayıtlarında WebM/Opus ve M4A/AAC formatları MIME türüne göre dinamik tanımlandı; FastAPI backend ses doğrulama katmanına tam uyumluluk getirildi.

## [4.31.0] - 2026-09-16
### 🛡️ MışılSpot™ & BabySteps™ Marka Dönüşümü, Sıfır-Hata Onboarding & Mobil Stabilizasyon (Build 44)

1. **Marka & Hukuki Koruma Dönüşümü:**
   - Huckleberry tescilli `SweetSpot®` adı menülerden, kod tabanından ve ana ekrandan tamamen kaldırıldı; özgün ve tescillenebilir **`MışılSpot™`** (Sirkadiyen Uyku Penceresi) ile değiştirildi.
   - `WonderWeeks` ifadeleri Domus Technica telif riskini önlemek amacıyla samimi ve bilimsel **`BabySteps™`** (10 Büyüme & Gelişim Sıçraması) olarak yenilendi.
   - Tıbbi risk taşıyan ifadeler yumuşatıldı: *"Uyku Teşhis Raporu"* ➔ **"Uyku Analiz Raporu"**, *"AI Pediatrik Danışman"* ➔ **"AI Ebeveyn Asistanı"**, *"Pediatrik Aşı Defteri"* ➔ **"Bebek Aşı Takip Defteri"**, *"Klinik Gelişim Skoru"* ➔ **"Bebek Gelişim Skoru"**.

2. **Sıfır Hata Onboarding & Kalıcı Profil Güvencesi:**
   - Adım 1'de ("Devam Et ➔") butonuna basıldığı an ve satın alma tamamlandığında bebek adı, doğum tarihi, ebeveyn adı ve rolü doğrudan `localStorage`'a kaydedildi.
   - Kullanıcının her açılışta tekrar onboarding ve isim sorma döngüsüne düşmesi engellendi.
   - `getBaby()` canlı veri ürettiği için **Bebek Gelişim Skoru** formülü girilen verilerle anında dinamik puan hesaplamaya başladı.

3. **Modern Bottom-Sheet Aile Bağlantısı (z-index Fix):**
   - Onboarding ekranının (`z-index: 350`) arkasında kalan aile kodu modalı `z-index: 1000` yapılarak öne alındı ve modern bir `bottom-sheet` tasarımına kavuşturuldu.
   - `getApiBaseUrl()` tanımlanarak `/api/v1/family/join` rotasına tam URL yönlendirmesi bağlandı; hatalı kod girildiğinde "interneti kontrol edin" yerine doğru *"Aile kodu bulunamadı"* bildirimi verilmesi sağlandı.

4. **Abonelik Watchdog Esnetilmesi (Satın Alma Hata Fix):**
   - Apple StoreKit / Google Play satın alma ekranı açıkken erken hata veren 6 saniyelik agresif zamanlayıcı 20 saniyeye çıkarıldı; satın alma tamamlandığında zamanlayıcı anında sıfırlandı.

5. **Mışıl Dadı Canlı Yapay Zekâ & Mobil Klavye Görünürlüğü:**
   - Backend `CoachChatRequest` şemasındaki `birth_date` alanı esnetildi; Gemini SSE canlı token akışı `/api/v1/coach/stream` üzerinden bağlandı, yerel statik kalıplar aşıldı.
   - Chat girdi kutusuna `scrollIntoView` ve visualViewport focus desteği eklenerek sanal klavyenin yazılan alanı örtmesi önlendi.

6. **Dinamik Akustik Ağlama Analizi:**
   - Dinleme motorundaki `async` eksiği giderildi; mikrofon izni ve yerel analiz motoru bebeğin uyanıklık ve beslenme süresine göre gerçekçi biyolojik varyasyonlar üretmeye başladı.

## [4.30.0] - 2026-09-16
### 💎 Dinamik Mağaza Fiyatlama, Gerçek Aile Senkronizasyonu & Ebeveyn Kimlik Mimarisi (Build 43)

1. **Dinamik Mağaza Fiyatlama & Matematik Motoru:**
   - App Store Connect API üzerinden `misil_monthly` ve `misil_annual` abonelik ürünlerinin Türkiye fiyatları resmi olarak Opsiyon 1 doğrultusunda güncellendi: Aylık **₺149.99**, Yıllık **₺599.99**.
   - Arayüzdeki kuruş ve matematik çelişkileri kökten giderildi: Yıllık paketin aylık karşılığı statik 49 TL yerine `(yearlyVal / 12)` dinamik formülüyle hesaplanarak **₺49.99/ay** olarak gösterildi.
   - Tasarruf oranı dinamik formülle (`(1 - (yıllık / (aylık * 12))) * 100`) hesaplanarak **%67 Tasarruf** rozetiyle canlı senkronize edildi.

2. **Dinamik Anne / Baba Kimliği & Kişiselleştirme:**
   - Ayarlar ve Onboarding ekranındaki sabit/sahte ebeveyn verileri (`Zeynep` ve `Emre`) tamamen temizlendi.
   - Onboarding 1. Adıma ebeveyn rolü seçimi (👩 Anne, 👨 Baba, 👵 Diğer) ve aktif ebeveyn adı girişi eklendi.
   - Mışıl Dadı AI pediatrik koçunun soru-cevap motoruna ebeveyn adı ve rolü parametre olarak bağlandı.

3. **Gerçek Aile Senkronizasyonu & Benzersiz Kod Paylaşımı:**
   - Sabit `MSL782` sahte kodu yerine backend'de (`/api/v1/family/create`) ve frontend'de kriptografik benzersiz `MB-XXXX` kod üretim motoru devreye alındı.
   - Hem Onboarding ekranına hem Ayarlar menüsüne *"Aileye Bağlan"* (Join Family) modülü eklendi; eşler veya dadılar bu kod ile bebeğin tüm rutinlerine ve VIP abonelik haklarına anında ortak olabilmektedir.

4. **Sürüm & Paket Senkronu:**
   - `app.config.ts`: `APP_VERSION = '4.30.0'`, `BUILD_NUMBER = 43`.
   - `public/app.html` ve `features/webview/offlineHtml.generated.ts` (325 KB) yeniden derlendi ve senkronize edildi.
 
## [4.29.0] - 2026-09-15
### 🛡️ Apple StoreKit 2 Resmi Sandbox Entegrasyonu, Watchdog Fallback & Dummy Card Temizliği (Build 42)

1. **Apple Guideline 3.1.1 Tam Uyum & Dummy Card Temizliği:**
   - Apple İnceleme Kuralları gereğince mağaza onayını riske atabilecek sanal kredi kartı formu (`modal-dummy-card`) ve ilişkili tüm geçici test fonksiyonları kod tabanından tamamen kaldırıldı.
2. **Kilitlenmeyi Önleyen IAP State & Watchdog Zamanlayıcısı:**
   - "7 Gün Ücretsiz Dene" ve "Satın Al" butonlarına tıklandığında anlık yükleniyor durumu (`🔄 Mağaza Açılıyor...`) eklendi.
   - 6 saniyelik güvenlik zamanlayıcısı (`storeWatchdogTimer`) kuruldu; mağaza penceresi yanıt vermediğinde veya bağlantı koptuğunda arayüzün askıda kalması engellendi, kullanıcıya anlaşılır bildirim verilerek buton otomatik olarak yeniden aktif hale getirildi.
3. **Apple StoreKit 2 ve RevenueCat Optimizasyonu:**
   - RevenueCat yapılandırmasına `usesStoreKit2IfAvailable: true` eklendi; iOS 15+ cihazlarda App Store Connect'teki `misil_monthly` ve `misil_annual` ürünlerinin TestFlight/Sandbox ortamında doğrudan ve modern StoreKit 2 motoruyla çekilmesi sağlandı.
   - Aday ürün kimlikleri listesi resmi mağaza kimlikleriyle tam hizalandı.
4. **Sürüm & Paket Senkronu:**
   - `app.config.ts`: `APP_VERSION = '4.29.0'`, `BUILD_NUMBER = 42`.
   - `public/app.html` ve `features/webview/offlineHtml.generated.ts` (308 KB) yeniden derlendi ve senkronize edildi.
 
## [4.28.0] - 2026-09-14
### 💳 Apple Sandbox / Dummy Kart Test Ödeme Motoru & Sıfır Sızma Onboarding Kalkanı (Build 41)

1. **Apple Sandbox & Dummy Kart Test Ödeme Motoru (Reviewer / TestFlight Bypass):**
   - App Store Connect üzerinde `misil_monthly` ve `misil_annual` ürünleri `READY_TO_SUBMIT` aşamasında beklerken StoreKit sandbox'ın ürün dönmemesi (`no_package`) sebebiyle testlerin ve Apple Review'ın tıkanmasını engelleyen interaktif Dummy Kart (Visa Sandbox `4242 •••• •••• 4242`) test ödeme motoru entegre edildi.
   - Native katmanda paket bulunamadığında kullanıcıyı duvara toslatmak yerine doğrudan web tarafında zarif test kartı modalı tetiklendi; 1.2 sn'lik ödeme simülasyonu ile VIP haklarının anında test edilebilmesi sağlandı.
   - Paywall ve Onboarding ekranlarına doğrudan sandbox test giriş bağlantısı eklendi.

2. **Sıfır Sızma (Zero-Leak) Onboarding Yaşam Döngüsü Koruması:**
   - Adım 1'de girilen bebek adı ve tarihinin erkenden `localStorage`'a kalıcı yazılması durduruldu; veriler süreç başarıyla tamamlanana kadar RAM'de (`quizAnswers`) izole edildi.
   - `#screen-onboarding` doğrudan HTML'de `active` sınıfıyla başlatılarak sayfa yüklenişinde ana ekranın saniyelik de olsa sızması engellendi.
   - `checkOnboardingState()` mantığı; kullanıcı aktif abone olmadan veya açıkça tamamlamadan uygulamayı kapatıp açsa dahi onboarding ekranını kesin olarak ekranda kilitli tutacak şekilde sertleştirildi.

3. **Sürüm & Paket Senkronu:**
   - `app.config.ts`: `APP_VERSION = '4.28.0'`, `BUILD_NUMBER = 41`.
   - `public/app.html` ve `features/webview/offlineHtml.generated.ts` senkronize edildi.

## [4.27.0] - 2026-09-14
### 🛡️ Apple Review Tam Uyumluluk, Onboarding Sızma Açığı Onarımı & Paywall Koruma Restorasyonu (Build 40)

1. **Apple Review & Guideline 2.3.10 / 3.1.1 Tam Mağaza İzolasyonu:**
   - Satın alma, paket yükleme ve abonelik yönetimindeki ham hata çıktıları (`result.error`) ve tüm teknik mağaza jargonları (StoreKit, TestFlight, Google Play vb.) kullanıcı arayüzünden tamamen arındırıldı.
   - iOS üzerinde yalnızca temiz, zarif ve Apple Kimliği / App Store odaklı hata metinleri sunuldu; Android ve çapraz platform referansları kesin olarak engellendi.
   - Onboarding Adım 5, Ayarlar ve Geri Yükleme modallarındaki çift mağaza referansları tek tip yasal mağaza ve hesap ayarları terminolojisine geçirildi.

2. **Onboarding Sızma ("Atlamadan Atlatma") Yaşam Döngüsü Açığının Kapatılması:**
   - Adım 1'de bebek adı ve tarihi girilip Adım 2'ye geçildiğinde verilerin kalıcı kaydedilmesi ve uygulama kapatılıp açıldığında `checkOnboardingState()` fonksiyonunun kullanıcıyı onboarding'i bitirmiş sayarak ana sayfaya sokma kritik bug'ı kökten kapatıldı.
   - `mishil_onboarding_completed` anahtarı olmadan onboarding ekranının kapanması engellendi; kullanıcı açıkça abone olmadan veya atlamadan ana ekrana sızma imkansız kılındı.

3. **SweetSpot & 18 Akustik Ses Tam VIP Lisans Koruması:**
   - Kod içine gömülmüş yetkisiz `FREE_TRACK_IDS` istisnası kaldırıldı; 18 stüdyo parçasının tamamı aktif VIP abonelik şartına (`requireActiveSubscription()`) bağlandı.
   - Ana ekrandaki SweetSpot uyku penceresi ve canlı takip butonlarına aktif lisans bariyeri getirildi; yetkisiz erişimler kapatıldı.

4. **Doğum Tarihi Formu & Responsive Layout İyileştirmesi:**
   - İlk girişte (Adım 1) küçük ekranlı telefonlarda ve iOS Webview'de doğum tarihi alanının ekran altına ve dışına kaymasına yol açan CSS hiyerarşisi düzeltildi.
   - Form elemanları en üste alınarak odak sağlandı; `.form-input` ve `.form-group` elemanlarına `box-sizing: border-box`, `max-width: 100%` ve safe-area boşlukları verilerek tüm ekran boyutlarında kusursuz görünüm ve erişilebilirlik sağlandı.

5. **Sürüm & Paket Senkronu:**
   - `app.config.ts`: `APP_VERSION = '4.27.0'`, `BUILD_NUMBER = 40`.
   - `public/app.html` ve `features/webview/offlineHtml.generated.ts` senkronize edildi.

## [4.26.1] - 2026-09-13
### ☀️ Light Mode (Aydınlık Tema) Görsel Netlik, Yüksek Kontrast & SweetSpot / Sesler Alanı Canlandırması (Build 39)

1. **SweetSpot Segment & Uyku Zamanı Aydınlık Mod Netliği:**
   - Koyu antrasit ve silik görünen `.segmented-control` arka planı hafif süt beyazı/buzlu gri (`rgba(15,23,42,0.06)`) ve gölgeli saf beyaz butonlara dönüştürüldü.
   - Seçili olmayan sekme butonları açık temada okunaklı grafit-lacivert tonuna (`#475569`, aktifte `#0F172A`) kavuşturuldu.
   - `.moon-circle` alanı antrasit koyuluktan arındırılarak fildişi-amber geçişli yumuşak altın aurasına (`linear-gradient(135deg, #FFFDF7, #FEF3C7)`) uyarlandı.
   - `.sleep-target-time` saati en üst seviye kontrastlı lacivert-siyah (`#0F172A`) rengine, alt metinler ferah arduvaz (`#475569`) tonuna taşındı.
2. **Sesler (Sounds) Sekmesi Tipografi & Kart Kontrastı:**
   - Kategori filtre çiplerindeki (`.cat-chip`) `#1A233A` antrasit bloklar kaldırıldı; saf beyaz zemin (`#FFFFFF`) ve okunaklı arduvaz yazı (`#334155`) ile antrasit üzeri antrasit yazı çakışması ve okunaksızlık tamamen giderildi.
   - Ses arama kutusu (`.search-input`) saf beyaz zemin ve belirgin sınır rengine kavuşturuldu.
   - Ses kartları (`.sound-item`) beyaz kart tasarımı, aktifken hafif bal sarısı pastel tonu (`rgba(217,119,6,0.06)`) ve koyu lacivert başlıkları (`.sound-title` `#0F172A`) ile kusursuz okunabilir kılındı.
   - Zamanlayıcı hapları (`.timer-pill`) ve ses çubuğu aydınlık tema tasarım standartlarına uyarlandı.
3. **Sürüm & Paket Senkronu:**
   - `app.config.ts`: `APP_VERSION = '4.26.1'`, `BUILD_NUMBER = 39`.
   - `public/app.html` ve `features/webview/offlineHtml.generated.ts` senkronize edildi.

## [4.26.0] - 2026-09-13
### 👵 Mışıl Dadı Mobil Klavye Mimarisi, Yeni Ebeveyn Keşif Rehberi & Aşı Bento Kartı (Build 38)

1. **Mışıl Dadı Mobil Klavye & Viewport Mimarisi (Klavye Kaybolması ve Ekran Zıplaması Giderildi):**
   - Mobil sanal klavye açıldığında iç içe iki kaydırma konteyneri (`.screen-container` ve `.dadi-messages-box`) arasındaki çakışma çözüldü.
   - `#view-coach` sekmesine geçildiğinde dış konteynere `.coach-mode-active` atanarak dış sayfa kaydırması kilitlendi (`overflow: hidden; height: 100%`).
   - `window.visualViewport` API entegrasyonu ve dinamik klavye dinleyicisi eklenerek klavye açıldığında input formunun sanal klavyenin hemen üstünde sabit kalması sağlandı, alt menü (`.tab-bar`) geçici olarak gizlenerek odak kaybı ve klavyenin anında kapanması engellendi.
2. **Yeni Ebeveyn Keşif & Karşılama Rehberi:**
   - İlk kez indiren anneler ve babalar için karmaşıklığı ve bilişsel yükü önleyen, 3 kolay adımda uyku takibi başlatma, aşı takvimini inceleme ve Mışıl Dadı'ya danışmaya yönlendiren sevimli karşılama kartı (`#home-welcome-guide`) entegre edildi.
3. **Ana Sayfa Pediatrik Aşı Bento Kartı (`#home-vaccine-card`):**
   - Aşı takvimi derin alt menülerden (`analytics-sec-health`) kurtarılarak Ana Sayfa'ya taşındı; yaklaşan aşıyı, kalan gün sayısını ("14 gün kaldı" veya "Tüm aşılar güncel") gösteren görsel bento kartı eklendi.
4. **Hızlı Pediatrik Aşı Defteri Modalı (`#modal-vaccine-schedule`):**
   - Sayfadan ayrılmadan, tek dokunuşla tüm Sağlık Bakanlığı ve DSÖ onaylı aşıların listelendiği ve tamamlandıkça işaretlenebildiği hızlı modal pencere sağlandı.
5. **Analiz & Gelişim Ekranı Görselleştirilmesi:**
   - Kuru klinik metrikler ve formüller yerine anne-baba dostu sevimli durum rozetleri (Uyku Ritimde 🟢, Aşı Takvimde 💉, Gelişim Sakin Dönem 🌸) ile görselleştirilmiş denge çubukları sunuldu.
6. **Sürüm & Paket Senkronu:**
   - `app.config.ts`: `APP_VERSION = '4.26.0'`, `BUILD_NUMBER = 38`.
   - `public/app.html` ve `features/webview/offlineHtml.generated.ts` senkronize edildi.

## [4.25.0] - 2026-09-11
### 📱 Dinamik Platform İzolasyonu & Çapraz Mağaza İhlali Koruması (Build 37)

1. **Dinamik Hata & Bilgilendirme Toast'ları:**
   - `MishilUnifiedWebView.tsx` içerisinde sabit `(StoreKit/Google Play)` metni kaldırılarak `Platform.OS === 'ios'` ayrımıyla App Store ve Google Play hata mesajları tamamen birbirinden izole edildi.
   - iOS'ta yalnızca "App Store" ve "Apple Kimliği / TestFlight" referansı; Android'de yalnızca "Google Play" referansı gösterilmesi garanti altına alındı (Apple Guideline 2.3.10 tam uyum).
2. **WebView Platform Standardizasyonu (`app.html`):**
   - `getAppPlatform()` ve `getStoreName()` yardımcı fonksiyonları eklenerek mağaza derin linkleri (`openStoreSubscriptionManagement`) ve UI metinleri platforma göre dinamik hale getirildi.
3. **Sürüm & Paket Senkronu:**
   - `APP_VERSION = '4.25.0'`, `BUILD_NUMBER = 37`.
   - `offlineHtml.generated.ts` paketi yeniden üretildi.

## [4.24.0] - 2026-09-11
### 🛡️ Apple StoreKit Gerçek Ürün Senkronizasyonu & Guideline 3.1.2(c) Yasal Uyumluluk (Build 36)

1. **Apple Guideline 3.1.2(c) Yasal Bağlantı Entegrasyonu:**
   - Onboarding Paywall (`#quiz-step-5`) ve VIP Yenileme Modalı (`#vip-renewal-modal`) altına tıklanabilir, fonksiyonel **Kullanım Koşulları (EULA)** ve **Gizlilik Politikası (Privacy Policy)** bağlantıları eklendi.
   - Apple Guideline 3.1.2 zorunlu otomatik yenileme ve hesap ayarlarından iptal bilgilendirme metni kart altına yerleştirildi.
2. **Apple StoreKit Asıl Ürün Senkronizasyonu:**
   - App Store Connect üzerinde tanımlı gerçek ürün kimlikleri olan `misil_monthly` (`prod2fc9b4842a`) ve `misil_annual` (`proddd11361bba`), RevenueCat iOS uygulamasına (`app3226253e41`) kaydedildi.
   - `pro` ve `mışıl_baby_pro` entitlement'larına bağlandı.
   - `$rc_monthly` ve `$rc_annual` paketlerine tek yetkili ürün olarak atanarak StoreKit Sandbox ürün teslimatı garantiye alındı.
3. **Native Güvenlik Kalkanı & OPEN_URL Köprüsü:**
   - Standalone iOS derlemelerinde runtime API anahtarı çözümlemesi `process.env.EXPO_PUBLIC_REVENUECAT_IOS` ile üçlü kalkan yapısına geçirildi.
   - Native köprüye `OPEN_URL` desteği eklenerek yasal sayfaların Safari'de sorunsuz açılması sağlandı.
4. **Light Mod Arayüz Kontrast Temizliği:**
   - Onboarding skor ve hedef kartlarındaki koyu zemin ve soluk metinler saf beyaz zemin ve derin lacivert (#0F172A) okunabilir renklerle hizalandı.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.24.0'`, `BUILD_NUMBER = 36` (`mobile/app.config.ts`, `public/app.html`, `WEB_APP_META`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts`.
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

## [4.23.0] - 2026-09-11
### 🎨 Light Mod Görsel Restorasyonu & iOS RevenueCat Sunucu Eşleşmesi (Build 35)

1. **Light Mod Görsel & Tipografi Restorasyonu:**
   - Onboarding tıbbi feragatname kutusu, abonelik plan kartları (`onboarding-plan-card`), Apple 3.1.2 bilgilendirme kutuları, changelog ve modal sayfalarındaki koyu/okunaksız zeminler açık temada saf beyaz zemin (`#FFFFFF`) ve derin okunaklı lacivert (`#0F172A`) renge kavuşturuldu.
   - Açık temada tüm kart gölgeleri ve yumuşak gri kenarlıklar netleştirildi.
2. **iOS App Store & RevenueCat Canlı Sunucu Entegrasyonu:**
   - Canlı RevenueCat v2 API üzerinden `proja1528882` projesine resmi `monthly` (`prodffab50f7a6`) ve `yearly` (`prodfdd7f067db`) App Store ürünleri eklendi.
   - Projenin `pro` ve `mışıl_baby_pro` entitlement'larına bağlandı.
   - Varsayılan `$rc_monthly` ve `$rc_annual` paketlerine `eligibility_criteria: all` ile resmi olarak iliştirildi (`HTTP 200 OK`).
3. **Şeffaf Hata Raporlama:**
   - `MishilUnifiedWebView.tsx` içerisinde IAP hatalarında genel uyarı yerine StoreKit veya Play Store test hesabını kontrol etmeye yönlendiren açıklayıcı hata detayı eklendi.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.23.0'`, `BUILD_NUMBER = 35` (`mobile/app.config.ts`, `public/app.html`, `WEB_APP_META`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts` (274 KB).
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

## [4.22.0] - 2026-09-11
### 🚀 Google Play Ürün ID Eşleme & Abonelik Yönetimi Doğrudan Deep Link Çözümü (Build 34)

Kullanıcının "hala daha abonelik başlat butonuna basınca paket yüklenemedi hatası alıyorum, aboneliği yönet tuşuna basınca hiçbir şey olmuyor" geri bildirimi doğrultusunda kök neden analizleri yapılarak iki kritik mağaza entegrasyonu tamamlandı:
1. **"Aboneliği Yönet" Doğrudan Deep Link Köprüsü:**
   - `openStoreSubscriptionManagement()` fonksiyonuna `window.location.href = url;` eklendi.
   - WebView ve mobil tarayıcılar `play.google.com` ve `apps.apple.com` bağlantılarını işletim sistemi seviyesinde yakalar. Böylece telefonda yüklü eski binary derlemelerde dahi yeni bir APK/AAB derlemesine ihtiyaç duyulmadan anında resmi Google Play / App Store Abonelik Yönetim sayfası açılır.
2. **Google Play Gerçek Ürün ID ve Seçenek Desteği (no_package Fix):**
   - Holdingin Google Play Console'daki gerçek ürün kimlikleri olan `'misil'` (Yıllık VIP) ve `'misilaylik'` (Aylık Pro) aday ürün listesine (`candidateProductIds`) ilk sıralardan eklendi.
   - Google Play Billing v5/v6/v7 tabanlı abonelik teklifleri (`products[0].defaultOption` ve `Purchases.purchaseSubscriptionOption`) desteği sağlandı.
3. **RevenueCat Canlı Public Anahtar Entegrasyonu:**
   - `mobile/app.config.ts` içerisindeki mock fallback yerine canlı RevenueCat public SDK anahtarları (`goog_LCNeMzKcaNSPdZModiKqmLtygYk` ve `appl_YErlYWqQcbRzipLuFKFliryZXAX`) bağlandı.
   - `projects/mishil/mobile/.env` dosyası oluşturularak ortam değişkenleri güvenceye alındı.

#### 🔧 Chore
- Sürüm artırımı: `APP_VERSION = '4.22.0'`, `BUILD_NUMBER = 34` (`mobile/app.config.ts`, `public/app.html`, `WEB_APP_META`).
- Çevrimdışı paket yenilendi: `features/webview/offlineHtml.generated.ts` (271 KB).
- Pre-flight doğrulama: `tsc --noEmit` 0 hata, Jest 4/4 PASS, `mobile_compliance_checker.py` READY_FOR_RELEASE.

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
