# 📜 Uygulama Planı: Işıl & Mışıl ile "Masalsı Uyku Pencereleri" Karuseli

> **Üst Göstergeler:**  
> ⏱️ **Tahmini Efor:** ~15 Dakika  
> 🔋 **Kapasite & Token Kullanımı:** Kalan oturumun yaklaşık **%4**'ü  
> 🛡️ **Risk & İnceleme Seviyesi:** Seviye 1 (Fast Lane / İçerik & Görsel Motoru)

---

## 🎯 Netleştirilmiş Hedef & Kapsam
Onaylanan resmi karakterlerimiz **Işıl Anne (Papatyalı Bandana)** ve **Mışıl Bebek (Tavşan Kulaklı Tulum)** merkezinde; kuru bir tıbbi tablo yerine **çocuk masalı tadında anlatılan**, ancak her slaytında annelere hayat kurtarıcı pediatrik uyku penceresi tüyoları veren **6 slaytlık 1:1 Kare (1080x1080 px)** gönderi seti üretmek.

---

## 🏎️ Tri-Agent Görev Dağılımı
* **Claude (Anlatı & Metin Mimarisi):** Masal tonunda diyalog kurgusu (*"Bir Varmış Bir Yokmuş..."*), anne-bebek şefkat bağı ve bilimsel verilerin masal içine organik yedirilmesi.
* **Codex (1:1 Görsel Render Motoru):** Playwright motorunu güncelleyip onaylanan karakter görselleri (`isil_3_ve_misil_2_birlikte_master.jpg`, `misil_2_rotus_a_gozler_acik.jpg`, `misil_2_rotus_b_esneyen.jpg`), Nordic Pastel zemin ve dev masalsı tipografiyle Ultra HD PNG çıktısı almak.
* **Antigravity (Orkestrasyon & Yerel Önizleme):** Sol paneldeki interaktif inceleme sayfasını güncellemek, hafıza dokümanlarını senkronize etmek ve kullanıcı onayına sunmak.

---

## 📖 6 Slaytlık Masal Kurgusu & Pediatrik İçerik

### 🌙 Slayt 1 (Kapak): *"Bir Varmış, Bir Yokmuş... Uykusuz Bir Gece Varmış"*
* **Görsel:** `isil_3_ve_misil_2_birlikte_master.jpg` (Işıl Anne kucağında tavşan tulumlu Mışıl ile)
* **Masal Metni:**  
  *"Işıl Anne saatlerdir kucağında tavşan tulumlu Mışıl'ı pışpışlıyordu. Mışıl esniyor ama uyuyamıyordu. Işıl 'Nerede hata yapıyorum?' diye fısıldadı. Ta ki Mışıl dile gelene kadar..."*
* **Kanca:** *"Sola kaydırın, Mışıl'ın uyku masalını dinleyin 👉"*

### ⏰ Slayt 2 (0-3 Ay): *"1. Masal: 45 Dakikalık Kum Saati"*
* **Görsel:** `misil_2_rotus_a_gozler_acik.jpg` (Mışıl Bebek pırıl pırıl gözleriyle anlatıyor)
* **Masal Metni:**  
  *"- Annecim, benim uyanıklık kum saatim sadece 45-60 dakikalık! Bu süre bittiğinde beynim kortizol alarmı çalar, istesem de dalamam. Gözlerimi ilk ovuşturduğum an beni yatağa al..."*
* **Bilgi Rozeti:** ⏳ **0 — 3 AY: 45 — 60 DAKİKA**

### 🌸 Slayt 3 (4-6 Ay): *"2. Masal: Büyülü 4. Ay Fırtınası"*
* **Görsel:** `misil_2_rotus_b_esneyen.jpg` (Mışıl Bebek bulutta tatlı tatlı esniyor)
* **Masal Metni:**  
  *"- Annecim, 4. ayda rüyalarım yetişkinler gibi olgunlaştı! Her 45 dakikada bir uyanıyorum. Beni sallamak yerine Mışıl Baby ninni melodisiyle döngüme geri bağla..."*
* **Bilgi Rozeti:** ⏳ **4 — 6 AY: 1.5 — 2.5 SAAT**

### 🧸 Slayt 4 (7-9 Ay): *"3. Masal: Küçük Kaşifin Uyku Savaşı"*
* **Görsel:** Mışıl'ın keşif ve oyun hali
* **Masal Metni:**  
  *"- Artık emekliyorum, dünyayı keşfetmek çok eğlenceli! Yorgunluktan bitsem de uykuya direniyorum. Uykudan 20 dakika önce ışıkları kısarsan kucağına teslim olurum..."*
* **Bilgi Rozeti:** ⏳ **7 — 9 AY: 2.5 — 3.5 SAAT**

### 🌙 Slayt 5 (10-12 Ay): *"4. Masal: Gece Nöbetinin Büyük Sırrı"*
* **Görsel:** Işıl Anne'nin gece lambası ve Mışıl'ın uykuya geçişi
* **Masal Metni:**  
  *"- Gece uykusundan önceki son pencerem günün en uzunu. Beni çok erken yatırırsan gece 03:00'te uyanırım. Kehribar ışıkla melatoninimi çağır..."*
* **Bilgi Rozeti:** ⏳ **10 — 12 AY: 3 — 4 SAAT**

### ✨ Slayt 6 (Kapanış & Mutlu Son): *"Ve Mışıl Mışıl Uyudular... 💤"*
* **Görsel:** İkili huzur içinde uyurken
* **Masal Metni:**  
  *"Işıl Anne doğru pencereleri öğrendi, ninniyi açtı ve Mışıl mışıl daldılar. Tüm anneler bu gece deliksiz uyusun diye masalımızın tablosunu hazırladık."*
* **Hediye / DM Çağrısı:**  
  *"Yoruma **'MASAL'** yazın; 0-12 Ay Masalsı Uyku Cetveli'ni DM'den anında ücretsiz gönderelim! 💌"*

---

## 🛠️ İcra Adımları
1. `projects/mishil/scripts/render_instagram_carousel_01.py` dosyasını bu masalsı şablon ve yeni karakter görselleriyle güncellemek.
2. Playwright motoru ile 6 slaytlık Ultra HD PNG setini (`post_01_slaytlar/`) üretmek.
3. Sol paneldeki interaktif inceleme dosyasını güncelleyerek kullanıcının canlı test etmesini sağlamak.
