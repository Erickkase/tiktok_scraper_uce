# Recopilador de datos de TikTok

Programa en Python que recibe un usuario de TikTok y guarda datos publicos de su
perfil y de hasta 10 videos recientes que consiga cargar. Utiliza Playwright,
sin extensiones del navegador.

## Que hace

- Obtiene la cantidad de seguidores y cuentas seguidas.
- Recopila enlaces y visualizaciones de hasta 10 videos.
- Obtiene las cantidades de corazones, comentarios, compartidos y guardados de cada video.
- Guarda los datos en dos archivos Excel: uno del perfil y otro de los videos.
- Descarga las miniaturas y la imagen del perfil cuando estan disponibles.
- Espera al menos 2 segundos entre las consultas de videos.

No descarga los videos completos ni el texto de los comentarios. No accede a
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
- Las imagenes que se hayan podido descargar.

Los datos no disponibles quedan vacios. La columna `Metrics Error` indica los
problemas al obtener interacciones. Si se cargan menos de 10 videos, se guardan
los disponibles. Ejecutar el mismo usuario el mismo dia puede sobrescribir los
archivos; cierra los Excel antes de volver a ejecutar el programa.
