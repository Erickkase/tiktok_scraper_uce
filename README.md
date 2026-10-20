# Recopilador de datos publicos de TikTok

Este proyecto permite escribir un usuario de TikTok en la terminal y guardar
datos publicos de su perfil y de hasta 10 videos recientes entre los candidatos
que consiga cargar. Genera dos archivos Excel y descarga las miniaturas y la
imagen del perfil cuando estan disponibles.

El programa principal es `main.py`. Recopila datos para que puedas revisarlos;
no realiza analisis estadistico, no calcula indicadores ni genera graficos.

## Que hace y que no hace

- Guarda enlaces de videos y cantidades de vistas, corazones, comentarios,
  compartidos y guardados que TikTok permita consultar.
- Guarda seguidores, cuentas seguidas, corazones totales del perfil, biografia
  e imagen del perfil.
- Usa los datos estructurados publicos incluidos en la pagina del video como
  primera fuente de interacciones. Si faltan, intenta leer los contadores
  visibles. Las vistas se leen de las tarjetas del perfil.
- `Comments` es la cantidad de comentarios, no su texto. Recopilar el texto de
  los comentarios queda como trabajo futuro; no esta implementado.
- No descarga videos MP4, no usa extensiones ni la API oficial de TikTok.
- No tiene pagina web ni base de datos: se ejecuta en la terminal y guarda
  archivos locales.
- No accede a contenido privado, no resuelve CAPTCHA ni evita restricciones.
  No garantiza resultados para todos los perfiles ni en todas las ejecuciones.

## Requisitos

- Windows con acceso a Internet y una terminal, como PowerShell.
- Python 3.9 o superior. Se recomienda Python 3.12 para facilitar la instalacion
  de dependencias compatibles.
- Espacio y permisos de escritura en la carpeta donde ejecutes el programa.

Playwright controla un navegador Chromium que se instala con el comando indicado
mas abajo. No necesitas instalar una extension. El navegador se abre en una
ventana durante la ejecucion.

## Instalacion en Windows

Abre la carpeta del proyecto en el Explorador de archivos. En este equipo esta
en `C:\Users\Erick\Downloads\tiktok_scraper_uce`; si lo descargaste en otro
equipo, abre la ubicacion donde lo guardaste. Haz clic en la barra de direcciones,
escribe `powershell` y pulsa Enter.
Asi la terminal empieza en la raiz del proyecto, donde estan `main.py` y
`requirements.txt`. Ejecuta los comandos de esta guia desde esa carpeta.

Comprueba que Python esta instalado:

```powershell
python --version
```

Si no se reconoce el comando, instala Python desde su sitio oficial y habilita
la opcion de agregarlo a PATH. Despues abre una terminal nueva.

Instala las dependencias y el navegador, un comando a la vez:

```powershell
python -m pip install --only-binary=:all: -r requirements.txt
python -m playwright install chromium
```

`requirements.txt` incluye pandas y openpyxl para los Excel, Playwright para el
navegador, y aiohttp y aiofiles para descargar y guardar imagenes. La opcion
`--only-binary=:all:` pide paquetes ya compilados y evita intentar compilarlos
en tu equipo.

### Entorno virtual opcional

Un entorno virtual separa las dependencias de este proyecto de las de otros
programas. Si prefieres esta opcion, usa estos comandos en lugar de la instalacion
anterior:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

No hace falta activar el entorno: se llama directamente a su ejecutable. Esto
evita problemas con la politica `ExecutionPolicy` de PowerShell sin cambiarla.
En los comandos de ejecucion y pruebas, sustituye `python` por
`.\.venv\Scripts\python.exe` si elegiste esta opcion.

El repositorio no tiene `.gitignore`: `.venv` y las salidas generadas no se ignoran
automaticamente. No subas el entorno virtual, los Excel ni las imagenes al
repositorio. Revisa los archivos antes de agregarlos a Git.

## Ejecucion

Desde la terminal abierta en la raiz del proyecto, ejecuta:

```powershell
python main.py
```

Cuando aparezca `Usuario de TikTok (con o sin @):`, escribe, por ejemplo,
`tiktok` o `@tiktok` y pulsa Enter. No pegues la URL del perfil. Si el nombre no
tiene un formato valido, el programa lo vuelve a pedir.

Espera a que termine y revisa los mensajes de la terminal. Puedes cancelar con
`Ctrl+C`. El programa intenta cerrar el navegador tambien ante errores o
cancelacion; cancelar antes de guardar puede dejarte sin los Excel completos.

Con el entorno virtual opcional, el comando es:

```powershell
.\.venv\Scripts\python.exe main.py
```

## Como funciona

1. Valida el usuario y abre su perfil publico en Chromium, con idioma ingles para
   interpretar los formatos numericos de los contadores.
