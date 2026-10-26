# ADR 001 — Orkestrasyon için LangGraph

**Durum:** Kabul edildi

## Bağlam
Supervisor'ın planı adım adım yürütmesi, kullanıcıdan cevap beklemesi (çözüm işe yaradı mı,
eksik bilgi), yazma işlemlerinden önce insan onayı alması ve konuşmanın yeniden başlatmadan
sonra devam etmesi gerekiyor.

## Karar
LangGraph `StateGraph` + `Command(goto=...)` handoff + `interrupt()` + Postgres checkpointer/store.

## Gerekçe
- `interrupt()` ve checkpointer, onay akışını ayrı bir kuyruk/iş akışı servisi olmadan sağlar.
- `Command` ile yönlendirme, ajanların supervisor'a dönüşünü kodda açık bırakır (mesaj geçişi).
- LangSmith ile her node otomatik izlenir.

## Alternatifler
- CrewAI / AutoGen: rol tabanlı konuşma için pratik, fakat durum kalıcılığı ve onay kesmesi
  için ek altyapı gerekiyor.
- Elle yazılmış durum makinesi: bağımlılık yok ama checkpoint, streaming ve tracing yeniden
  yazılmalı.
