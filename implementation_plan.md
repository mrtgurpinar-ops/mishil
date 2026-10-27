# 📐 Implementation Plan: Mışıl Comics #2 — Dengeli Hibrit Çizgi Roman Modeli

### 📊 Üst Gösterge Alanı:
* **Tahmini Efor:** Orta (45 - 60 dk)
* **Kalan Kapasite (Context / Turn Kullanımı):** Yaklaşık %8 - %10

---

## 🎯 Kullanıcı İstek Analizi & Netleştirilmiş Kapsam (Prompt Refinement & Expansion)

* **🎯 Netleştirilmiş Hedef & Kapsam:**
  - Kullanıcının *"bu yazılar telefonda okunmaz küçük kalır"* ve *"bunu ışılla mışıl bir arada kucağında salonda vb yapamıyor muyuz?"* talepleri konsensüs filtresinden geçirildi.
  - Sırf çizim olsun diye 6 slaytın tamamını arka planı kalabalık salon sahneleriyle doldurmak metin okunabilirliğini ve Instagram'da kaydedilme (save) oranını düşüreceği için **"Dengeli Hibrit Çizgi Roman Modeli"** kararlaştırıldı:
    1. **Kapak (Slayt 1) & Zafer (Slayt 6):** Işıl'ın kucağında Mışıl ile salonda koltukta oturduğu tam boy duygusal sahne illüstrasyonu + retro çizgi roman masthead'i + dev başlık/CTA.
    2. **Ara Slaytlar (Slayt 2, 3, 4, 5):** Ekranın bir kısmında Işıl ve Mışıl'ın salondaki gerçek anı (ayakta pışpışlarken, kucakta incelerken, beşik başında); diğer kısmında ise gözü yormayan, kontrastlı, dev puntolu (34-40px) hap bilgi/infografik panelleri (45 dk uyku evresi, sallama tuzağı, anne karnı beyaz gürültü kalkanı).
  - Böylece hem samimi ev/salon hikayesi canlı kalacak, hem de anneler telefondan tek bir kelimeyi bile zorlanmadan okuyup gönderiyi kaydedebilecek.

* **🏎️ 3 Ajanlı Görev Dağılımı (Tri-Agent Roles):**
  - **Antigravity Şeridi (Tasarım & Orkestrasyon):** Kapak/kapanış salon sahnelerini ve ara slayt hibrit bento düzenlerini kurgular; interaktif önizleme panelini (`preview_instagram_concepts.html`) günceller.
  - **Codex Şeridi (Hızlı Kodlama & Render Motoru):** `projects/mishil/scripts/render_instagram_comic_02.py` betiğini hibrit sahne kompozisyonu, devasa 34-40px kontrastlı diyalog balonları ve 1080x1080 Playwright renderı ile günceller.
  - **Claude Şeridi (Pediatrik İçerik & Dil Denetimi):** 4. ay uyku gerilemesi diyaloglarının hem tıbbi doğruluğunu hem de annelerle kurulan sıcak empati dilini denetler.

* **🛡️ Risk Seviyesi & Kademeli Doğrulama:**
  - **Seviye 1 (Düşük Risk / Tasarım & Pazarlama Varlıkları):** Kod değişikliği yalnızca Python pazarlama render betiğindedir. Mobil native derleme gerekmez (🟢 Yeşil: Build Gerekmez).

* **⚠️ Kısıtlar ve Önleyici Tedbirler:**
  - **Devasa Tipografi Güvencesi:** Slaytlardaki ana diyaloglar 34-38px, ara başlıklar 44-52px, notlar 26px altına inmeyecek.
  - **Kontrast Koruması:** Detaylı salon çizimlerinin üzerine metin doğrudan bindirilmeyecek; arkası %100 opak krem/beyaz çizgi roman balonları ve koyu bento panelleri kullanılacak.
  - **Karakter Tutarlılığı:** `isil_3_ve_misil_2_birlikte_master.jpg` ana referans olarak baz alınacak.
  - **Canlıya Dağıtım Yasağı:** Değişiklikler yerel ortamda üretilip incelenecek; açık kullanıcı onayı olmadan `git push` yapılmayacak.

