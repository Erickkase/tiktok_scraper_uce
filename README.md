# TikTok Data Scraper and Metrics Analysis

This repository contains two Python scripts designed to scrape TikTok data and analyze video metrics from specified TikTok user profiles. The scripts utilize Playwright for web automation and asyncio for asynchronous operations. 

## Scripts

1. **main.py**
2. **obtener_estadisticas.py**

### main.py

This script scrapes TikTok profiles to extract video links, views, and profile information. It saves the data in organized Excel files for further analysis.

#### Key Features:
- Scrapes video links and views from TikTok profiles.
- Downloads video thumbnails.
- Extracts and saves profile information (followers, following, likes, bio, profile image).
- Stores all collected data in Excel files.

#### Usage:
Requires Python 3.9 or newer. No browser extensions are used.

1. Install dependencies and the browser:
   ```bash
   python -m pip install -r requirements.txt
   python -m playwright install chromium
   ```
2. Run the script:
   ```bash
   python main.py
   ```
3. Enter a TikTok username when prompted, for example `@tiktok` or `tiktok`.
   Do not enter a profile URL. Results are saved in a folder named after the user,
   relative to the directory from which you run the script.

### Desarrollo Por Etapas

- Etapa 1: entrada de un usuario por consola y validacion del nombre.
- Pendiente: seleccionar los ultimos 10 videos, considerando las publicaciones fijadas.
- Pendiente: integrar comentarios, corazones, compartidos y guardados por video en la descarga.
- Pendiente: manejar perfiles privados, inexistentes, bloqueos y datos no disponibles.

La extraccion actual conserva su comportamiento anterior: no limita la descarga a
10 videos ni integra automaticamente `obtener_estadisticas.py`. Solo puede intentar
recopilar datos publicos que TikTok permita cargar; no evita CAPTCHA ni restricciones.

### obtener_estadisticas.py

This script reads a list of TikTok video links from an Excel file, extracts detailed metrics for each video, and combines this data with the original dataset. It then saves the enriched dataset into a new Excel file.

#### Key Features:
- Parses video publication dates and metrics (likes, comments, shares, saves).
- Converts abbreviated metrics (K, M) into integers.
- Handles errors gracefully and logs any issues encountered.
- Merges extracted metrics with the original dataset and saves to a new Excel file.

#### Usage:
1. Ensure you have Python and the necessary libraries installed (Playwright, pandas).
2. Update the `archivo_entrada` variable with the path to your input Excel file.
3. Run the script:
   ```bash
    python obtener_estadisticas.py
   ```
