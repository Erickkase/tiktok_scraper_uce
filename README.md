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

No descarga los videos completos ni las respuestas a los comentarios. No accede a
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
No necesitas ejecutar ningun otro script.

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
