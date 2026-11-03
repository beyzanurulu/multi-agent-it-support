# Elle doğrulama (Label Studio)

Amaç: test setini oluşturacak, **eğitimde hiç görülmeyen şablonlardan** gelen örnekleri elle
kontrol etmek. Şablon verisinin etiketleri zaten doğrudur; asıl hata kaynağı LLM ile yeniden
ifade edilmiş örneklerdir (entity'nin yanlış yere kayması, niyetin değişmesi). Bu yüzden önce
`--llm` ile çeşitlendirme yapın, sonra doğrulayın.

## 1. Görevleri hazırla
```bash
python ml/data/generate.py --n 3000 --llm 0.5 --provider ollama   # veya openai
python ml/data/clean.py ml/data/raw.jsonl ml/data/clean.jsonl
python ml/data/labelstudio.py export ml/data/clean.jsonl ml/data/ls_tasks.json --n 600 --heldout-only
```
`--heldout-only` yalnızca test/val şablonlarından örnek alır (önce test).

## 2. Label Studio
```bash
pip install label-studio
label-studio start            # http://localhost:8080
```
1. **Create Project** → *Labeling Setup* → *Custom template* → `ml/data/label_studio_config.xml`
   içeriğini yapıştır.
2. **Import** → `ml/data/ls_tasks.json`. Ön-etiketler "prediction" olarak gelir.
3. Her görevde:
   - Niyetler doğru mu? Birden fazla seçilebilir; mesaj IT dışıysa yalnızca `other`.
   - Entity sınırları doğru mu? Ek dahil değil: "Outlook'ta" → yalnızca `Outlook`.
   - Cümle anlamsız veya LLM bozmuşsa görevi **Skip** et (veriye girmez).
   - Kısa kural: emin değilsen etiketleme, skip et.
4. **Export** → *JSON* → `ls_export.json`.

Hız: ön-etiketler çoğunlukla doğru olduğu için görev başına ~15–25 sn; 600 görev ≈ 3–4 saat.
Parça parça yapılabilir; her export'tan sonra 3. adım tekrar çalıştırılabilir.

## 3. Veriye geri al ve böl
```bash
python ml/data/labelstudio.py import ls_export.json ml/data/verified.jsonl
python ml/data/labelstudio.py merge ml/data/clean.jsonl ml/data/verified.jsonl ml/data/clean.jsonl
python ml/data/split.py ml/data/clean.jsonl ml/data/splits
cat ml/data/splits/split_report.json     # test_verified = test satır sayısı olmalı
```
Sonra eğitim: `ml/MODEL_CARD.md` → Eğitim.
