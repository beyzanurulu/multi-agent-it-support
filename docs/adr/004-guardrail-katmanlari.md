# ADR 004 — Guardrail'ler katmanlı, LLM'e güvenmeden

**Durum:** Kabul edildi

## Karar
Her risk için LLM'in doğru davranmasına bağlı olmayan en az bir kontrol:
- Yazma tool'ları → `interrupt()` ile insan onayı.
- SQL → sqlglot doğrulaması **ve** veritabanı seviyesinde read-only rol / view / timeout.
- Tool erişimi → kod seviyesinde ajan × rol allowlist.
- PII → LLM'e gitmeden önce maskeleme.
- Prompt injection → giriş sınıflandırıcısı; kaçan bir deneme yine de yukarıdaki katmanlara takılır.

## Gerekçe
Prompt injection sınıflandırıcısı tek başına %100 olamaz; zarar verebilecek her işlem
deterministik bir kontrolün arkasında durmalı.
