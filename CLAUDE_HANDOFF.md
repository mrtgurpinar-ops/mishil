# Claude Devir Teslim (CLAUDE_HANDOFF.md) — Mışıl Baby v4.10.2

> **Protokol:** `AGENTS.md §1 & §7` uyarınca Antigravity ➔ Claude Code devir teslim belgesidir.  
> **Kapsam:** Claude Code YALNIZCA aşağıdaki 7 adımı sırasıyla uygulayacak, başka hiçbir dosyayı veya şeridi değiştirmeyecektir.  
> **Tarih:** 2026-09-08  

---

## 🛑 Kesin Sınırlar & Altın Kurallar (Claude Code İçin)
1. **Push Kesinlikle Yok:** `git push` komutu çalıştırma (`AGENTS.md §2.4`). Yalnızca yerel commit at.
2. **Bebek Verisi Dokunulmazdır:** `localStorage` içindeki `mishil_baby_name`, `mishil_baby_bdate` vb. kayıtları ASLA silme veya sıfırlama.
3. **Şerit Dışına Çıkma:** Sadece aşağıda numaralandırılmış 3 dosyayı düzenle.

---

## 📋 SIRALI UYGULAMA ADIMLARI (Strict Sequential Steps)

### 🔹 ADIM 1: Backend Önbellek Kilidini Ekle
* **Dosya:** `projects/mishil/app/main.py`
* **Yapılacak İş:** `/app` ve `/preview` endpoint'lerindeki `HTMLResponse` yanıtına şu başlıkları ekle:
  ```python
  headers = {
      "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
      "Pragma": "no-cache",
      "Expires": "0",
  }
  ```
* **Amaç:** Telefonların diske eski HTML önbelleği kaydetmesini engellemek; her zaman Railway'deki canlı kodu çekmesini sağlamak.

---

### 🔹 ADIM 2: Bebek Profilini Onboarding'den Ayır & %100 Kalıcı Yap
* **Dosya:** `projects/mishil/public/app.html`
* **Yapılacak İş:**
  1. `checkOnboardingStatus()` fonksiyonunu incele ve revize et: Eğer `mishil_baby_name` ve `mishil_baby_bdate` kayıtlıysa, `#screen-onboarding` ekranı **kesinlikle açılmasın**, doğrudan ana ekrana geçilsin.
  2. Kullanıcı bebeğinin adını ve doğum tarihini bir kez girdiyse bu veriler kalıcıdır; hiçbir hata veya durum bu verileri sıfırlamamalıdır.

---

### 🔹 ADIM 3: Bağımsız VIP Yenileme Modalı Ekle (`#vip-renewal-modal`)
* **Dosya:** `projects/mishil/public/app.html`
* **Yapılacak İş:**
  1. HTML içine onboarding anketinden tamamen bağımsız `#vip-renewal-modal` ekle.
  2. Modal içeriği:
     - Başlık: `👑 [Bebek Adı] için Mışıl VIP Aboneliğinizi Yenileyin` (Bebek adı dinamik okunur).
     - Açıklama: Sirkadiyen uyku pencereleri, Mışıl Dadı AI Koçu ve 18 stüdyo sesine kesintisiz erişim.
     - 3 Paket Kartı: Yıllık VIP (Önerilen), Aylık Pro, Ömür Boyu.
     - Butonlar: "Yenile / Satın Al" (`PURCHASE_PACKAGE`) ve "Satın Alımları Geri Yükle" (`RESTORE_PURCHASES`).
  3. `mishil_subscription_active === 'false'` olduğunda Pro özellikler tıklandığında anket yerine doğrudan bu modal açılsın.

---

### 🔹 ADIM 4: Native Tarafta Canlı Lisans Doğrulaması Yap
* **Dosya:** `projects/mishil/mobile/components/MishilUnifiedWebView.tsx`
* **Yapılacak İş:**
  1. `onLoad` anında ve uygulama ön plana geldiğinde (`AppState.addEventListener('change')`):
     - `Purchases.getCustomerInfo()` çağır.
     - `hasActiveEntitlement(customerInfo)` kontrolü yap.
  2. **Sonuç Aktifse:** WebView'e `localStorage.setItem('mishil_subscription_active', 'true');` enjekte et.
  3. **Sonuç Süresi Dolmuş/İnaktifse:** WebView'e `localStorage.setItem('mishil_subscription_active', 'false');` enjekte et ve Pro özellikleri kilitlet.
  4. **Kritik:** Bebek adını veya verilerini kesinlikle silme!

---

### 🔹 ADIM 5: Çevrimdışı Paketi Yenile
* **Dizin:** `projects/mishil/mobile`
* **Komut:**
  ```bash
  npm run bundle:offline
  ```
* `features/webview/offlineHtml.generated.ts` dosyasının güncellendiğini teyit et.

---

### 🔹 ADIM 6: Doğrulama Kapısından Geç (Tüm Testler Yeşil Olmalı)
* **Dizin:** `projects/mishil/mobile`
* **Komutlar:**
  ```bash
  npx tsc --noEmit -p tsconfig.json          # TypeScript (0 HATA)
  node node_modules/jest/bin/jest.js         # Birim testler (4/4 PASS)
  ```

---

### 🔹 ADIM 7: Yerel Git Commit At (PUSH YOK!)
* **Komut:**
  ```bash
  git -C projects/mishil add CHANGELOG.md app/main.py public/app.html mobile/components/MishilUnifiedWebView.tsx mobile/features/webview/offlineHtml.generated.ts
  git -C projects/mishil commit -m "feat(subscription): persistent baby profile, standalone vip renewal modal and live entitlement sync (v4.10.2)"
  ```
* **Bitiş:** Commit tamamlandıktan sonra oturumunu sonlandır ve Antigravity'ye devret.
