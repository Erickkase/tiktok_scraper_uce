# Recopilador de datos de TikTok

Programa en Python que recibe un usuario de TikTok y guarda datos publicos de su
perfil y de hasta 10 videos recientes que consiga cargar. Utiliza Playwright,
sin extensiones del navegador.

## Que hace

- Obtiene la cantidad de seguidores y cuentas seguidas.
- Recopila enlaces y visualizaciones de hasta 10 videos.
- Obtiene las cantidades de corazones, comentarios, compartidos y guardados de cada video.
- Intenta obtener 20 comentarios principales con texto por video, sin duplicar sus IDs.
- Guarda tres archivos Excel: perfil, videos y comentarios.
- Descarga las miniaturas y la imagen del perfil cuando estan disponibles.
- Espera al menos 2 segundos entre las consultas de videos.

El comando principal no descarga los videos completos ni las respuestas a los comentarios. No accede a
cuentas privadas ni evita CAPTCHA o restricciones de TikTok. La disponibilidad
de los datos depende de lo que TikTok permita cargar; la pausa no garantiza evitar bloqueos.

## Instalacion

Necesitas Python 3.9 o superior y conexion a Internet. Abre una terminal en la
carpeta del proyecto, donde estan `main.py` y `requirements.txt`.

Ejecuta estos comandos, uno a la vez, antes del primer uso:

```powershell
python -m pip install --only-binary=:all: -r requirements.txt
python -m playwright install chromium
```

## Como ejecutar

En la terminal del proyecto, ejecuta:

```powershell
python main.py
```

Escribe el usuario cuando el programa lo solicite, con o sin `@`, y pulsa Enter:

```text
Usuario de TikTok (con o sin @): @tiktok
```

No ingreses la URL completa. Se abrira una ventana de Chromium; espera a que
termine y revisa los mensajes de la terminal. Puedes cancelar con `Ctrl+C`.
No necesitas ejecutar ningun otro script para obtener los Excel y comentarios.

## Resultados

Se crea una carpeta con el nombre del usuario dentro del directorio desde el
que ejecutaste el programa. Contiene:

- `<usuario>_perfil_<fecha>.xlsx`: seguidores, seguidos y datos del perfil.
- `<usuario>_post_<fecha>.xlsx`: enlaces, vistas e interacciones de los videos.
- `<usuario>_comentarios_<fecha>.xlsx`: enlace del video, ID del comentario, autor, texto y corazones del comentario.
- Las imagenes que se hayan podido descargar.

Los datos no disponibles quedan vacios. La columna `Metrics Error` indica los
problemas al obtener interacciones. Si se cargan menos de 10 videos, se guardan
los disponibles. `Comments` sigue siendo el contador total del video;
`Comments Collected` indica cuantos textos se obtuvieron y `Comments Error`
explica si no se llego a 20 o hubo un problema. Se guarda lo disponible si hay
menos de 20 comentarios publicos o TikTok no permite cargarlos. Se sigue el orden
que muestra TikTok, no necesariamente el cronologico. La espera entre videos se
mantiene y se esperan 2 segundos entre intentos de cargar mas comentarios.
Ejecutar el mismo usuario el mismo dia puede sobrescribir los
archivos; cierra los Excel antes de volver a ejecutar el programa.

## Descargar los videos (opcional)

Esta es la primera etapa de preparacion para analizar el lenguaje hablado de los
videos. Todavia no transcribe audio ni calcula Big Five, emociones o personalidad.

Usa Python 3.12 para este paso. La descarga es independiente del scraper y no
cambia su instalacion de Python. Instala las dependencias opcionales:

```powershell
py -3.12 -m pip install --only-binary=:all: -r requirements_videos.txt
py -3.12 -m playwright install chromium
```

Despues de ejecutar `main.py`, indica la ruta real del Excel de publicaciones:

```powershell
py -3.12 descargar_videos.py "usuario\usuario_post_2026-10-21.xlsx"
```

Cambia `usuario` y la fecha por los de tu archivo. Se intenta descargar hasta 10
videos unicos en la subcarpeta `videos`, junto al Excel. El limite es 200 MiB por
archivo y se esperan al menos 2 segundos entre consultas. Los MP4 existentes que
pasan las comprobaciones basicas se reutilizan. No se sobrescriben archivos
existentes invalidos ni se intenta evitar restricciones.

Se genera `<nombre_del_excel>_descargas.xlsx` con el avance, archivo y motivo de
cada resultado. Los estados son `downloaded` (descargado), `existing` (ya existia),
`error` (fallo), `not_queried` (no consultado), `invalid` (enlace invalido),
`duplicate` (repetido), `limit` (fuera del limite) y `cancelled` (cancelado).
Si aparece una restriccion 403/429, CAPTCHA o solicitud de inicio de sesion, se
detienen las consultas restantes. No todos los videos publicos permiten descarga.
Se espera un MP4 del reproductor publico, sin unir pistas ni convertir con FFmpeg.
Las comprobaciones de archivo son basicas; la transcripcion debera comprobar si
contiene voz util antes de realizar cualquier analisis.
