# ADR 002 — NLU: fine-tuned BERTurk + LLM yerine

**Durum:** Kabul edildi (model eğitimi bekleniyor)

## Bağlam
Her mesajda intent ve NER gerekiyor. Bunu LLM ile yapmak her mesaja maliyet ve gecikme ekler;
çıktı biçimi de her zaman kararlı değildir.

## Karar
`dbmdz/bert-base-turkish-cased` üzerinde ortak intent + NER modeli, ONNX int8, CPU'da ayrı
servis. Model yokken aynı arayüzü sunan kural tabanlı backend.

## Gerekçe
- Hedef: CPU p95 < 80 ms, istek başına sıfır maliyet, deterministik çıktı.
- Ayrı servis: model güncellemesi agent-api'yi yeniden deploy etmeden yapılır.
- Kural tabanlı backend hem yedek hem de değerlendirmede baseline'dır.

## Doğrulama
`ml/evaluate.py` aynı elle doğrulanmış test setinde BERTurk, LLM few-shot ve kural tabanlı
backend'i doğruluk, latency ve maliyetle karşılaştırır (`ml/MODEL_CARD.md`).
