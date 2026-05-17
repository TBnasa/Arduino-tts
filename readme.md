# 🗣️ Turkish Arduino TTS (Ses Sentezleyici) Projesi

Hoş geldiniz! Bu proje, kısıtlı donanım kaynaklarına sahip Arduino geliştirme kartlarında (Uno, Nano vb.) **pürüzsüz ve gerçek zamanlı Türkçe ses sentezleme (Text-to-Speech)** yapabilmek için geliştirilmiştir.

Proje, kolaydan zora doğru 3 farklı donanım ve yazılım katmanına ayrılmış, tamamen bağımsız 3 klasör halinde organize edilmiştir:

---

## 📂 Klasör Yapısı ve Seçenekler

### 1️⃣ [1_arduino](file:///home/tahir/%C4%B0ndirilenler/arduimo-tts/1_arduino) (Başlangıç Düzeyi)
* **Açıklama:** Sadece **tek bir Arduino** kartıyla çalışır. I2C veya ek kartlara ihtiyaç duymaz.
* **Ses Kalitesi:** 16.000 Hz Örnekleme Hızı (Oldukça temiz ve anlaşılır).
* **Donanım:** 1 adet Arduino Uno veya Nano, 1 adet 1K Ohm direnç, 1 adet 100nF kondansatör.

### 2️⃣ [2_arduino](file:///home/tahir/%C4%B0ndirilenler/arduimo-tts/2_arduino) (Orta Düzey)
* **Açıklama:** **İki adet Arduino** kartının (1 Master + 1 Slave) belleklerini I2C üzerinden birleştirir (Toplam 64KB Ses Belleği).
* **Ses Kalitesi:** 24.000 Hz (CD Kalitesinde ses birleştirme).
* **Donanım:** 2 adet Arduino, I2C haberleşme kabloları, pasif direnç mikseri.

### 3️⃣ [3_arduino](file:///home/tahir/%C4%B0ndirilenler/arduimo-tts/3_arduino) (İleri Düzey / Tam Sürüm)
* **Açıklama:** **Üç adet Arduino** kartının (1 Master + 2 Slave) belleklerini I2C üzerinden birleştirerek devasa ses kütüphanesi sunar (Toplam 96KB Ses Belleği).
* **Ses Kalitesi:** 24.000 Hz (CD Kalitesi, tiz korumalı özel empedans tasarımı).
* **Donanım:** 3 adet Arduino, I2C paralel haberleşme, paralel direnç mikseri ve gürültü süzgeci.

---

## 🚀 Nasıl Başlanır?

Kullanmak istediğiniz klasörün içerisine girin ve oradaki özel **`readme.md`** belgesini okuyarak kurulumu ve bağlantıları tamamlayın. Her klasörün kendi ses üretim, test ve Python arayüz dosyaları o klasörün altında yer almaktadır.

*İyi çalışmalar ve keyifli dinlemeler!*
