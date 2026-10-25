# Implementation Plan: Mışıl Baby Yeni Native Derleme (v4.39.0 / Build 57)

- **Tahmini Efor:** ~15-20 Dakika (Pre-flight testler + EAS Cloud Build)
- **Kapasite Kullanımı:** Kalan turn/bağlam limitinin yaklaşık %8-10'u

---

## 1. Netleştirilmiş Hedef ve Kapsam (Refined Scope)
18 Ekim'de yayınlanan mevcut mağaza sürümümüz **Build 56 (v4.37.0)** üzerinde çalışmaktadır. O tarihten bu yana kod tabanına eklenen kritik native yetenekler (Aşı/Uyku Bildirim Motoru - `CareNotificationEngine`, App Store 5-Yıldız Anne Dayanışması Çarkı ve güncellenmiş çevrimdışı çekirdek) henüz native EAS derlemesine dönüştürülmemiştir. Bu planla:
- `BUILD_NUMBER` değeri **56'dan 57'ye** artırılacak.
- `public/app.html` içeriği en güncel haliyle `offlineHtml.generated.ts` içine paketlenecek.
- Pre-flight doğrulama kapısı (TypeScript, Jest, Mobile Compliance Checker) çalıştırılacak.
- Kullanıcı onayıyla yeni production derlemesi başlatılacaktır.

---

## 2. 3 Ajanlı Görev Dağılımı (Tri-Agent Protocol)
- **Antigravity Şeridi (Orkestrasyon & Dağıtım):**
  - `projects/mishil/mobile/app.config.ts` içerisinde `BUILD_NUMBER: 57` güncellemesi.
  - EAS Build CLI üzerinden derlemenin başlatılması (`eas build --platform ios --profile production`).
  - Süreç takibi ve build URL'sinin raporlanması.
- **Claude Şeridi (Tip & Mimari Bütünlük):**
  - `npx tsc --noEmit -p tsconfig.json` ile Expo 54 ve React Native 0.81 tip güvenliği doğrulaması.
- **Codex Şeridi (Test & Pre-Flight Uyumluluk):**
  - `npm run bundle:offline` ile offline bundle senkronizasyonu.
  - `node node_modules/jest/bin/jest.js` ile birim testlerinin koşulması.
  - `core/mobile_compliance_checker.py` ile Google Play / App Store regülasyon denetimi.

---

## 3. Kademeli Doğrulama Kapısı (Tiered Review Gate: Seviye 2 - Standart Derleme)
1. **Yerel Sentaks & Tip Kontrolü:** `tsc` hatasız tamamlanmalı.
2. **Offline HTML Senkronizasyonu:** `features/webview/offlineHtml.generated.ts` dosyasının en güncel `app.html` ile senkron olduğu doğrulanmalı.
3. **Mağaza Uyumluluk Denetimi:** Target SDK 36, RevenueCat API Key kontrolü ve ATS / Background audio izinleri yeşil olmalı.
4. **Kullanıcı İcra Onayı:** EAS Build komutu çalıştırılmadan önce platform tercihi (Sadece iOS mu, yoksa iOS + Android mi) kullanıcıya sunulacaktır.

---

## 4. İcra Adımları
1. **Adım 1:** `projects/mishil/mobile/app.config.ts` -> `BUILD_NUMBER = 57` yapılması.
2. **Adım 2:** `npm run bundle:offline` çalıştırılarak offline bundle'ın güncellenmesi.
3. **Adım 3:** `npx tsc --noEmit` ve `jest` testlerinin çalıştırılması.
4. **Adım 4:** `python core/mobile_compliance_checker.py projects/mishil/mobile` pre-flight denetimi.
5. **Adım 5:** Kullanıcı onayıyla EAS derlemesinin tetiklenmesi:
   - Seçenek A: `npx eas-cli build --platform ios --profile production`
   - Seçenek B: `npx eas-cli build --platform all --profile production`
