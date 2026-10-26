# Eval raporu

Senaryo seti: `evals/scenarios.jsonl` — 120 sentetik senaryo (`evals/build_scenarios.py`).

| Kategori | n | İçerik |
|---|---|---|
| single | 36 | Tek niyet; çözüm kabul / ret + ticket onayı / ret, ticket durumu, IT dışı mesaj, kritik |
| multi | 20 | Çoklu niyet (plan sırası, adım adım çözüm, araya ticket) |
| typo | 19 | Yazım hatası, Türkçe karaktersiz yazım, Türkçe/İngilizce karışık |
| injection | 15 | Prompt injection / SQL enjeksiyonu denemeleri |
| missing_info | 10 | Eksik bilgi → Triage soru sormalı |
| unauthorized_sql | 10 | Yönetici olmayan rollerin rapor/SQL istekleri |
| report | 10 | Yöneticinin doğal dil → SQL soruları |

Çalıştırma: `uv run python evals/run_eval.py --check --label <ad>` (CI her PR'da `--check` ile
çalıştırır; hedef altı skor PR'ı kırmızı yapar). Ham sonuçlar: `evals/reports/<ad>.json`.

## Koşullar (bu rapordaki tüm sayılar için)

- NLU: **kural tabanlı yedek backend** (`nlu_service/rules.py`). BERTurk modeli henüz eğitilmedi
  (bkz. `ml/MODEL_CARD.md`).
- LLM: **yok** (OpenAI/Ollama anahtarı tanımlı değil). Solution ajanı KB makalesinin adımlarını
  verir, Analytics ajanı şablon SQL üretir, görev başarısı **kural tabanlı** kontrol edilir
  (LLM-as-judge LLM tanımlanınca otomatik devreye girer).
- Embedding: offline hashing embedding (CI ile aynı). Üretimde multilingual MiniLM kullanılır.
- Latency: tek makinede, in-process servislerle, ilk ajan mesajına kadar geçen süre.

## İyileştirme iterasyonları

| Metrik | Hedef | baseline | v1 | v2 |
|---|---|---|---|---|
| Routing doğruluğu | ≥ 0.90 | 0.908 | 0.967 | 1.000 |
| Görev başarısı (kural tabanlı) | ≥ 0.85 | 0.883 | 0.975 | 1.000 |
| Tool çağrı doğruluğu | ≥ 0.90 | 0.967 | 1.000 | 1.000 |
| Tutarlılık (20 senaryo × 5) | ≥ 0.90 | 1.000 | 1.000 | 1.000 |
| Guardrail bloklama | 1.00 | **0.92** | 0.96 | 1.000 |
| İlk yanıt p95 | < 3 sn | 65 ms | 64 ms | 78 ms |
| Maliyet / konuşma | raporlanır | $0 (LLM yok) | $0 | $0 |
| Başarısız senaryo | | 16 | 4 | 0 |

**baseline → v1**
- NLU anahtar kelimelerinde eksikler: "cihazım bozuldu", "ekipman", "ne aşamada", "ortalama
  çözüm süresi" `other` olarak sınıflanıyordu → kelime listeleri genişletildi.
- Yazım hatası toleransı yoktu ("outlok", "acilmiyor") → kelime öneklerinde edit distance ≤ 1
  eşleşmesi ve Türkçe karaktersiz karşılaştırma eklendi.
- "SAP için yetki talebim var" hem `access_request` hem `ticket_status` çıkıyordu → durum
  sorgusu anahtar kelimeleri durum fiillerine daraltıldı.
- Triage, "Finans klasörüne erişim" isteğinde gereksiz soru soruyordu → eksik bilgi kontrolü
  departman entity'sini de kabul ediyor.
- **Eval seti düzeltmesi:** 5 çoklu niyet senaryosunda ticket açılmasına rağmen beklenen sonuç
  "solution" yazılmıştı; "ticket" olarak düzeltildi. Görev başarısındaki artışın bir kısmı bu
  etiket düzeltmesinden geliyor.

**v1 → v2**
- Kısa anahtar kelimeler Türkçe karaktersiz karşılaştırmada kelime içinde eşleşiyordu
  ("yapılır" → "yapilir" ⊃ "pil" → `hardware_issue`) → 5 harften kısa kelimeler artık yalnızca
  kelime başında eşleşiyor.
- "Satış ekibinin kaç talebi var" (p→b ünsüz yumuşaması) rapor sorusu olarak tanınmıyordu →
  rapor konusu kalıbına "talebi" eklendi. Yetkisiz SQL bloklama oranı %100'e çıktı.
- "monitor goruntu" Türkçe karaktersiz yazıldığında CIHAZ entity'si çıkmıyordu → cihaz
  sözlüğüne Türkçe karaktersiz varyantlar eklendi.

## Sınırlar — bu sayılar neyi kanıtlamıyor

- Senaryolar ve kural tabanlı NLU **aynı kişi tarafından, birbirini görerek** yazıldı. v2'deki
  %100, kuralların bu seti kapsadığını gösterir; görülmemiş gerçek kullanıcı mesajlarına
  genellemeyi göstermez. Genelleme ölçüsü, elle doğrulanmış test setinde BERTurk değerlendirmesi
  (`ml/evaluate.py`) ve LLM-as-judge ile yapılacak bir sonraki eval turudur.
- LLM kapalıyken tutarlılık tanım gereği %100'dür (deterministik). Asıl tutarlılık ölçümü
  `OPENAI_API_KEY` tanımlıyken alınmalıdır.
- Latency ölçümü LLM çağrısı içermez; LLM açıkken ilk yanıt süresi yeniden ölçülmelidir.
