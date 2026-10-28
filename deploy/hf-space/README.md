---
title: Türkçe IT Destek Multi-Agent
emoji: 🛠️
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 5.9.1
python_version: "3.12"
app_file: app.py
pinned: false
short_description: LangGraph + FastMCP ile Türkçe IT destek asistanı (demo)
---

# Türkçe IT Destek Multi-Agent — canlı demo

Giriş: `calisan`, `uzman` veya `yonetici`, şifre `demo`. Tüm veriler sentetiktir ve Space her
başladığında sıfırlanır. Kod ve açıklamalar: https://github.com/beyzanurulu/multi-agent-it-support

Bu Space yalnızca `app.py`, `requirements.txt`, `packages.txt` ve bu dosyayı içerir. Arayüz
Gradio değil Chainlit'tir: `app.py` kodu GitHub'dan çeker, bağımlılıkları ayrı bir ortama kurar
ve servisleri başlatır. İlk açılış birkaç dakika sürer.