---

## 📋 6 Slaytlık Hibrit Çizgi Roman Senaryo Haritası

1. **Slayt 1 (Kapak - Tam Sahne Salon):**
   - *Görsel:* Gece saat 03:15, loş abajurlu salonda kanepede Işıl kucağında kocaman gözlerle bakan sevimli tavşan tulumlu Mışıl ile oturuyor.
   - *Metin:* Üstte `⚡ MIŞIL COMICS SAYI #2`, ortada dev çizgi roman başlığı: **"BÜYÜLÜ 4. AY FIRTINASI!"** / *(Ne Oldu Bu Bebeğe?!)*.
2. **Slayt 2 (Kriz - Ayakta Volta & Kriz Balonu):**
   - *Görsel:* Işıl salonda ayakta Mışıl omzunda hafif esnerken duvardaki saate bakıyor.
   - *Metin:* Büyük konuşma balonu: *"Daha 45 dakika önce uyumuştun, ne oldu tatlım?!"* + Anlatıcı kutusu: `📍 SAAT 03:15 • SALONDA 4. TUR...`
3. **Slayt 3 (Biyolojik Sır - Hibrit Şema):**
   - *Görsel:* Üstte kucakta Mışıl'a bakan Işıl Anne; altta geniş, temiz zeminli **45 Dakikalık Rüyalar Treni Şeması** (Hafif Uyku ➔ Derin Uyku ➔ Kritik Uyanış Köprüsü).
   - *Metin:* *"Bebek beyni yetişkin uykusuna geçiyor. Döngüyü bağlamayı henüz bilmiyor!"* (Büyük, net puntolar).
4. **Slayt 4 (Tuzak - Kucakta Sallama Döngüsü):**
   - *Görsel:* Işıl kucağında Mışıl'ı beşik başında sallıyor; Mışıl tam durunca gözünü açıyor.
   - *Metin:* Çizgi Roman Çıkartması: `💥 45 DAKİKA ALARMI!` + *"Her mıkırdanmada sallarsak kendi kendine dalmayı öğrenemez!"*
5. **Slayt 5 (Süper Güç / Çözüm - Rahatlama & Reçete):**
   - *Görsel:* Işıl koltukta gevşemiş, komodinde Mışıl Baby açık, Mışıl kucağında esneyip derin uykuya dalıyor.
   - *Metin:* `🛡️ AKUSTİK KALKAN!` + 3 Adımlı Reçete (1. Işıkları Karart, 2. Anne Karnı Sesi Aç, 3. İlk 3 Dk Dokunma).
6. **Slayt 6 (Zafer & CTA - Sarılıp Uyuma & DM Tetikleyici):**
   - *Görsel:* Sabah ışığı girerken kanepede huzurla sarılıp uyuyan Işıl ve Mışıl.
   - *Metin:* **"FIRTINA GEÇTİ, MIŞIL UYUDU! 💤"** + *"Yorumlara FIRTINA yaz, 4. Ay Kılavuzunu DM'den gönderelim!"*

---

## 🛠️ İcra Adımları

1. **Adım 1:** Kapak için loş salon/kanepe sahnesi referansı ile render motorunu entegre etme.
2. **Adım 2:** `projects/mishil/scripts/render_instagram_comic_02.py` dosyasını hibrit düzen, kucakta/salonda paneller ve dev 34-40px tipografi ile güncelleme.
3. **Adım 3:** Playwright ile 6 slaytın yüksek çözünürlüklü (1080x1080) renderını alma.
4. **Adım 4:** `projects/mishil/public/preview_instagram_concepts.html` önizleme arayüzünü güncelleme ve tarayıcıda doğrulama.
5. **Adım 5:** Kullanıcı incelemesine ve onayına sunma.
