# Mishil Mobile: Baby Sleep & Routines (React Native & Expo)

**Mishil Mobile**, ebeveynlere yönelik gece görüşüne ve duyusal regülasyona duyarlı, Expo Router, TypeScript ve Reanimated ile inşa edilmiş modern bir mobil istemcidir.

---

## 🌙 Tasarım ve İmza Deneyimi
- **Renk Dünyası:**
  - Koyu Mod (Varsayılan): Zemin `#141B2E`, Metin `#C9CEDC`, Kartlar `#1D2640`.
  - Açık Mod: Zemin `#F7F5F1`, Metin `#2A2E3D`, Kartlar `#FFFFFF`.
  - Tekil Sıcak Vurgu (Accent): `#E8A855` (Bal/Amber) — Yalnızca CTA ve uyku vaktine yakın göstergelerde kullanılır.
- **İmza Elemanı (`BreathingMoonIndicator`):**
  - ~4 saniyelik pürüzsüz nefes alma/verme ritmiyle atan hilal ikonu.
  - Sıradaki uyku vaktine yaklaşıldıkça hafif kehribar tonuna evrilir.
  - `AccessibilityInfo.isReduceMotionEnabled` açık olduğunda otomatik olarak statik zarif hilal görseline geçer.
- **Kesintisiz Ses Çalar:** `expo-av` ile arka planda (`UIBackgroundModes: ['audio']`) ekran kapalıyken bile 432Hz pembe gürültü ve pışpışlama sesini kesintisiz çalar.
- **Offline-First Rutin Kaydı:** İnternet yokken eklenen beslenme/bez logları yerel kuyruğa yazılır, internet geldiğinde FastAPI backend ile otomatik eşitlenir.

---

## 🚀 Kurulum ve Başlatma

### 1. Bağımlılıkları Yükleyin
```bash
cd antigravity_core/projects/mishil/mobile
npm install
```

### 2. Ortam Değişkenlerini Tanımlayın
```bash
cp .env.example .env
```

### 3. Expo Uygulamasını Başlatın
```bash
npx expo start
```
- **iOS Simülatör:** `i` tuşuna basın.
- **Android Emülatör:** `a` tuşuna basın.
- **Web Önizleme:** `w` tuşuna basın.

### 4. İmza Hilal Önizleme Ekranı (Storybook / Preview Mode)
Nefes alan ay animasyonunu izole olarak incelemek için Expo Router rotası:
👉 `/(preview)/moon-preview`

---

## 🧪 Testleri Çalıştırma
```bash
npm test
```
