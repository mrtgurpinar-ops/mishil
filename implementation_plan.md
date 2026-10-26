# Mışıl Baby — Aşama 4: Full Sensory Suite (Haptics 2.0, Akustik Crossfade & Gece Beşiği Modu) Uygulama Planı

| Metrik | Değer |
| :--- | :--- |
| **Tahmini Efor** | ~40 - 50 Dakika |
| **Kalan Kapasite Kullanımı** | Yaklaşık %10 - 14 |
| **Risk Seviyesi** | **Seviye 2 (Orta Risk / Standart UI Modülü - Çift Kontrol)** |
| **Hedef Sürüm** | `v4.44.0` (Build 62) — Holding: `v8.61.0` |
| **Etkilenecek Dosyalar** | `projects/mishil/public/app.html`, `projects/mishil/mobile/components/MishilUnifiedWebView.tsx`, `projects/mishil/mobile/app.config.ts`, `projects/mishil/CHANGELOG.md` |

---

## 🎯 1. Netleştirilmiş Hedef & Kapsam (Refined Prompt)
Kullanıcının tercihi doğrultusunda **Öneri 4C (Full Sensory Suite)** hayata geçirilecek; uygulamanın webview tabanlı olduğunu unutturan saf yerel mekanik dokunuşlar, pürüzsüz ses geçişleri ve gece nöbetinde anneyi rahatlatan komodin saati deneyimi entegre edilecektir:

1. **Haptics 2.0 (Çok Katmanlı Apple Dokunsal Geri Bildirim):**
   - `hapticSelection()`: Sekme geçişlerinde, filtre çipleri ve zamanlayıcı haplarında mikroskobik mekanik tık dokusu.
   - `hapticImpact('medium')`: Merkezi altın FAB butonuna (`#dock-center-fab`), canlı uyku başlat/bitir ve modal tetikleyicilerinde tok mekanik darbe.
   - `hapticSuccess()`: Canlı uyku tamamlandığında ve rutin kaydedildiğinde çift ritmik onay titreşimi.
   - React Native köprüsünde (`MishilUnifiedWebView.tsx`) `selection` ve `success` tipleri yerel olarak desteklenecektir.

2. **Akustik Crossfade (0.8s Sinüzoidal Ses Geçişi):**
   - Parça değiştirildiğinde veya durdurulduğunda ani patlama ve kesinti olmadan 0.8 saniyelik yumuşak ses kısılarak geçiş (smooth fade-in / fade-out) sağlanacak; bebek ani ses değişimleriyle irkilmeyecektir.

3. **Gece Beşiği Modu (Melatonin Gece Koruması & Ambient Screen Saver):**
   - Ana başlıkta tek dokunuşla açılan zarif 🌙 butonuyla aktive olan tam ekran loş komodin modu (`#night-ambient-overlay`).
   - Ekranı %10 loşluğa çeker, göz yoran tüm butonları gizler; yavaşça nefes alan sıcak kehribar bir hilal ve büyük dijital saat (`#ambient-clock-val`) gösterir.
   - Ekrana herhangi bir yere dokunulduğunda pürüzsüzce normal ekrana döner.

4. **Spring Physics & Mikro Dokunma Yaylanması:**
   - Kartlara ve butonlara `cubic-bezier(0.34, 1.56, 0.64, 1)` mikro yaylanma dokunuşu kazandırılacaktır.

---

## 🏎️ 2. Ajan Şerit Dağılımı (Tri-Agent Roles)
* **Claude Şeridi (Ses Motoru & Crossfade Mimarisi):** Akustik sinüzoidal gain ramp algoritması, `togglePlayTrack` pürüzsüz geçiş motoru.
* **Codex Şeridi (Haptics 2.0 & Bridge Entegrasyonu):** `hapticSelection`, `hapticImpact`, `hapticSuccess` fonksiyonları, React Native `MishilUnifiedWebView.tsx` haptik handler genişletmesi, TypeScript ve Jest testleri.
* **Antigravity Şeridi (Gece Beşiği UI, Orkestrasyon & Sürüm Yönetimi):** `#night-ambient-overlay` DOM elemanı, header butonu, offline paket derlemesi (`bundle:offline`), DOM audit (`audit_app_html.py`) ve versiyonlama (`4.44.0`).

---

## 📋 3. Yapılacak İşler ve İcra Adımları

### Adım 1: Haptics 2.0 & React Native Köprüsü (`MishilUnifiedWebView.tsx` & `app.html`)
- [ ] `MishilUnifiedWebView.tsx` içindeki `triggerHaptic` fonksiyonuna `selection` (`Haptics.selectionAsync()`) ve `success` (`Haptics.notificationAsync()`) desteği ekleme.
- [ ] `app.html` içinde `hapticSelection()`, `hapticImpact()` ve `hapticSuccess()` fonksiyonlarını tanımlama.

### Adım 2: Akustik Crossfade Motoru (`app.html`)
- [ ] `togglePlayTrack` içine parça değişimlerinde 0.8 saniyelik yumuşak ses fade-in/fade-out mekanizmasını entegre etme.

### Adım 3: Gece Beşiği Modu (Melatonin Ambient Screen Saver — `app.html`)
- [ ] `#night-ambient-overlay` tam ekran loş gece ekranı HTML ve CSS stillerini ekleme.
- [ ] Ana başlığa (`.app-header`) tek dokunuşluk 🌙 Gece Lambası butonu yerleştirme.
- [ ] `openNightAmbient()` ve `closeNightAmbient()` kontrol fonksiyonlarını bağlama.

### Adım 4: Doğrulama ve Test Kapısı
- [ ] `npm run bundle:offline` ile `offlineHtml.generated.ts` dosyasını derleme.
- [ ] `npx tsc --noEmit -p tsconfig.json` ile tip denetimi.
- [ ] `node node_modules/jest/bin/jest.js` ile birim testleri (10/10 PASS).
- [ ] `python scratch/audit_app_html.py` ile DOM ID ve onclick bütünlük taraması.
- [ ] Versiyon güncelleme (`APP_VERSION = 4.44.0`, `BUILD_NUMBER = 62`).

---

## 🛡️ 4. Risk Seviyesi & Kademeli Doğrulama Kapısı (Tiered Review Gate)
* **Risk Seviyesi:** **Seviye 2 (Orta Risk - Dual Check)**.
* **Denetim Odağı:** React Native WebView köprüsünde haptik mesajlarının çökme üretmemesi, Web Audio ve HTML Audio'da crossfade'in bellek sızıntısı yapmaması.
* **Onay Şartı:** Kod yazımına başlamadan önce bu planın kullanıcı tarafından onaylanması zorunludur.

---

## ⚠️ 5. Kısıtlar ve Önleyici Tedbirler
- **Kesin Yerel Öncelik:** Tüm geliştirmeler yalnızca yerel test ortamında koşturulacak; kullanıcıdan yazılı canlıya alma onayı gelmedikçe `git push` yapılmayacaktır.
- **Native Build Kısıtlaması:** Webview ve köprü katmanında kalındığı için native EAS derlemesi tetiklenmeyecektir.
