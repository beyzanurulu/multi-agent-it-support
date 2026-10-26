# ADR 003 — KB için pgvector (ayrı vektör DB yerine)

**Durum:** Kabul edildi

## Karar
Bilgi tabanı vektörleri, ticketlar, checkpoint'ler ve uzun dönem hafıza tek PostgreSQL
örneğinde. Arama hibrit: pgvector kosinüs + Türkçe tam metin (`to_tsvector('turkish')`) + hata
kodu eşleşmesi, Reciprocal Rank Fusion ile birleştirilir.

## Gerekçe
- Ücretsiz altyapıda (4 ARM çekirdek / 24 GB) tek veritabanı işletmek daha ucuz ve basit.
- Hata kodu gibi tam eşleşme gereken sorgularda yalnızca vektör arama zayıf; FTS ve kod
  eşleşmesi bunu kapatır.
- Analytics ajanı aynı veritabanında read-only rol ve view ile güvenle sorgu yapabilir.

## Bedeli
Vektör DB'lerin bazı özellikleri (ör. otomatik yeniden sıralama) yok; 60+ doküman ölçeğinde
gerek yok.
