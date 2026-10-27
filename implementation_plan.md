# 📐 Implementation Plan: Işıl & Mışıl Çizgi Roman Serisi (Post 02: 4. Ay Fırtınası)

### 📊 Üst Gösterge Alanı:
* **Tahmini Efor:** Orta (1.5 - 2 saat)
* **Kalan Kapasite (Context / Turn Kullanımı):** Yaklaşık %12 - %15

---

## 🎯 Kullanıcı İstek Analizi & Netleştirilmiş Kapsam (Prompt Refinement & Expansion)

* **🎯 Netleştirilmiş Hedef & Kapsam:**
  - Kullanıcı Post 01'i Instagram'da başarıyla paylaştı. İki kritik tasarım geri bildirimi verdi:
    1. *"Bir sonrakinde daha az boşluklu yapalım"* (Fazla negatif boşluklardan arındırılmış, dolu dolu ve zengin görsel kompozisyon).
    2. *"Çizgi roman serisi gibi olsun istiyorum"* (Resimli masal kitabından dinamik **Instagram Çizgi Roman Serisi / Webcomic Episode** formatına geçiş).
  - Bu doğrultuda **Bölüm 2 (Post 02)**: *"Işıl & Mışıl'ın Uyku Maceraları • Sayı #2: Büyülü 4. Ay Fırtınası (4. Ay Uyku Gerilemesi ve Çözüm Haritası)"* temasıyla; klasik çizgi roman kapak masthead'i, anlatıcı kutuları (*"Saat 03:15... Işıl Anne'nin yatak odası"*), dinamik çizgi roman panelleri, ses efekti balonları (*"ESNEEE!", "Zzzz...", "PIŞŞŞ!"*), çizgi roman konuşma kuyrukları ve dolgun bento panel mimarisiyle 6 slaytlık 1:1 kare (1080x1080) karusel olarak üretilecektir.

* **🏎️ 3 Ajanlı Görev Dağılımı (Tri-Agent Roles):**
  - **Antigravity Şeridi (Tasarım & Orkestrasyon):** Çizgi roman görsel panel mimarisini, CSS grid panel motorunu, masthead/sayı rozetlerini, interaktif önizleme panelini ve Instagram metin/DM kurgusunu tasarlar.
  - **Codex Şeridi (Hızlı Kodlama & Render Motoru):** `projects/mishil/scripts/render_instagram_comic_02.py` betiğini sıfır boşluklu, tam dolgulu çizgi roman panelleri ve Playwright otomasyonu ile optimize eder.
  - **Claude Şeridi (Pediatrik Hikaye & İletişim Mantığı):** 4. ay gerilemesi biyolojik evrelerini çizgi roman diyaloglarına (Işıl vs Mışıl empati akışına) dönüştürür.

* **🛡️ Risk Seviyesi & Kademeli Doğrulama:**
  - **Seviye 1 (Düşük Risk / Tasarım & Pazarlama Varlıkları):** Kodlama yalnızca pazarlama scriptleri ve CSS panel şablonundadır. Mobil native derleme gerekmez (🟢 Yeşil: Build Gerekmez).

* **⚠️ Kısıtlar ve Önleyici Tedbirler:**
  - **Daha Az Boşluk Kuralı:** Atıl siyah/koyu boşluklar kaldırılacak; karakterler daha büyük (160-200px), paneller ekranın %90'ını dolduracak, çizgi roman çıkartmaları ve anlatıcı kutuları boşlukları dinamik olarak dolduracak.
  - **1:1 Profil Izgara Hizası:** 1080x1080 px kare korunarak profilde kırpılma önlenecek.
  - **Tek Kaynak Hafızası:** Çizgi roman serisi kuralları `INSTAGRAM_BUYUME_HAFIZASI.md` içine işlenecek.
  - **Canlıya Alma Kapısı:** Yerel render ve test sonrası kullanıcı onayı alınmadan canlı dağıtım yapılmayacak.

---

## 🎨 Çizgi Roman Serisi Görsel & Panel Mimarisi (Comic Style Guide)

