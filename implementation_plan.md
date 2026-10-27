# Implementation Plan - Mışıl Baby Evrensel Akıllı Mağaza Köprüsü (Universal Smart Store Bridge)

**Tahmini Efor:** ~10-15 Dakika  
**Tahmini Kapasite Kullanımı:** %2 - %3

---

### 1. Ajan Uzmanlık Şeritleri ve Görev Dağılımı (Tri-Agent Roles)
- **Claude Şeridi:** Backend mimari kontrolü (`app/main.py` routing & User-Agent regex ayrıştırması).
- **Codex Şeridi:** Python sözdizimi, birim testleri ve User-Agent simülasyon testleri.
- **Antigravity Şeridi (Birincil İcra):**
  - `projects/mishil/app/main.py` dosyasındaki `/ios`, `/download`, `/app-store` (ve yeni `/android`) uç noktalarının güncellenmesi.
  - Cihaz tespiti ile hem Python seviyesinde hem istemci JS seviyesinde dinamik yönlendirme (`Google Play` vs `App Store`).
  - Meta/Crawler bot korumasının (`_BOT_USER_AGENTS`) eksiksiz muhafaza edilmesi.
  - Sürüm ve Changelog senkronizasyonu (`projects/mishil/CHANGELOG.md`, `CHANGELOG.md`, `MASTER_DOCUMENT.md`).

---

### 2. Aktarım ve İcra Yöntemi (Execution Strategy)
- Düzenleme yerel ortamda `projects/mishil/app/main.py` üzerinde yapılacak.
- Python ile simüle edilmiş User-Agent testleri (Android, iPhone, Facebook Bot, Desktop) koşturulacak.

---

### 3. Kademeli Çapraz Doğrulama Kapısı (Tiered Review Gate)
- **Risk Seviyesi:** **Seviye 2 (Orta Risk / Standart Modül - Dual Check)**
- Backend endpoint davranışı yerel python mock istekleriyle hem Android hem iOS hem Bot senaryolarında test edilecek.

---

### 4. Limit/Kota Aşımı Durum Planı (Fallback Protocol)
- Değişiklik yerel FastAPI katmanında yürütülecektir; harici CLI kotası harcanmaz.

---

## Yapılacak İşler Listesi (Proposed Changes)

#### [projects/mishil/app/main.py](file:///c:/Users/MSI-NB/OneDrive/Desktop/antigravity_core/projects/mishil/app/main.py)
- `GOOGLE_PLAY_URL` ve `APP_STORE_URL` sabitlerini tanımla:
  - `GOOGLE_PLAY_URL = "https://play.google.com/store/apps/details?id=com.levitas.misilbaby"`
  - `APP_STORE_URL = "https://apps.apple.com/app/m%C4%B1%C5%9F%C4%B1l-baby-bebek-uyku-ve-a%C4%9Flama/id6809223195"`
- `smart_app_store_bridge` fonksiyonunu güncelle:
  - Meta / arama motoru botları için: `public/index.html` (200 OK) dönmeye devam et.
  - Android cihazlar için (`"android" in user_agent`):
    - Başlık: `Mışıl Baby — Google Play'de Açılıyor...`
    - Buton: `🤖 Google Play'de Aç`
    - Yönlendirme JS: `GOOGLE_PLAY_URL`
  - iOS / Apple cihazlar için (`"iphone" in user_agent or "ipad" in user_agent or "ipod" in user_agent`):
    - Başlık: `Mışıl Baby — App Store'da Açılıyor...`
    - Buton: `🍏 App Store'da Aç`
    - Yönlendirme JS: `APP_STORE_URL`
  - Masaüstü / Diğer cihazlar için:
    - İki butonu yan yana sun ve ana sayfaya yönlendir.
- Endpoint decorator listesine `@app.get("/android", ...)` ekle.

---

## Doğrulama Planı (Verification Plan)

### Otomatik & Yerel Testler
1. `python -m py_compile app/main.py` sözdizimi denetimi.
2. Yerel Python test scripti:
   - Android User-Agent simülasyonu -> `play.google.com` çıktısı.
   - iPhone User-Agent simülasyonu -> `apps.apple.com` çıktısı.
   - Facebook Bot User-Agent simülasyonu -> `public/index.html` içeriği.
3. Submodule ve ana repo commit/push senkronizasyonu.
4. Canlı Railway endpoint testi.
