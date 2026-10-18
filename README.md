# TikTok Data Scraper and Metrics Analysis

This repository contains two Python scripts designed to scrape TikTok data and analyze video metrics from specified TikTok user profiles. The scripts utilize Playwright for web automation and asyncio for asynchronous operations. 

## Scripts

1. **main.py**
2. **obtener_estadisticas.py**

### main.py

This script scrapes TikTok profiles to extract video links, views, and profile information. It saves the data in organized Excel files for further analysis.

#### Key Features:
- Scrapes up to 10 recent video links and views from a TikTok profile.
- Downloads video thumbnails.
- Collects likes, comment counts, shares and saves for each selected video.
- Extracts and saves profile information (followers, following, likes, bio, profile image).
- Stores all collected data in Excel files.

#### Usage:
Requires Python 3.9 or newer. No browser extensions are used.

1. Install dependencies and the browser:
   ```bash
   python -m pip install --only-binary=:all: -r requirements.txt
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
- Etapa 2: exportar hasta 10 videos unicos, ordenados del mas reciente al mas antiguo.
- Etapa 3: integrar comentarios, corazones, compartidos y guardados por video en la descarga.
- Etapa 4: pausa entre videos, deteccion de restricciones y cierre seguro del navegador.

La seleccion carga hasta reunir al menos 20 candidatos o hasta que tres intentos
consecutivos no agreguen videos, con un maximo de 30 lecturas. Ordena los videos
por su identificador temporal de TikTok para que los fijados antiguos no desplacen
a los recientes. Supone que el perfil carga en el orden habitual de publicaciones
recientes, no por popularidad. Solo considera enlaces del usuario solicitado.
Si TikTok carga menos de 10 videos, exporta los disponibles y muestra un aviso;
esto no demuestra que el perfil tenga menos de 10 publicaciones. Los videos sin
vistas o miniatura siguen incluidos, con esos datos vacios o marcados como ausentes.

`main.py` visita cada video y agrega las columnas `Likes` (corazones), `Comments`
(cantidad de comentarios), `Shares` (compartidos), `Saves` (guardados) y `Metrics Error`
al Excel de publicaciones. No descarga el texto de los comentarios ni los videos.
Primero lee los contadores de los datos estructurados de la pagina, comprobando
que correspondan al video solicitado. Si faltan, intenta leer los contadores
visibles, incluido `favorite-count` para guardados. Los contadores visibles con K,
M o B son aproximados. La navegacion usa el idioma ingles para interpretar esos
formatos numericos. Una metrica ausente queda vacia, no se convierte en cero;
`Metrics Error` explica los fallos recuperables y la ejecucion continua con el siguiente video.

Entre el final de una consulta de interacciones y la apertura del siguiente video
se esperan al menos 2 segundos (`VIDEO_DELAY_SECONDS` en `main.py`), incluso si
faltaron metricas en el video anterior. Para 10 videos hay 9 pausas: al menos
18 segundos adicionales. No hay una pausa adicional antes del primero ni despues
del ultimo. La pausa no garantiza evitar bloqueos y no limita las solicitudes
internas que el navegador hace al cargar cada pagina.

Ante HTTP 403/429, una verificacion visible conocida o una redireccion al login,
se detienen las consultas de videos: se guardan los resultados obtenidos y se
marcan los videos restantes con el motivo. No hay reintentos automaticos ni
intentos de evitar la restriccion. Los mensajes visibles de perfil privado o
cuenta inexistente se muestran como errores claros. Si no se cargan enlaces de
videos, se informa sin afirmar que la cuenta no tenga publicaciones. Estos
detectores dependen del HTML y los mensajes de TikTok y no cubren todas sus
variantes. El navegador se cierra tambien ante errores o cancelacion. Si el Excel
esta abierto o no hay permisos para guardarlo, se muestra un mensaje explicativo.

No es necesario ejecutar `obtener_estadisticas.py`: queda como script independiente
anterior y no se utiliza en el flujo principal. Solo se recopilan datos publicos
que TikTok permita cargar; no se evitan CAPTCHA ni restricciones.

#### Pruebas locales

```bash
python -B -m unittest discover -s tests -v
```

Estas pruebas usan datos simulados y no consultan TikTok.

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