2. Busca enlaces de videos del usuario solicitado, elimina duplicados y desplaza
   la pagina para cargar mas candidatos.
3. Deja de buscar al reunir al menos 20 candidatos, tras 3 lecturas consecutivas
   sin nuevos videos o al llegar a un maximo de 30 lecturas.
4. Ordena los candidatos por su identificador numerico de TikTok, de mayor a
   menor, y elige hasta 10. El identificador contiene informacion temporal; asi
   los fijados antiguos no desplazan a los recientes solo por estar arriba.
5. Visita cada video seleccionado en otra pagina del navegador para obtener sus
   interacciones. Comprueba que los datos correspondan al video solicitado.
6. Intenta descargar las imagenes y guarda los Excel de publicaciones y perfil.

La seleccion supone que TikTok carga el perfil en su orden habitual de
publicaciones recientes, no por popularidad. No revisa todo el historial ni
garantiza encontrar los 10 videos mas recientes de toda la cuenta. Si carga
menos de 10, exporta los disponibles sin duplicarlos y muestra un aviso. Esto
no demuestra que el perfil tenga menos publicaciones. Un video sin vistas o
miniatura sigue incluido.

Entre el final de una consulta de interacciones y la apertura del siguiente
video se esperan al menos 2 segundos (`VIDEO_DELAY_SECONDS`). Para 10 videos
hay 9 pausas: al menos 18 segundos adicionales al tiempo de carga y procesamiento.
No hay pausa adicional antes del primero ni despues del ultimo, y la espera
tambien se aplica tras un error recuperable.

Esta pausa no garantiza evitar bloqueos o suspensiones. No es un limite global
de solicitudes: no controla las peticiones internas del navegador, las descargas
de imagenes ni otras instancias del programa que ejecutes a la vez.

## Archivos generados

Las salidas se guardan en una carpeta con el usuario, sin `@`, relativa al
directorio actual de la terminal, no necesariamente al lugar donde esta
`main.py`. Si sigues esta guia, la carpeta queda en la raiz del proyecto.

Por ejemplo, para `tiktok` en la fecha `2026-10-19`:

```text
tiktok/
  tiktok_post_2026-10-19.xlsx
  tiktok_perfil_2026-10-19.xlsx
  2026-10-19_1.jpg
  2026-10-19_2.jpg
  ...
  imagen_cover.jpg
```

Las miniaturas se numeran del 1 hasta el numero de videos seleccionados, con un
maximo de 10. Solo aparecen las imagenes que se logren descargar. Se guardan los
bytes recibidos con nombre `.jpg`; esa extension no garantiza que se haya
convertido la imagen al formato JPEG. Son miniaturas o imagenes del perfil, no
capturas de pantalla ni archivos de video.

Repetir el mismo usuario el mismo dia sobrescribe los Excel y las miniaturas con
nombres coincidentes. `imagen_cover.jpg` se sobrescribe cuando se descarga de
nuevo, incluso en otro dia. No se limpian archivos antiguos que sobren. Si
necesitas conservar una ejecucion, respalda su carpeta antes de repetirla.

### Excel de publicaciones

Las columnas de `<usuario>_post_<fecha>.xlsx`, en su orden real, son:

| Columna exacta | Significado en espanol |
| --- | --- |
| `Video Links` | Enlace publico del video; su URL contiene el identificador real de TikTok. |
| `Views` | Cantidad de vistas leida en la tarjeta del perfil. |
| `image_id` | Nombre del archivo de miniatura descargado, o `Sin id` si no se guardo. |
| `id_post` | Identificador local con fecha de ejecucion y numero, por ejemplo `2026-10-19_1`. No es el ID real del video ni su fecha de publicacion. |
| `Likes` | Cantidad de corazones o Me gusta del video. |
| `Comments` | Cantidad de comentarios, sin su texto. |
| `Shares` | Cantidad de veces compartido. |
| `Saves` | Cantidad de guardados o favoritos. |
| `Metrics Error` | Motivo de un fallo o de contadores de interacciones ausentes; vacio si no se detecto un problema en esa consulta. |
| `id_perfil` | Usuario consultado, sin `@`. |

### Excel del perfil

Las columnas de `<usuario>_perfil_<fecha>.xlsx`, en su orden real, son:

| Columna exacta | Significado en espanol |
| --- | --- |
| `Followers` | Cantidad de seguidores. |
| `Following` | Cantidad de cuentas que sigue el perfil. |
| `Likes` | Cantidad total de corazones mostrada en el perfil, no la suma calculada de los videos seleccionados. |
| `Bio` | Texto de la biografia, o `N/A` si no se encontro el elemento. |
| `Profile Image` | Nombre de la imagen del perfil descargada (`imagen_cover.jpg`), o celda vacia si no se guardo. |
| `id_perfil` | Usuario consultado, sin `@`. |

