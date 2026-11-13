# Euskara Hiztegiak (eu-eu & eu-es) — StarDict / KOReader

Colección de diccionarios de euskera en formato **StarDict** optimizados para **KOReader**, con índice morfológico de declinaciones, formas verbales y *aditz trinkoak* (`.syn`):

- **`eu-eu-hiztegia/`**: Diccionario monolingüe **Euskara → Euskara** (~32.000 lemas y ~2,5M de flexiones).
- **`eu-es/`**: Diccionario bilingüe **Euskara → Gaztelania** con traducciones directas y flexiones indexadas.

## Instalación en KOReader
1. Descarga `eu-eu-hiztegia-stardict.zip` y/o `eu-es-hiztegia-stardict.zip` desde la sección **Releases** (o clona este repositorio).
2. Copia las carpetas `eu-eu-hiztegia/` y `eu-es/` dentro de `koreader/data/dict/` en tu dispositivo.
3. Reinicia KOReader o recarga los diccionarios desde **Búsqueda → Ajustes → Gestión de diccionarios**.

## Recompilar desde cero

    curl -fL -o euwiktionary.xml.bz2 https://dumps.wikimedia.org/euwiktionary/latest/euwiktionary-latest-pages-articles.xml.bz2
    python3 -m venv venv && source venv/bin/activate
    pip install nltk
    python3 build_stardict_eu.py
    python3 build_stardict_eu_es.py

## Fuentes y licencias
- **Wikiztegia** (`eu.wiktionary.org`) — Licencia CC BY-SA 4.0.
- **Euskal WordNet** (Grupo IXA, UPV/EHU, vía Open Multilingual Wordnet) — Licencia CC BY 4.0.
