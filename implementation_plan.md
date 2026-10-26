# Mışıl Baby — Aşama 3: Organic Pediatric Hub (C'nin Zekâsı & B'nin Sade Sıcaklığı) Uygulama Planı

| Metrik | Değer |
| :--- | :--- |
| **Tahmini Efor** | ~45 - 60 Dakika |
| **Kalan Kapasite Kullanımı** | Yaklaşık %12 - 15 |
| **Risk Seviyesi** | **Seviye 2 (Orta Risk / Standart UI Modülü - Çift Kontrol)** |
| **Hedef Sürüm** | `v4.43.0` (Build 61) — Holding: `v8.60.0` |
| **Etkilenecek Dosyalar** | `projects/mishil/public/app.html`, `projects/mishil/mobile/app.config.ts`, `projects/mishil/CHANGELOG.md` |

---

## 🎯 1. Netleştirilmiş Hedef & Kapsam (Refined Prompt)
Kullanıcının *"C olsun ama B'nin basitliğini sevmiştim"* yönlendirmesi doğrultusunda, **C'nin güçlü veri zekâsı ve pediatrik analitiği**, **B'nin gözü yormayan sade, organik ve şefkatli arayüz felsefesiyle** sentezlenecektir:

1. **Analiz Sekmesi (`view-analytics` — Sade Biyometrik Hub):**
   - **Üstte Şefkatli Denge Kartı (B'den):** 26px yumuşak köşe radüslü, adaçayı/kaşmir zeminli organik kart. Tek bakışta *"Denge Skoru: %88 • 9 sa 49 dk"* özetini ve sakinleştirici pedagojik geri bildirimi sunar.
   - **Orta Kısımda 7 Günlük Çubuk Trendi (C'den):** Karmaşık teknik tablolardan arındırılmış, pastel tonlu sütunlar (Pt-Pz) ve ortalama uyku süresi göstergesi (`#weekly-avg-sleep-val`).
   - **24 Saatlik Bebek Ritmi & Zirve Saatler:** Acıkma, gaz ve en derin uyku bloklarını sade, net şeritler halinde gösteren pediatrik zirve kartı.
   - **%100 DOM ID Güvencesi:** Mevcut tüm DOM ID'leri (`analytics-score-val`, `analytics-score-badge-val`, `stat-badge-sleep`, `weekly-sleep-bento-chart`, `rollup-sleep-val`, `peak-feeding-hours` vb.) korunacak, JS hesaplamaları sıfır hatayla çalışacaktır.

2. **Sesler Sekmesi (`view-sounds` — Sade Akustik Stüdyo & Loş Gece Çaları):**
   - Gece uykusuz ve loş odadaki anneyi yoracak karmaşık DJ mikserleri yerine, B'nin 2 sütunlu sıcak stüdyo ses kartları mimarisi.
   - Çalan parça üzerinde yavaşça nefes alan amber ses dalgası aurası.
   - **Kapanma Zamanlayıcısı Hapları:** Tek dokunuşla seçilen sade zamanlayıcı butonları (*Sürekli, 15 dk, 30 dk, 45 dk, 60 dk*).
   - Freemium kurallarına tam uyum: 3 temel parça (`womb_amniotic`, `pink_432hz`, `brahms_lullaby`) için `🎁 ÜCRETSİZ` rozetleri, diğer 15 parça için `🔒 VIP` kilitleri.

---

## 🏎️ 2. Ajan Şerit Dağılımı (Tri-Agent Roles)
* **Claude Şeridi (Mimari & Tasarım Sentezi):** C'nin veri yoğunluğu ile B'nin dinginliğini birleştiren CSS mimarisi, pastel adaçayı/şeftali/lavanta renk paleti, 26px organik radüsler.
* **Codex Şeridi (DOM Restorasyonu, Grafik Çizimi & Testler):** `renderWeeklyChart()` çubuk stilleri, `renderSoundsList()` 2 sütunlu bento stüdyo kartı şablonu, TypeScript (`tsc`) ve Jest birim testleri (10/10 test).
* **Antigravity Şeridi (Orkestrasyon, Doğrulama & Sürüm Yönetimi):** DOM ID ve onclick audit taraması (`audit_app_html.py`), offline paket derlemesi (`bundle:offline`), CHANGELOG ve versiyonlama (`4.43.0`).

---

## 📋 3. Yapılacak İşler ve İcra Adımları

### Adım 1: CSS Altyapısı & Sade Organik Hub Stilleri (`app.html`)
- [ ] Analiz ve Sesler ekranları için organik kart (`.analytics-organic-card`), 7 günlük çubuk grafiği ve 2 sütunlu stüdyo ses kartı (`.sound-studio-card`) stillerini tanımlama.
- [ ] Dark Mode Kaşmir (#13101C) ve Light Mode Sıcak Krem (#FAF6F0) uyumlu renk değişkenlerini bağlama.

### Adım 2: Analiz Ekranı Restorasyonu (`view-analytics` — `app.html`)
- [ ] `analytics-sec-sleep` panelindeki Denge Skoru ve Haftalık Çubuk Grafiği bloklarını sade, ferah ve şefkatli tasarıma dönüştürme.
- [ ] Tüm analitik DOM ID'lerinin eksiksiz kaldığını doğrulama.

### Adım 3: Sesler Ekranı & Akustik Stüdyo Restorasyonu (`view-sounds` — `app.html`)
- [ ] `renderSoundsList()` JavaScript fonksiyonunda parça kartlarını 2 sütunlu, dokunması keyifli stüdyo bento kartları olarak render etme.
- [ ] Kapanma zamanlayıcısı haplarını ergonomik hale getirme.

### Adım 4: Doğrulama ve Test Kapısı
- [ ] `npm run bundle:offline` ile `offlineHtml.generated.ts` dosyasını derleme.
- [ ] `npx tsc --noEmit -p tsconfig.json` ile tip denetimi.
- [ ] `node node_modules/jest/bin/jest.js` ile birim testleri (10/10 PASS).
- [ ] `python scratch/audit_app_html.py` ile DOM ID ve onclick bütünlük taraması.
- [ ] Versiyon güncelleme (`APP_VERSION = 4.43.0`, `BUILD_NUMBER = 61`).

---

## 🛡️ 4. Risk Seviyesi & Kademeli Doğrulama Kapısı (Tiered Review Gate)
* **Risk Seviyesi:** **Seviye 2 (Orta Risk - Dual Check)**.
* **Denetim Odağı:** 18 ses parçasının ses çalma motoruyla (`togglePlayTrack`), zamanlayıcıyla (`setTimer`) ve analitik grafikleriyle tam uyumlu kalması.
* **Onay Şartı:** Kod yazımına başlamadan önce bu planın kullanıcı tarafından onaylanması zorunludur.

---

## ⚠️ 5. Kısıtlar ve Önleyici Tedbirler
- **Kesin Yerel Öncelik:** Tüm geliştirmeler yalnızca yerel test ortamında koşturulacak; kullanıcıdan yazılı canlıya alma onayı gelmedikçe `git push` yapılmayacaktır.
- **Native Build Kısıtlaması:** Webview katmanında kalındığı için native EAS derlemesi tetiklenmeyecektir.
