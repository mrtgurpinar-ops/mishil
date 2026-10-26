# Mışıl Baby — Aşama 2: Organic Warm Bento Grid & Ana Sayfa Restorasyonu Uygulama Planı

| Metrik | Değer |
| :--- | :--- |
| **Tahmini Efor** | ~45 - 60 Dakika |
| **Kalan Kapasite Kullanımı** | Yaklaşık %10 - 14 |
| **Risk Seviyesi** | **Seviye 2 (Orta Risk / Standart UI Modülü - Çift Kontrol)** |
| **Hedef Sürüm** | `v4.42.0` (Build 60) — Holding: `v8.59.0` |
| **Etkilenecek Dosyalar** | `projects/mishil/public/app.html`, `projects/mishil/mobile/app.config.ts`, `projects/mishil/CHANGELOG.md` |

---

## 🎯 1. Netleştirilmiş Hedef & Kapsam (Refined Prompt)
Mışıl Baby ana ekranındaki sıkışık, derinliksiz ve kontrastı zayıf kart blokları kaldırılarak, kullanıcının seçtiği **Öneri 2B: Organic Warm Bento (Kaşmir & Mum Işığı Anne-Bebek Dünyası)** mimarisine dönüştürülecektir:
1. **Panoramik Hero Bento Kartı (`.hero-organic-card`):**
   - Üstte tam genişlikte ferah, 26px organik köşe radüslü, sıcak kaşmir cam kart.
   - Merkezde yavaşça nefes alıp veren sıcak kehribar mum ışığı aurası (`.warm-moon-aura`) ve büyük altın hilal.
   - 38px cesur saat tipografisi (`#target-sleep-display`), dinamik geri sayım (`#target-sleep-subtext`) ve canlı uyku sayacı (`#live-sleep-timer`).
2. **İkincil Çiftli Organik Bento Grid (`.grid-organic-duo`):**
   - **Sol Kart (Uyku Kalitesi & Ritim - Adaçayı Yeşili):** `%84` Denge Skoru SVG kadranı (`#home-bento-score-fill`), ritim rozeti (`#home-bento-score-badge`) ve toplam uyku süresi göstergesi.
   - **Sağ Kart (Hızlı Rutinler - Sıcak Şeftali):** Gece loş ışıkta tek dokunuşla çalışan 4 adet pürüzsüz dokunmatik hap buton (*Besle, Bez, Masaj, Ninni*).
3. **%100 DOM ID ve State Güvencesi:**
   - Mevcut tüm DOM ID'leri (`target-sleep-display`, `target-sleep-subtext`, `live-sleep-timer`, `btn-toggle-sleep`, `home-bento-score-val`, `home-bento-score-fill`, `home-bento-score-badge`, `sweetspot-status-badge`, `moon-aura-circle`, `moon-shape`) korunacak; JavaScript'teki canlı uyku ve rutin fonksiyonları sıfır kırılmayla çalışacaktır.
4. **Çift Tema Desteği:**
   - Hem Koyu Kaşmir (#13101C) hem de Sıcak Krem (#FAF6F0) temaları için organik pastel kontrast değişkenleri bağlanacaktır.

---

## 🏎️ 2. Ajan Şerit Dağılımı (Tri-Agent Roles)
* **Claude Şeridi (Mimari & Grid Sistemi):** Bento Grid CSS kütüphanesi, CSS Grid esnekliği, 26px organik radüs tokenları ve Dark/Light mode renk geçişleri.
* **Codex Şeridi (DOM Restorasyonu, GPU Animasyonları & Testler):** Mum ışığı nefes alma animasyonu (`@keyframes candlePulse`, 60fps GPU), hızlı rutin buton işleyicileri, TypeScript (`tsc`) ve Jest birim testleri (10/10 test).
* **Antigravity Şeridi (Orkestrasyon, Doğrulama & Sürüm Yönetimi):** DOM ID ve onclick audit taraması (`audit_app_html.py`), offline paket derlemesi (`bundle:offline`), CHANGELOG ve versiyonlama (`4.42.0`).

---

## 📋 3. Yapılacak İşler ve İcra Adımları

### Adım 1: CSS Altyapısı & Organik Bento Stilleri (`app.html`)
- [ ] `.hero-organic-card`, `.grid-organic-duo`, `.bento-card-sage`, `.bento-card-peach` ve `.routine-pill-btn` sınıflarını tanımlama.
- [ ] Mum ışığı aurası için `@keyframes candlePulse` nefes alma animasyonunu ekleme.
- [ ] Light Mode için yumuşak adaçayı ve şeftali pastel renk tonlarını bağlama.

### Adım 2: HTML Ana Sayfa Markup Restorasyonu (`app.html`)
- [ ] Satır 2695-2745 arasındaki `.hero-bento-row` yapısını yeni panoramik Hero + Çiftli Bento Grid mimarisine dönüştürme.
- [ ] Tüm kritik DOM ID'lerinin korunduğunu teyit etme.
- [ ] Hızlı rutin butonlarını `openAddRoutineModal('feed')`, `openAddRoutineModal('diaper')` vb. fonksiyonlara bağlama.

### Adım 3: JavaScript Etkileşim ve State Senkronizasyonu (`app.html`)
- [ ] `toggleLiveSleep()` fonksiyonunun yeni mum ışığı aurasıyla görsel uyumunu sağlama.
- [ ] Canlı sayaç çalışırken Hero kartının arka plan gradyanını yeşil/mor uyku moduna geçirme.

### Adım 4: Doğrulama ve Test Kapısı
- [ ] `npm run bundle:offline` ile `offlineHtml.generated.ts` dosyasını derleme.
- [ ] `npx tsc --noEmit -p tsconfig.json` ile tip denetimi.
- [ ] `node node_modules/jest/bin/jest.js` ile birim testleri (10/10 PASS).
- [ ] `python scratch/audit_app_html.py` ile DOM ID ve onclick bütünlük taraması.
- [ ] Versiyon güncelleme (`APP_VERSION = 4.42.0`, `BUILD_NUMBER = 60`).

---

## 🛡️ 4. Risk Seviyesi & Kademeli Doğrulama Kapısı (Tiered Review Gate)
* **Risk Seviyesi:** **Seviye 2 (Orta Risk - Dual Check)**.
* **Denetim Odağı:** Ana sayfa DOM ID'lerinin eksiksiz kalması, uykuda/uyanık durum geçişlerinin görsel doğruluğu ve ekran taşmalarının önlenmesi.
* **Onay Şartı:** Kod yazımına başlamadan önce bu planın kullanıcı tarafından onaylanması zorunludur.

---

## ⚠️ 5. Kısıtlar ve Önleyici Tedbirler
- **Kesin Yerel Öncelik:** Tüm geliştirmeler yalnızca yerel test ortamında koşturulacak; kullanıcıdan yazılı canlıya alma onayı gelmedikçe `git push` yapılmayacaktır.
- **Native Build Kısıtlaması:** Webview katmanında kalındığı için native EAS derlemesi tetiklenmeyecektir.
