# Implementation Plan - Mışıl Baby Web Sitesi Google Play Bağlantısı Güncellemesi

**Tahmini Efor:** ~10-15 Dakika  
**Tahmini Kapasite Kullanımı:** %2 - %3

---

### 1. Ajan Uzmanlık Şeritleri ve Görev Dağılımı (Tri-Agent Roles)
- **Claude Şeridi:** (Bu görevde mimari/backend değişikliği bulunmamaktadır).
- **Codex Şeridi:** Değiştirilen HTML dosyalarında sözdizimi doğrulaması ve regex/lint kontrolü.
- **Antigravity Şeridi (Birincil İcra):**
  - Web landing page (`projects/mishil/public/index.html`) üzerindeki "Çok Yakında" ibaresinin "Hemen İndirin" olarak güncellenmesi ve canlı Google Play linkinin eklenmesi.
  - Açılır modal penceresine (`#appModal`) Google Play butonu eklenmesi.
  - Web önizleme dosyasının (`projects/mishil/mobile/web-preview/index.html`) senkronize edilmesi.
  - Mobil webview (`projects/mishil/public/app.html`) mağaza değerlendirme ucu (`submitStoreRating`) ve koruma ekranındaki (`guard-store-btn`) Google Play paket id'sinin `com.levitas.misilbaby` olarak güncellenmesi.
  - Offline bundle senkronizasyonu (`offlineHtml.generated.ts`).

---

### 2. Aktarım ve İcra Yöntemi (Execution Strategy)
- Değişiklikler Antigravity tarafından yerel ortamda doğrudan uygulanacaktır.
- Doğrulama yerel test kapılarıyla (`offlineHtml` bundle ve node syntax denetimi) yürütülecektir.

---

### 3. Kademeli Çapraz Doğrulama Kapısı (Tiered Review Gate)
- **Risk Seviyesi:** **Seviye 1 (Düşük Risk / Rutin UI & Link Güncellemesi - Fast Lane)**
- Harici CLI kotası harcanmadan, yerel node kontrolleri ve offline bundle derlemesi ile doğrulanacaktır.

---

### 4. Limit/Kota Aşımı Durum Planı (Fallback Protocol)
- Rutin frontend düzenlemesi olduğu için harici kota riski bulunmamaktadır.

---

## Yapılacak İşler Listesi (Proposed Changes)

#### [projects/mishil/public/index.html](file:///c:/Users/MSI-NB/OneDrive/Desktop/antigravity_core/projects/mishil/public/index.html)
- `cta-group` içindeki Google Play butonunu güncelle:
  - Eski: `onclick="showAppPrompt('Google Play')"` + `<small>Çok Yakında</small>`
  - Yeni: `href="https://play.google.com/store/apps/details?id=com.levitas.misilbaby"` + `target="_blank"` + `<small>Hemen İndirin</small>` + `class="store-btn primary"`
- `modal` penceresi içerisine App Store butonunun altına doğrudan Google Play indirme bağlantısı ekle.

#### [projects/mishil/mobile/web-preview/index.html](file:///c:/Users/MSI-NB/OneDrive/Desktop/antigravity_core/projects/mishil/mobile/web-preview/index.html)
- Google Play butonu ve modal yapısını `public/index.html` ile senkronize et.

#### [projects/mishil/public/app.html](file:///c:/Users/MSI-NB/OneDrive/Desktop/antigravity_core/projects/mishil/public/app.html) & [projects/mishil/mobile/features/webview/offlineHtml.generated.ts](file:///c:/Users/MSI-NB/OneDrive/Desktop/antigravity_core/projects/mishil/mobile/features/webview/offlineHtml.generated.ts)
- `submitStoreRating()` fonksiyonundaki mağaza URL'sini `com.levitas.misilbaby` yap.
- Koruma ekranı (`guard-store-btn`) Google Play buton linkini güncelle.
- `npm run bundle:offline` komutuyla çevrimdışı HTML dosyasını güncelle.

---

## Doğrulama Planı (Verification Plan)

### Otomatik & Yerel Testler
1. HTML syntax denetimi (`node --check`).
2. `npm run bundle:offline` derlemesinin yeşil tamamlanması.
3. Yerel tarayıcıda buton linklerinin ve yönlendirmelerinin gözle test edilmesi.
