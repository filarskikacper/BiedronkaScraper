# BiedronkaScraper

Automatyczny system scrapowania gazetek **Biedronki**, ekstrakcji danych produktów przez AI (Google Gemini Vision) oraz wizualizacji promocji i historii cen.

[biedronkascraper.vercel.app](https://biedronkascraper.vercel.app)

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

