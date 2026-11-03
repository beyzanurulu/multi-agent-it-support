# Model kartı — Türkçe IT destek NLU (intent + NER)

> **Durum: henüz eğitilmedi.** Eğitim hattı uçtan uca çalışıyor ve CI'da küçük bir modelle
> duman testinden geçiyor (`ml/tests/test_pipeline.py`). Aşağıdaki metrik tablosu, BERTurk
> Colab/Kaggle GPU'da eğitilip `ml/evaluate.py` çalıştırıldığında doldurulacak. Doldurulmamış
> hiçbir sayı README'de iddia edilmez.

## Model
- Temel: `dbmdz/bert-base-turkish-cased`
- Mimari: ortak encoder + iki kafa — `[CLS]` üzerinde çok etiketli intent (sigmoid, BCE) ve
  token sınıflandırma NER (BIO, cross-entropy) (`ml/modeling.py`)
- Servis: ONNX (opset 17) + dinamik int8 quantization, ONNX Runtime CPU (`ml/export_onnx.py`,
  `services/nlu-service`)

## Etiketler
- Intent (12, çoklu etiket): password_reset, vpn_issue, email_issue, software_install,
  hardware_issue, network_issue, access_request, printer_issue, account_locked, ticket_status,
  report_request, other
- NER (7): YAZILIM, CIHAZ, HATA_KODU, DEPARTMAN, KISI, IP_ADRESI, TARIH

## Veri
- `ml/data/generate.py`: **189 şablon** (niyet başına 13–19) + slot doldurma ile 3000 sentetik
  Türkçe talep; %20 çoklu niyet; yazım hatası, Türkçe karaktersiz yazım, kısaltma,
  Türkçe/İngilizce karışık varyantlar. Her örnek hangi şablondan geldiğini (`templates`) taşır.
  `--llm 0.5 --provider ollama|openai` ile örneklerin bir kısmı LLM ile yeniden ifade edilir
  (entity metinleri birebir korunmazsa örnek değiştirilmeden bırakılır).
- İlk sürümde yalnızca 71 şablon vardı; 3000 örnek pratikte 71 cümlenin varyasyonuydu. Şablon
  sayısı bu yüzden artırıldı ve split şablon bazlı yapıldı (aşağıda).
- `ml/data/clean.py`: tekrar temizleme, span doğrulama, sınıf dengesi raporu
  (`ml/reports/data_report.md`).
- Etiketleme: `ml/data/labelstudio.py export` ile ön-etiketli 600 görev → Label Studio
  (`label_studio_config.xml`) → elle düzeltme → `import` + `merge` ile `verified=true`.
- `ml/data/split.py`: **şablon bazlı** ayırma — her niyetin şablonlarının ~%15'i yalnızca teste,
  ~%15'i yalnızca val'e gider; eğitim bu şablonları hiç görmez (aynı şablonun varyasyonları
  rastgele ayrılırsa test skoru ezberi ölçer). Eğitim/test şablonu karışan çoklu niyet örnekleri
  atılır. Test seti varsayılan olarak **yalnızca elle doğrulanmış** örneklerden oluşur;
  `--allow-unverified-test` kullanılırsa rapora bu açıkça yazılır.
- Entity değer listeleri (yazılım, departman, hata kodu…) bölümler arasında ortaktır; model
  görmediği bir değeri tanıyabiliyor mu, ayrıca ölçülmez.
- Kişi adları, departmanlar ve tüm talepler sentetiktir; gerçek kişi/şirket verisi yoktur.

## Eğitim (önerilen)
```bash
python ml/data/generate.py --n 3000 --llm 0.5 --provider ollama     # veya --provider openai
python ml/data/clean.py ml/data/raw.jsonl ml/data/clean.jsonl
python ml/data/labelstudio.py export ml/data/clean.jsonl ml/data/ls_tasks.json --n 600 --heldout-only
#   ... Label Studio'da düzelt, export al ...
python ml/data/labelstudio.py import ls_export.json ml/data/verified.jsonl
python ml/data/labelstudio.py merge ml/data/clean.jsonl ml/data/verified.jsonl ml/data/clean.jsonl
python ml/data/split.py ml/data/clean.jsonl ml/data/splits
python ml/train.py --train ml/data/splits/train.jsonl --val ml/data/splits/val.jsonl \
    --epochs 4 --lr 3e-5 --max-len 96          # MLflow: mlruns/
python ml/export_onnx.py ml/artifacts/berturk models/nlu
python ml/evaluate.py ml/data/splits/test.jsonl --onnx models/nlu --llm
```

## Metrikler (test seti, elle doğrulanmış)

| Backend | Intent macro-F1 | NER F1 | CPU p95 | $/1k istek |
|---|---|---|---|---|
| BERTurk (ONNX int8) | _eğitim sonrası_ | _eğitim sonrası_ | _eğitim sonrası_ | 0 |
| LLM few-shot (gpt-4o-mini) | _eğitim sonrası_ | _eğitim sonrası_ | _eğitim sonrası_ | ≈0.3 |
| Kural tabanlı (mevcut yedek) | 0.70¹ | 0.67¹ | 0.67 ms¹ | 0 |

¹ Ön ölçüm: şablon bazlı split'in test bölümü (456 örnek, 35 görülmemiş şablon), **henüz elle
doğrulanmamış**. Rapor: `ml/reports/nlu_eval_rules_heldout.md`. Aynı kurallar kendi 120 senaryoluk
eval setinde %100 alıyordu; görülmemiş cümle yapılarında düşüş, fine-tuned modele duyulan
ihtiyacın ölçüsü. En zayıf sınıflar: `other` 0.36, `hardware_issue` 0.43, `vpn_issue` 0.52.

Hedefler: intent macro-F1 ≥ 0.90, NER entity-F1 ≥ 0.85, CPU inference p95 < 80 ms.

## Bilinen sınırlar / riskler
- Sentetik şablonlar gerçek kullanıcı dilinin çeşitliliğini tam yansıtmaz; LLM paraphrase ve
  elle doğrulama bu açığı kısmen kapatır.
- `KISI` etiketi şablonlarda az sayıda isimle üretilir; yeni isimlere genelleme zayıf olabilir.
- Hata kodları kapalı bir listeden gelir; görülmemiş kod biçimleri kaçabilir.
- Model, PII maskeleme guardrail'inden **sonra** çalışır; maskelenmiş metinde (`<TELEFON>`) NER
  doğal olarak entity bulmaz.
