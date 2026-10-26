# Mışıl Baby — Aşama 1: Huckleberry Pro FAB Dock & Vektörel İkonografi Uygulama Planı

| Metrik | Değer |
| :--- | :--- |
| **Tahmini Efor** | ~45 - 60 Dakika |
| **Kalan Kapasite Kullanımı** | Yaklaşık %12 - 15 |
| **Risk Seviyesi** | **Seviye 2 (Orta Risk / Standart UI Modülü - Çift Kontrol)** |
| **Hedef Sürüm** | `v4.41.0` (Build 59) |
| **Etkilenecek Dosyalar** | `projects/mishil/public/app.html`, `projects/mishil/mobile/app.config.ts`, `projects/mishil/CHANGELOG.md` |

---

## 🎯 1. Netleştirilmiş Hedef & Kapsam (Refined Prompt)
Mışıl Baby mobil webview arayüzünde amatör ve eski bir görüntü yaratan sistem emojili Tab Bar (`🌙`, `📊`, `👵`, `🎵`) tamamen kaldırılarak yerine kullanıcının seçtiği **Öneri 1C: Huckleberry Pro FAB Dock** mimarisi entegre edilecektir:
1. **Merkezi Dairesel FAB (Floating Action Button):** Dock'un ortasında hafifçe yukarı taşan, altın gradyanlı ve parlayan bir canlı eylem butonu (`#dock-center-fab`). Canlı uyku kapalıyken tek tıkla uyku başlatır, canlı uyku açıkken nabız gibi atan altın bir aura (`golden-pulse`) ile sayacı ve bitir butonunu temsil eder.
2. **4 Kanatlı Minimalist SVG İkonografi:** Emojiler yerine 1.5px strok kalınlığına sahip, retina uyumlu saf vektörel SVG ikonlar (*Mışıl Spot Hilali, Analiz Nabız Çizgisi, Mışıl Dadı AI Kıvılcımı, Stüdyo Ses Dalgası*).
3. **Derin Cam Morfolojisi & Ergonomi:** `backdrop-filter: blur(28px) saturate(190%)`, 1px saten üst kenar ışığı, iOS Home Bar güvenli alan (`env(safe-area-inset-bottom)`) entegrasyonu ve dokunma fiziği (`scale(0.92)`).
4. **Çift Yönlü Durum Senkronizasyonu:** `switchTab()` çağrıları ve `toggleLiveSleep()` durumları FAB ve sekme ikonlarıyla gerçek zamanlı reaktif bağlanacaktır.

---

## 🏎️ 2. Ajan Şerit Dağılımı (Tri-Agent Roles)
* **Claude Şeridi (Mimari & Tasarım Sistemi):** SVG sembol kütüphanesinin kurulması, CSS token uyumu, `safe-area` boşluk matematiği ve ekran yüksekliği çakışmalarının önlenmesi.
* **Codex Şeridi (Hızlı Kodlama, Render & Test):** CSS animasyonlarının GPU hızlandırması (`will-change: transform`, 60fps), `switchTab` ve `updateFabSleepState` fonksiyonlarının entegrasyonu, TypeScript ve Jest birim testlerinin yeşile çekilmesi.
* **Antigravity Şeridi (Orkestrasyon, Doğrulama & Dokümantasyon):** `app.html` DOM ID ve onclick bütünlüğü, mobil compliance pre-flight denetimi, CHANGELOG ve versiyonlama yönetimi.

---

## 📋 3. Yapılacak İşler ve İcra Adımları

### Adım 1: CSS & Vektörel SVG İkon Altyapısı (`app.html`)
- [ ] Tab Bar CSS kurallarını `.tab-bar` yerine modern `.huckleberry-dock` ve `.fab-center-btn` sınıflarıyla güncelleme.
- [ ] Her sekmeye dokunulduğunda yaylanma sağlayan `transform: scale(0.92)` mikro dokunma fiziği ekleme.
- [ ] Canlı uyku sırasında altın düğmenin etrafında parıldayan `@keyframes fabPulse` animasyonunu tanımlama.
- [ ] Hem Dark Mode (#13101C) hem de Light Mode (#FAF6F0) için renk ve kontrast değişkenlerini bağlama.

### Adım 2: HTML Tab Bar Markup Restorasyonu (`app.html`)
- [ ] Satır 3389-3406 arasındaki eski emoji tab bar markup'ını 5 elemanlı yeni yapıya dönüştürme:
  1. Sol Dış: `tab-item-home` (Mışıl Spot SVG + Başlık)
  2. Sol İç: `tab-item-analytics` (Analiz Grafiği SVG + Başlık)
  3. **Merkez: `#dock-center-fab`** (58px Altın Hilal / Canlı Uyku FAB Butonu)
  4. Sağ İç: `tab-item-coach` (Mışıl Dadı AI SVG + Başlık)
  5. Sağ Dış: `tab-item-sounds` (Sesler Stüdyo SVG + Başlık)

### Adım 3: JavaScript Durum & Senkronizasyon Mantığı (`app.html`)
- [ ] `switchTab(tabId)` fonksiyonunda SVG ikonlarının `active` durumlarını ve renklerini dinamik güncelleyecek mantığı kurma.
- [ ] `updateFabSleepState()` fonksiyonu yazarak, `isSleeping` değişkeni değiştikçe (`toggleLiveSleep` içinde) FAB butonunun ikonunu (Hilal ➔ Canlı Uyku / Bitir karesi) ve nabız aurasını senkronize etme.
- [ ] Uygulama açılışında (`DOMContentLoaded`) mevcut sekme ve uyku durumuna göre FAB'ı başlatma.

### Adım 4: Doğrulama ve Test Kapısı
- [ ] `npm run bundle:offline` ile `offlineHtml.generated.ts` dosyasını derleme.
- [ ] `npx tsc --noEmit -p tsconfig.json` ile tip denetimi.
- [ ] `node node_modules/jest/bin/jest.js` ile birim testleri (10/10 PASS).
- [ ] `python scratch/audit_app_html.py` ile DOM ID ve onclick bütünlük taraması.
- [ ] Versiyon güncelleme (`APP_VERSION = 4.41.0`, `BUILD_NUMBER = 59`).

---

## 🛡️ 4. Risk Seviyesi & Kademeli Doğrulama Kapısı (Tiered Review Gate)
* **Risk Seviyesi:** **Seviye 2 (Orta Risk - Dual Check)**.
* **Denetim Odağı:** Alt dock yüksekliği ve FAB çıkıntısının ana sayfa içeriği veya modal pencerelerin alt butonlarıyla çakışmaması (z-index ve scroll padding-bottom denetimi).
* **Onay Şartı:** Kod yazımına başlamadan önce bu planın kullanıcı tarafından onaylanması zorunludur.

---

## ⚠️ 5. Kısıtlar ve Önleyici Tedbirler
- **Kesin Yerel Öncelik:** Tüm geliştirmeler yalnızca yerel test ortamında koşturulacak; kullanıcıdan yazılı canlıya alma onayı gelmedikçe `git push` yapılmayacaktır.
- **Native Build Kısıtlaması:** Webview katmanında kalındığı için native EAS derlemesi tetiklenmeyecektir.
