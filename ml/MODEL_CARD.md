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
- Mevcut veri (`ml/data/clean.jsonl`): **2349 örnek**, 187 şablon, 930'u Ollama
  (qwen2.5:7b) ile yeniden ifade edilmiş, 401 çoklu niyet; split: train 1409 / val 369 /
  test 350 (tamamı doğrulanmış).
- `ml/data/generate.py`: **189 şablon** (niyet başına 13–19) + slot doldurma ile 3000 sentetik
  Türkçe talep; %20 çoklu niyet; yazım hatası, Türkçe karaktersiz yazım, kısaltma,
  Türkçe/İngilizce karışık varyantlar. Her örnek hangi şablondan geldiğini (`templates`) taşır.
  `--llm 0.5 --provider ollama|openai` ile örneklerin bir kısmı LLM ile yeniden ifade edilir
  (entity metinleri birebir korunmazsa örnek değiştirilmeden bırakılır).
- İlk sürümde yalnızca 71 şablon vardı; 3000 örnek pratikte 71 cümlenin varyasyonuydu. Şablon
  sayısı bu yüzden artırıldı ve split şablon bazlı yapıldı (aşağıda).
- `ml/data/clean.py`: tekrar temizleme, span doğrulama, sınıf dengesi raporu
  (`ml/reports/data_report.md`) ve üç otomatik düzeltme:
  - **LLM çıktı temizliği:** yerel modelin sohbet artıkları ("Tabii, işte…", "Talep:"), çok
    satırlı cevaplar, yabancı alfabe (Çince/Rusça) ve kod blokları. İlk Ollama turunda 1344
    yeniden ifadenin 691'i bunlardan birini taşıyordu; ~590'ı kırpılarak kurtarıldı, ~80'i atıldı.
  - **Bağlam kontrolü:** şablon başına izinli değerler (`generate.py` `INTENT_SLOTS`,
    `TEMPLATE_SLOTS`); "Office sürekli kopuyor" (VPN), "kulaklık fanı", VPN şablonunda kurulum
    hata kodu gibi anlamsız kombinasyonlar atılır.
  - **Gazetteer:** şablonda sabit yazılı yazılım/cihaz adları ("GlobalProtect bağlanıyor",
    "Outlook arama çalışmıyor", "yazıcı") etiketsizdi; bilinen adlar eksikse etiketlenir.
- Doğrulama: `ml/data/labelstudio.py export --heldout-only` ile test/val şablonlarından 600
  ön-etiketli görev → Label Studio. Her doğrulanmış örnek kimin doğruladığını taşır
  (`verified_by`):
  - **human:** 127 örnek Label Studio'da elle (`ml/data/ls_export_partial.json`); 40'ı test setinde.
  - **claude:** test şablonlarından kalan 336 örnek Claude tarafından aynı yönergeyle
    (`ml/LABELING.md`) tek tek okundu; 310 doğrulandı, 26 atıldı (anlamı bozuk, niyeti kaymış,
    bozuk kelime). Kararlar ve gerekçeler: `ml/data/review_claude.json`, uygulama:
    `ml/data/apply_review.py`.
  - Test setinin %89'u bir LLM (Claude) tarafından doğrulandı; insan doğrulaması kadar
    güvenilir sayılmamalı. İnsan doğrulamasını artırmak için kalan görevler Label Studio'da
    tamamlanıp aynı adımlarla birleştirilebilir.
- `ml/data/split.py`: **şablon bazlı** ayırma — her niyetin şablonlarının ~%15'i yalnızca teste,
  ~%15'i yalnızca val'e gider; eğitim bu şablonları hiç görmez (aynı şablonun varyasyonları
  rastgele ayrılırsa test skoru ezberi ölçer). Eğitim/test şablonu karışan çoklu niyet örnekleri
  atılır. Test seti varsayılan olarak **yalnızca elle doğrulanmış** örneklerden oluşur;
  `--allow-unverified-test` kullanılırsa rapora bu açıkça yazılır.
- Entity değer listeleri (yazılım, departman, hata kodu…) bölümler arasında ortaktır; model
  görmediği bir değeri tanıyabiliyor mu, ayrıca ölçülmez.
- Kişi adları, departmanlar ve tüm talepler sentetiktir; gerçek kişi/şirket verisi yoktur.

## Eğitim

**Kolay yol:** [`ml/colab_train.ipynb`](colab_train.ipynb) — Colab'da T4 GPU ile aç, `clean.jsonl`'u
yükle, *Tümünü çalıştır*. Çıktı: `nlu-model.zip` (→ GitHub Release, tag `nlu-v*`) ve
`nlu-reports.zip`. Release yayınlanınca `ml/fetch_model.py` modeli `models/nlu/`'ya indirir;
`nlu-service` imajı ve demo sayfası bunu otomatik yapar.

Elle (aynı adımlar):
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
| Kural tabanlı (mevcut yedek) | 0.745 | 0.852 | 0.91 ms | 0 |

Test seti: **350 doğrulanmış örnek**, 35 görülmemiş şablon (eğitim bu şablonları hiç görmez).
Rapor: `ml/reports/nlu_eval_rules.md`. En zayıf sınıflar: `other` 0.32, `access_request` 0.47,
`hardware_issue` 0.58 — fine-tuned modelin kapatması beklenen açık. (Aynı kurallar kendi
120 senaryoluk agent eval setinde %100 alıyordu.)

Hedefler: intent macro-F1 ≥ 0.90, NER entity-F1 ≥ 0.85, CPU inference p95 < 80 ms.

## Bilinen sınırlar / riskler
- Sentetik şablonlar gerçek kullanıcı dilinin çeşitliliğini tam yansıtmaz; LLM paraphrase ve
  elle doğrulama bu açığı kısmen kapatır.
- `KISI` etiketi şablonlarda az sayıda isimle üretilir; yeni isimlere genelleme zayıf olabilir.
- Hata kodları kapalı bir listeden gelir; görülmemiş kod biçimleri kaçabilir.
- Model, PII maskeleme guardrail'inden **sonra** çalışır; maskelenmiş metinde (`<TELEFON>`) NER
  doğal olarak entity bulmaz.