### 1. Çizgi Roman Kapak Başlığı (Masthead)
* Üstte retro/modern çizgi roman künyesi:
  `⚡ MIŞIL COMICS • SAYI: #2 • HER PAZARTESİ YENİ BÖLÜM ⚡`
* Kapak Başlığı: **"Büyülü 4. Ay Fırtınası!"** / *"Her Şey Harika Giderken Gece Neden Çığlıklarla Bölündü?"*
* Çizgi Roman Kapağı: Odasında şaşkınlıkla telefona bakan Işıl Anne + tulumunun tavşan kulaklarını kaşıyan sevimli Mışıl Bebek.

### 2. Çizgi Roman Panel Düzeni (Sıfır Boşluk - Dense Comic Panels)
* **Sarı/Krem Anlatıcı Kutuları (Narration Boxes):**
  Sol üst köşede çizgi romanlara özgü dikdörtgen parşömen kutusu:
  `📍 SAAT 02:40 • IŞIL ANNE'NİN ODASI` veya `📍 O SIRADA MIŞIL'IN BEYNİNDE...`
* **Dinamik Çizgi Roman Konuşma Balonları (Comic Bubbles):**
  Koyu 3px siyah/arduvaz konturlu beyaz/krem dolgulu puf balonlar; karakterin ağzına doğru incelen keskin çizgi roman kuyrukları.
* **Ses Efektleri & Çıkartmalar (Comic SFX & Stickers):**
  `💥 ESNEME KRİZİ!` • `⚡ KORTİZOL ALARMI!` • `🎵 PIŞ PIŞ PIŞ!` • `💤 DERİN UYKU DÖNGÜSÜ!`
* **İkili / Üçlü Panel Akışı (Multi-Panel Strip):**
  Her slaytta tek bir düz metin yerine; üstte *"Problem Anı"* (Işıl Anne paneli), ortada devasa metrik/reaksiyon, altta *"Mışıl'ın Biyolojik Sırrı ve Çözüm"* paneli. Çerçeve dopdolu, eğlenceli ve akıcı!

---

## 📋 6 Slaytlık Çizgi Roman Bölüm Planı (Bölüm 2: 4. Ay Fırtınası)

1. **Slayt 1 (Kapak):** *MIŞIL COMICS #2: Büyülü 4. Ay Fırtınası! (Ne Oldu Bu Bebeğe?!)*
2. **Slayt 2 (Kriz Anı):** *Panel 1: "3. ayda 5 saat uyuyan bebek gitti, 45 dakikada bir uyanan alarm geldi!"* Anlatıcı: *Beyindeki gizli devrim başladı!*
3. **Slayt 3 (Biyolojik Sır):** *Mışıl'ın Rüyalar Dünyası:* 45 dakikalık yetişkin uyku evrelerine geçiş şeması.
4. **Slayt 4 (Yanlış Hamle):** *"Her mıkırdanmada kucağa almak neden uyku döngüsünü kilitler?"*
5. **Slayt 5 (Süper Güç / Çözüm):** *Işıl Anne Mışıl Baby'nin Akustik Kalkanını Devreye Sokuyor! (Anne Karnı & Beyaz Gürültü)*
6. **Slayt 6 (Zafer & Özet):** *Çizgi Roman Kurtuluş Tablosu & Yoruma "FIRTINA" yazana 4. Ay Hayatta Kalma Rehberi DM!*

---

## 🚦 İcra Adımları & Onay Kapısı
1. **Adım 1:** Çizgi roman panel render motorunun (`render_instagram_comic_02.py`) hazırlanması.
2. **Adım 2:** 6 slaytlık çizgi roman karuselinin 1080x1080 Ultra HD render edilmesi.
3. **Adım 3:** İnteraktif önizleme sayfasına `preview_instagram_concepts.html` "Çizgi Roman Bölüm 2" sekmesinin eklenmesi.
4. **Adım 4:** Paylaşım metni (caption), sabit yorum ve "FIRTINA" DM otomasyonunun hazırlanması.
5. **Adım 5:** Kullanıcı incelemesine sunulması.
