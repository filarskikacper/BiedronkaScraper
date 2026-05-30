# BiedronkaScraper 🐞

Automatyczny system scrapowania gazetek **Biedronki**, ekstrakcji danych produktów przez AI (Google Gemini Vision) oraz wizualizacji promocji i historii cen.

🌐 **Dashboard na żywo:** [biedronkascraper.vercel.app](https://biedronkascraper.vercel.app) *(po konfiguracji)*

---

## Jak to działa?

```
┌──────────────┐     ┌────────────────┐     ┌──────────────┐     ┌────────────┐
│ Biedronka.pl │ ──▶ │ Scrapy crawler │ ──▶ │ Gemini OCR   │ ──▶ │ SQLite DB  │
│  (gazetki)   │     │ (obrazy stron) │     │ (ekstrakcja) │     │ (dane)     │
└──────────────┘     └────────────────┘     └──────────────┘     └─────┬──────┘
                                                                       │
                                                                       ▼
                                                              ┌────────────────┐
                                                              │ export_static  │
                                                              │ (JSON files)   │
                                                              └───────┬────────┘
                                                                      │
                                                              ┌───────▼────────┐
                                                              │  Vercel        │
                                                              │  (dashboard)   │
                                                              └────────────────┘
```

### Pipeline (GitHub Actions — codziennie o 20:00 CET):
1. **Scrapy** pobiera obrazy stron gazetek z biedronka.pl
2. **Gemini Vision API** analizuje obrazy i wyciąga dane o produktach (ceny, promocje, kategorie)
3. **SQLite** przechowuje dane z deduplikacją produktów i historią cen
4. **export_static.py** eksportuje dane do plików JSON
5. **Vercel** automatycznie deployuje zaktualizowaną stronę

---

## Konfiguracja

### 1. GitHub Secrets

W repozytorium na GitHubie: **Settings → Secrets and variables → Actions → New repository secret**

| Nazwa | Wartość |
|-------|---------|
| `GEMINI_API_KEY` | Twój klucz API Google Gemini |

### 2. Vercel

1. Załóż konto na [vercel.com](https://vercel.com)
2. Kliknij **"Add New Project"**
3. Importuj repozytorium `BiedronkaScraper` z GitHuba
4. Vercel automatycznie wykryje `vercel.json` i skonfiguruje się sam
5. Po każdym pushu do `main`, strona się automatycznie przebudowuje

### 3. Ręczne uruchomienie pipeline'u

Na GitHubie: **Actions → Scrape & Deploy → Run workflow**

---

## Uruchomienie lokalne

```bash
# Instalacja zależności
pip install -r requirements.txt

# 1. Scraping gazetek
cd biedronka && scrapy crawl gazetka && cd ..

# 2. Przetwarzanie OCR (wymaga GEMINI_API_KEY w .env)
python ocr_processor.py

# 3. Dashboard Flask (tryb deweloperski)
python dashboard.py

# 4. Eksport do statycznych JSON-ów
python export_static.py
```

---

## Struktura projektu

```
BiedronkaScraper/
├── .github/workflows/scrape.yml   # Automatyzacja GitHub Actions
├── biedronka/                     # Scrapy project (crawler)
│   ├── biedronka/
│   │   ├── spiders/gazetka.py     # Spider scrapujący gazetki
│   │   ├── pipelines.py           # Pipeline pobierania obrazów
│   │   ├── items.py               # Definicja items
│   │   └── settings.py            # Konfiguracja Scrapy
│   └── gazetki/                   # Pobrane obrazy (gitignore)
├── site/                          # Statyczna strona (Vercel)
│   ├── index.html                 # Dashboard
│   ├── style.css                  # Style
│   └── data/                      # Dane JSON (generowane przez CI)
├── database.py                    # Modele SQLAlchemy + logika DB
├── ocr_processor.py               # Procesor Gemini Vision OCR
├── export_static.py               # Eksport DB → JSON
├── dashboard.py                   # Dashboard Flask (dev)
├── vercel.json                    # Konfiguracja Vercel
└── requirements.txt               # Zależności Python
```

---

## Technologie

- **Scrapy** — crawling stron Biedronki
- **Google Gemini Vision API** — OCR / ekstrakcja danych z obrazów
- **SQLAlchemy + SQLite** — baza danych z deduplikacją
- **Flask** — dashboard deweloperski
- **Vercel** — hosting statycznej strony
- **GitHub Actions** — automatyzacja pipeline'u CI/CD