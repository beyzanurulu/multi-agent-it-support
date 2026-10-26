Fine-tuned BERTurk ONNX modeli buraya gelir (`ml/export_onnx.py` çıktısı):
`model.onnx`, `tokenizer.json`, `labels.json`. Dosyalar yoksa nlu-service kural tabanlı
yedek backend ile çalışır (`/health` -> `"backend": "rules"`).