### Como interpretar los datos

- `0` significa que se pudo leer un contador con valor cero. Una celda numerica
  vacia significa que no se obtuvo un valor valido; no equivale a cero.
- `Sin id` indica una miniatura no guardada. `N/A` indica que no se encontro el
  elemento de la biografia, no una cantidad numerica.
- Los contadores abreviados se convierten a enteros: `1.5K` pasa a `1500`,
  `2M` a `2000000` y `1B` a `1000000000`. Si la pagina muestra un numero
  redondeado, la conversion no recupera la cantidad exacta original.
- Los datos reflejan lo que cargo TikTok durante la consulta. No son un historial
  ni una garantia de exactitud o de disponibilidad completa. `Metrics Error`
  no informa de fallos de imagenes ni de todos los datos del perfil.

## Errores y restricciones

Un error recuperable al consultar un video, como un contador ausente o una carga
fallida sin restriccion detectada, se anota en `Metrics Error`. Se conservan los
valores disponibles y se continua con el siguiente video.

Si durante las consultas de interacciones se detecta HTTP 403/429, un CAPTCHA
visible conocido o una redireccion al inicio de sesion, se detienen las consultas
de videos. Se conservan los resultados obtenidos y se preparan las filas del
video afectado y de los pendientes con interacciones vacias y el motivo en
`Metrics Error`. El flujo continua hacia las descargas de imagenes y los Excel,
si no ocurre otro error: solo se detienen esas consultas de videos, no toda
actividad de red. No hay reintentos automaticos ni mecanismos para eludir el
bloqueo. Deten la ejecucion si corresponde y prueba mas tarde.

Si la restriccion aparece al cargar el perfil o buscar candidatos, el programa
puede terminar antes de generar los Excel. Los mensajes conocidos de perfil
privado o cuenta inexistente se muestran como errores. Si no se cargan enlaces,
se avisa sin afirmar que la cuenta no tenga publicaciones. La deteccion depende
del HTML y de los mensajes de TikTok: no cubre todas las variantes de perfiles
privados, cuentas inexistentes, CAPTCHA o bloqueos. Los cambios de TikTok pueden
hacer que los datos falten o que el programa deje de funcionar.

### Problemas de instalacion o guardado

- Si aparece un error de compilacion de `greenlet`, usa la instalacion con
  `--only-binary=:all:` indicada arriba. Si pip dice que no encuentra una version
  compatible, prueba Python 3.12 y, si usas un entorno virtual, crea uno nuevo
  con esa version. No hace falta empezar instalando Visual C++ para compilar.
- Si Playwright indica que falta el navegador, ejecuta
  `python -m playwright install chromium` con el mismo Python que usas para
  ejecutar `main.py`.
- Si no se puede guardar un Excel, cierralo en Excel u otro programa y comprueba
  los permisos de escritura de la carpeta. Un archivo abierto puede impedir
  sobrescribirlo.
- Si TikTok tarda demasiado o restringe el acceso, revisa la conexion y prueba
  mas tarde. El programa no garantiza completar la descarga.

## Pruebas locales

Con las dependencias instaladas, ejecuta desde la raiz:

```powershell
python -B -m unittest discover -s tests -v
```

Hay 26 pruebas con paginas y datos simulados: no consultan TikTok ni ejecutan
una descarga real. Comprueban seleccion de videos, contadores, errores,
restricciones, cierre del navegador y pausas. Una prueba incluye una espera real
de al menos 2 segundos para comprobar el intervalo. La opcion `-B` evita generar
archivos de cache de Python durante las pruebas. Superarlas no garantiza que
TikTok mantenga su pagina sin cambios.

## Estructura del repositorio

```text
main.py                      Programa principal.
requirements.txt             Dependencias de Python.
README.md                    Esta guia de uso.
GUIA_CODIGO.md                Explicacion linea por linea de main.py.
obtener_estadisticas.py       Script antiguo e independiente.
tests/
  test_recent_videos.py      Pruebas de seleccion de candidatos.
  test_interactions.py       Pruebas de contadores de interacciones.
  test_access_and_pacing.py  Pruebas de acceso, pausas y cierre.
```

La [Guia del codigo](GUIA_CODIGO.md) explica cada linea no vacia de `main.py`,
los conceptos basicos, el orden real de ejecucion y preguntas para una exposicion.
Es un documento de estudio; no es necesario leerlo para ejecutar el programa.

`obtener_estadisticas.py` es un legado que no se necesita para el flujo de
`main.py` y no esta actualizado. Tiene rutas fijas de otro equipo y usa un
selector antiguo para guardados (`undefined-count`). No se recomienda ejecutarlo
como paso de esta guia ni como complemento necesario para obtener interacciones.

Usa los datos publicos de forma responsable y respeta las condiciones de TikTok
y la privacidad de las personas.
