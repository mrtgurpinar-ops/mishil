# Uygulama Planı: Mışıl Baby App Store "5 Yıldız Çarkı" (Smart In-App Rating & Sentiment Gate)

**Tahmini Efor:** ~20-25 Dakika  
**Kapasite Kullanımı:** %2 - %3  
**Risk Seviyesi:** Seviye 1 (Düşük Risk / Rutin İşler - Fast Lane - Tamamen Webview/Frontend Katmanı)  

---

## 🎯 Netleştirilmiş Hedef & Kapsam (Refined Prompt)
* **Hedef Proje:** `projects/mishil` (`public/app.html`, `mobile/features/webview/offlineHtml.generated.ts`)
* **Amaç:** Reklamlardan ve tanıtımlardan gelen annelerin memnuniyet anlarını tespit ederek, olumsuz yorumları içeride filtreleyen ve mutlu kullanıcıları doğrudan **App Store & Google Play "5 Yıldız ve Yorum Yaz"** ekranına yönlendiren akıllı bir itibar ve ASO çarkı kurmak.
* **Kapsam:**
  1. **Zamanlama & Tetikleyici Motoru (Smart Trigger Logic):**
     * İlk açılışta asla çıkmayacak.
     * Kullanıcı en az **2 farklı günde** veya **toplam 20+ dakika** kesintisiz ses/gece lambası seansı tamamladığında (bebeğin uyuduğu kesinleştiğinde) tetiklenecek.
     * `localStorage` üzerinde `misil_rated: true` veya `misil_rate_later: timestamp` ile kullanıcı asla spam yapılmayacak.
  2. **İki Aşamalı Akıllı Filtreleme (Sentiment Gate):**
     * **Aşama 1 (Duygu Yoklaması):** *"Mışıl Baby bu gece miniğinizi sakinleştirmeye yardımcı oldu mu? 🌙"*
       * `[😍 Evet, Harika!]` -> Pozitif Akış
       * `[😕 Biraz Zorlandık]` -> Negatif/İç İyileştirme Akışı
     * **Aşama 2A (Pozitif / 5 Yıldız Akışı):**
       * *"Bunu duyduğumuza çok sevindik! 🤍 Uykusuz diğer annelerin de bizi keşfetmesi için App Store'da 5 yıldızla destek olur musunuz?"*
       * `[⭐ 5 Yıldız Bırak]` butonuna tıklandığında:
         * iOS: `https://apps.apple.com/app/id6809223195?action=write-review`
         * Android: `market://details?id=com.mrtgurpinar.misilbaby`
     * **Aşama 2B (Negatif / Koruma Akışı):**
       * Mağazaya yönlendirilmez! Mağaza puanı korunur.
       * *"Üzüldük! Size ve bebeğinize daha iyi bir deneyim sunabilmemiz için neyi geliştirmeliyiz?"* modalı açılarak geri bildirim doğrudan WhatsApp hattına veya yerel log'a yönlendirilir.
  3. **Tasarım & UI Standartı:**
     * Mışıl Baby'nin sirkadiyen gece mavisi ve altın hilal tasarım diline %100 uyumlu, zarif animasyonlu modal.

---

## 🏎️ 3 Ajanlı Görev Dağılımı (Tri-Agent Protocol)

| Ajan Şeridi | Rol & Sorumluluk | Yapılacak İşler |
| :--- | :--- | :--- |
| **Claude Şeridi** | UX Mantığı & Tetikleyici Algoritması | Oturum sayacı, süre takibi ve duygu filtreleme durum makinesinin (state-machine) hatasız kurgulanması. |
| **Codex Şeridi** | Hızlı Kodlama & Sözdizimi Doğrulama | `app.html` modal bileşeninin ve Store yönlendirme URL fonksiyonlarının kodlanması, `node --check` doğrulaması. |
| **Antigravity Şeridi** | Orkestrasyon, Offline Bundle & Dağıtım | `npm run bundle:offline` ile çevrimdışı derleme, testler ve Railway canlıya alma hazırlığı. |

---

## 🚀 Aktarım ve İcra Yöntemi
* Değişiklik doğrudan `public/app.html` içinde yerel olarak tamamlanacaktır.
* Tamamlandıktan sonra `npm run bundle:offline` ile `offlineHtml.generated.ts` senkronize edilecektir.
* **Native Build Gerekmez (🟢 Yeşil):** Webview katmanında olduğu için native paket gerektirmez, EAS build alınmasına gerek yoktur.

---

## 🛡️ Kademeli Çapraz Doğrulama Kapısı (Tiered Review Gate)
* **Risk Seviyesi:** Seviye 1 (Düşük Risk / Rutin İşler - Fast Lane)
* **Doğrulama Adımları:**
  1. JavaScript syntax check (`node --check`)
  2. Modal açılma/kapanma ve `localStorage` durum testleri
  3. Platform ayrımı (iOS / Android / Web) URL yönlendirme testi
  4. `npm run bundle:offline` çıktısının doğrulanması

---

## ⚠️ Kısıtlar, Önleyici Tedbirler & Fallback
* **Apple Guideline 5.6.1 Uyumu:** Apple kuralları uyarınca kullanıcıya "puan verirse VIP üyelik hediyesi" gibi rüşvet/ödül teklif edilmez (kesin ret sebebidir). Duygu anketi tamamen gönüllü ve doğal bir destek ricası olarak kurgulanmıştır.
* **Kullanıcı Onayı:** Kullanıcı bu planı onaylamadan hiçbir kod değişikliği veya dağıtım yapılmayacaktır.
