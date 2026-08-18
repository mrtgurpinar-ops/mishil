# Mishil: Baby Sleep & Routines Backend

**Mishil**, 0-36 ay arası bebekler için dinamik uyku penceresi (wake window) hesaplayan, Librosa destekli ağlama sesi heuristik öznitelik analizi (MFCC, ZCR, Spectral Centroid) gerçekleştiren, rutin takibi (beslenme, bez, uyku) sunan ve RevenueCat uyumlu abonelik yönetimi sağlayan production-ready bir mobil backend servisidir.

---

## 🌟 Öne Çıkan Özellikler
1. **Dinamik Wake Window Algoritması:**
   - 0-36 ay arası ay bazlı adaptif uyanıklık penceresi hesabı.
   - Önceki uykunun <30 dk olması durumunda aşırı yorgunluk (overtired) uyarısı ve %15 pencere daraltması.
   - Yaşa göre günlük toplam uyku bütçesi ve günün kalan nap planı projeksiyonu.
2. **Ağlama Sesi Heuristik Analizi:**
   - Librosa ile MFCC (13 katsayı), Zero-Crossing Rate (ZCR) ve Spectral Centroid çıkarımı.
   - Kesin teşhis iddiasından kaçınan olasılık dağılımı çıktısı (`possible_causes`: hungry, tired, pain/colic, discomfort).
   - Önerilen rahatlatıcı ses (örn. `pink_noise_432hz`, `womb_sounds`) ve ebeveyn aksiyonu.
3. **Mobil Rutin Takibi:**
   - Beslenme, alt değiştirme, uyku ve ruh hali kayıtları (CRUD).
4. **Gelir & Abonelik Modeli:**
   - 3 günlük deneme sürümü (trial) başlatma ve durum sorgulama.
   - RevenueCat Webhook imza doğrulama ve durum senkronizasyon iskeleti.
5. **Güvenlik & Mimari:**
   - JWT tabanlı mobil kimlik doğrulama.
   - Global RFC 7807 hata yönetimi ve `X-Request-ID` ile yapılandırılmış JSON loglama.

---

## 🚀 Hızlı Başlangıç

### 1. Yerel Geliştirme (Python)
```bash
# Sanal ortam oluşturup aktif edin
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Bağımlılıkları yükleyin
pip install -r requirements.txt

# Ortam değişkenlerini kopyalayın
cp .env.example .env

# Uygulamayı başlatın
python app/main.py
```
API Dokümantasyonu (Swagger UI): `http://localhost:8000/docs`

---

### 2. Docker Compose ile Başlatma (Production-Ready)
Tek komutla hem PostgreSQL hem de Mishil API konteynerini ayağa kaldırın:
```bash
docker compose up -d --build
```
Logları takip etmek için:
```bash
docker compose logs -f mishil-api
```
Servisleri durdurmak için:
```bash
docker compose down
```

---

## 🧪 Testleri Çalıştırma
```bash
pytest tests/ -v
```
