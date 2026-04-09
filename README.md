# 🏠 Wohnungsqualitäts Score

Eine webbasierte Anwendung zur objektiven Bewertung der Wohnqualität von Nachbarschaften basierend auf der Nähe zu Infrastrukturen (Supermärkte, Ärzte, ÖPNV, Parks).

## ✨ Features

- 🔍 Adresssuche und Bewertung
- 📊 Detaillierte Analyse nach 5 Kategorien
- 🗺️ Interaktive Kartenvizualisierung
- 📌 Vergleichsfunktion mit Pinning
- 🎨 Radius-Visualisierung mit unterschiedlichen Farben
- 📥 CSV/JSON Export
- ⚙️ Anpassbare Gewichtungen

## 🚀 Installation

```bash
git clone https://github.com/pottmeier/housing-score.git
cd housing-score
docker compose up --build
```

Frontend: **http://localhost:8501**

## 🏗️ Technologie

| Komponente | Technologie |
|-----------|-------------|
| Frontend | Streamlit, Folium |
| Backend | FastAPI, Python |
| Cache | Redis |
| Daten | OpenStreetMap (Nominatim, Overpass) |

## 📄 Lizenz

[MIT](LICENSE)
