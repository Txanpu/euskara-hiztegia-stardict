# Euskara Hiztegia (eu-eu) - StarDict / KOReader

# Euskara Hiztegia (eu-eu) - StarDict / KOReader

Diccionario monolingüe de euskera (eu -> eu) en formato StarDict optimizado para KOReader, con índice de declinaciones (deklinabidea), formas verbales y aditz trinkoak (.syn).

## Instalación en KOReader
1. Descarga eu-eu-hiztegia-stardict.zip desde Releases (o clona este repositorio).
2. Copia la carpeta eu-eu-hiztegia/ dentro de koreader/data/dict/ en tu dispositivo.
3. Reinicia KOReader o recarga los diccionarios desde Búsqueda -> Ajustes -> Gestión de diccionarios.

## Recompilar desde cero

    curl -fL -o euwiktionary.xml.bz2 https://dumps.wikimedia.org/euwiktionary/latest/euwiktionary-latest-pages-articles.xml.bz2
    python3 -m venv venv && source venv/bin/activate
    pip install nltk
    python3 build_stardict_eu.py

## Fuentes y licencias
- Wikiztegia (eu.wiktionary.org) - Licencia CC BY-SA 4.0.
- Euskal WordNet (Grupo IXA, UPV/EHU, vía Open Multilingual Wordnet) - Licencia CC BY 4.0.
