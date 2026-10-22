# TikTok: datos publicos y senales textuales Big Five

Recopila datos publicos de un perfil de TikTok y genera automaticamente tres
Excel originales y un cuarto Excel de analisis linguistico. Analiza la biografia
y los comentarios escritos, no el audio ni las imagenes de los videos.

Las cinco dimensiones son apertura, responsabilidad, extraversion, amabilidad y
neuroticismo. Los resultados son senales exploratorias del texto, no rasgos
demostrados del propietario, diagnosticos ni puntuaciones de personalidad.
No implementa BFI-2 ni tiene validacion psicometrica.

| Dimension teorica | Significado general |
| --- | --- |
| Apertura a la experiencia (Openness) | Curiosidad, imaginacion e interes por ideas o experiencias nuevas. |
| Responsabilidad o escrupulosidad (Conscientiousness) | Organizacion, constancia, planificacion y cumplimiento de compromisos. |
| Extraversion (Extraversion) | Sociabilidad, expresividad y preferencia por la interaccion. |
| Amabilidad (Agreeableness) | Cooperacion, empatia y consideracion en el trato interpersonal. |
| Neuroticismo o emocionalidad negativa (Neuroticism) | Tendencia a preocupacion y reactividad emocional, frente a estabilidad emocional. No equivale a un diagnostico. |

El programa busca expresiones relacionadas con esas dimensiones, no mide esas
caracteristicas en personas. Una emocion puntual no demuestra una tendencia estable.

## Instalacion En Windows

Usa Python 3.12 y Visual Studio Code. En VS Code, abre la carpeta completa del
proyecto, donde estan `main.py` y `requirements.txt`, y abre una terminal
PowerShell en esa carpeta. Ejecuta:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

En la paleta de comandos de VS Code, elige `Python: Select Interpreter` y
selecciona `.venv\Scripts\python.exe`. Los comandos de este documento usan ese
interprete directamente: no necesitas activar el entorno ni cambiar
`ExecutionPolicy`.

Las unicas dependencias directas de `requirements.txt` son:

- `pandas>=2.2,<4`: lectura y organizacion de tablas.
- `playwright>=1.50,<2`: navegador Chromium y paginas publicas.
- `openpyxl>=3.1,<4`: lectura y escritura de Excel.
- `beautifulsoup4>=4.12,<5`: extraccion alternativa de enlaces del HTML renderizado.

No se requieren `aiohttp`, `yt-dlp` ni dependencias para descargar videos.
La instalacion y la recopilacion necesitan Internet. El analisis predeterminado
funciona sin Ollama y no realiza conexiones de red.

## Recopilar Y Analizar

Para introducir el usuario cuando se solicite:

```powershell
.\.venv\Scripts\python.exe main.py
```

Escribe un nombre con o sin `@`, no la URL completa. Tambien puedes dar todos los
parametros en el comando:

```powershell
.\.venv\Scripts\python.exe main.py --usuario demo --videos 10 --comentarios 20 --pausa 2 --espera-comentarios 2 --enlaces auto --sin-ventana --salida "resultados\demo"
```

- `--usuario`: opcional; si falta, se solicita en consola.
- `--videos`: objetivo maximo de videos, 10 por defecto; entero positivo.
- `--comentarios`: objetivo maximo de comentarios por video, 20 por defecto; entero positivo.
- `--pausa`: segundos entre consultas de videos, 2 por defecto y minimo 2.
- `--espera-comentarios`: segundos entre intentos de carga del panel, 2 por defecto y minimo 2.
- `--enlaces`: `auto`, `playwright` o `beautifulsoup`; por defecto `auto`.
- `--sin-ventana`: ejecuta Chromium sin ventana; sin esta opcion se abre una ventana.
- `--salida`: directorio de resultados; por defecto, una carpeta con el nombre del usuario en el directorio actual.
- `--motor`: `heuristica` por defecto u `ollama`, que requiere un modelo local indicado con `--modelo`.
- `--modelo` y `--ollama-url`: configuracion opcional de Ollama, explicada mas adelante.

Si un usuario coincide con un nombre de archivo reservado de Windows, como `CON`,
se usa el prefijo `usuario_` para su carpeta y archivos, sin cambiar la cuenta consultada.

`configuracion.py` centraliza estos limites. Tambien establece esperas de 3
segundos entre desplazamientos del perfil, hasta 30 desplazamientos y 5 rondas
sin novedades; para comentarios, hasta 30 rondas, 8 sin novedades una vez que
hay comentarios y un plazo de 90 segundos por recolector. Los tiempos de
navegacion y selectores son de 30 segundos. Son limites de intentos, no una
promesa de recuperar todos los datos ni una duracion total fija.

Al terminar la recopilacion se exportan primero los datos originales y despues
se ejecuta el analisis, sin tener que lanzar otro script. Si falla el analisis,
los tres archivos originales ya guardados permanecen disponibles. `Ctrl+C`
cancela la ejecucion y conserva archivos completos ya guardados, pero no hay
guardado incremental: si cancelas antes de que termine la recopilacion, puede
no guardarse nada de esa ejecucion.

## Alcance De La Captura

Obtiene biografia, seguidores, seguidos y likes del perfil; enlaces, IDs, vistas
e interacciones de videos; y comentarios principales con texto. Los enlaces
encontrados se validan para el perfil solicitado, se deduplican y se ordenan por
ID de video descendente antes de aplicar el limite. Se intenta reunir un margen
de candidatos para reducir el efecto de videos fijados, sin garantizar que se
hayan cargado todas las publicaciones recientes.

Para cada video se intenta conservar los primeros 20 comentarios principales
validos segun el orden que presenta TikTok, o el limite configurado. No se afirma
que sean los mas recientes. Se comprueba el video asociado, se excluyen las
respuestas y se deduplica por `Comment ID`, conservado como texto. El orden se
reconstruye por cursor y orden de las respuestas observadas, no por la velocidad
con que termine de leerse cada respuesta.

El recolector observa respuestas que la propia pagina publica carga al navegar
y desplazar el panel. No genera peticiones adicionales a la API de comentarios,
no usa APIs privadas ni evita restricciones. HTTP 403/429, CAPTCHA o una
solicitud de inicio de sesion detienen las consultas restantes cuando se
detectan; no se intenta eludirlos. Los perfiles privados no son accesibles.
Las pausas no garantizan evitar bloqueos. Respeta las condiciones de TikTok y
la privacidad de quienes escriben los textos.

Si Chromium muestra `net::ERR_HTTP_RESPONSE_CODE_FAILURE`, se conserva el error
de navegacion original en lugar de intentar leer comentarios de la pagina anterior.
El listener tambien observa el documento del video: un HTTP 403/429 detiene el
lote aunque `goto` lance una excepcion sin devolver su respuesta. Si no se logra
observar el codigo HTTP de ese rechazo, se detiene por precaucion con estado
`error`, sin afirmar que sea un 403. No se reinician sesiones ni cookies para
saltarse el rechazo; prueba mas tarde, no mediante ejecuciones repetidas.

### Enlaces Con Playwright Y BeautifulSoup

Playwright es el navegador y cargador de JavaScript en todos los modos. El
extractor `playwright` consulta mediante JavaScript los atributos y contadores
del DOM vivo. El extractor `beautifulsoup` analiza una instantanea del HTML ya
renderizado, obtenida con `page.content()`, y normaliza enlaces relativos y
variantes validas de URL, incluso si no tienen contador de vistas.

En modo `auto`, BeautifulSoup sirve de rescate cuando Playwright lanza una
excepcion, no produce candidatos validos o deja de encontrar enlaces nuevos.
No es un cargador de JavaScript ni de red independiente, no evita restricciones
y no se usa para extraer comentarios. Las pruebas cubren esos casos de rescate.

### Estados Y Datos Ausentes

`Comments` es el contador total reportado por TikTok; `Comments Collected` es
el numero de textos capturados. No son intercambiables. `Comments Status` tiene
cinco estados:

| Estado | Significado |
| --- | --- |
| `completo` | Se alcanzo el objetivo configurado sin error del recolector. |
| `parcial` | Se conservaron comentarios, pero no se completo el objetivo o hubo un problema. |
| `sin_comentarios` | No hay captura ni error y existe evidencia de cero: contador cero o respuesta vacia final compatible con total ausente/cero. |
| `restringido` | Se detecto una restriccion; puede haber datos parciales previos. Los videos restantes no consultados conservan conteos de captura vacios, no ceros inventados. |
| `error` | No se obtuvieron comentarios y no hay evidencia suficiente para afirmar que no existen, o fallo la carga. |

`Comments Error`, `Metrics Error` y `Profile Error` describen problemas de carga.
Un contador ausente queda vacio: desconocido no significa cero. Si solo hay 12
comentarios disponibles, capturar esos 12 es util y no un fallo artificial; aun
asi, el objetivo de 20 no se alcanzo y el scraper informa `parcial`. Un cero
reportado tampoco cuenta respuestas o textos que no se hayan observado.

## Archivos Generados

Una ejecucion que completa captura, exportacion y analisis genera:

- `<usuario>_perfil_<TIMESTAMP>.xlsx`: hoja `perfil`, con `id_perfil`, `Bio`, `Followers`, `Following`, `Likes` y campos adicionales como `Profile Error`.
- `<usuario>_post_<TIMESTAMP>.xlsx`: hoja `posts`, con `Video Links`, `Video ID`, `Views`, `id_post`, `Likes`, `Comments`, `Shares`, `Saves`, `Metrics Error`, `Comments Collected`, `Comments Status`, `Comments Error` e `id_perfil`.
- `<usuario>_comentarios_<TIMESTAMP>.xlsx`: hoja `comentarios`, con `Video Links`, `Comment ID`, `Author Handle`, `Author`, `Comment Text`, `Comment Likes`, `Video ID` e `id_perfil`.
- `<usuario>_bigfive_<TIMESTAMP>.xlsx`: cinco hojas de analisis descritas abajo.

`TIMESTAMP` usa `AAAAMMDD_HHMMSS_microsegundos`. Los tres originales comparten
marca; el analisis tiene la suya. Si un nombre ya existe se agrega un sufijo
numerico, sin sobrescribir. No se descargan imagenes de perfil, miniaturas ni
MP4. Los antiguos scripts de descarga y estadisticas separados fueron retirados;
no forman parte del flujo actual.

### Conservacion Del Texto En Excel

Se conservan Unicode, emojis, vacios e identificadores como texto, sin convertir
IDs a flotantes. El lector offline rechaza IDs numericos Excel cuya precision
ya no es fiable; convertir despues un numero redondeado a texto no lo repara.
Todos los textos, incluidas cabeceras y valores que parecen formulas, se escriben
con tipo de celda texto para evitar su ejecucion como formulas.

La codificacion reversible duplica las barras invertidas y representa controles
no validos para XML mediante secuencias `\uXXXX`. La constante `TEXT_ENCODING`
vale `tiktok_text_escape:backslash_u_v1` y se guarda en la propiedad
`description` del libro. Esa propiedad es la marca autoritativa: el lector
offline aplica `_restore_text` una sola vez, de izquierda a derecha, solamente
si coincide. No se deben decodificar archivos antiguos sin esa marca ni decidir
por el aspecto de una celda o por el texto de la hoja `Metodologia`.

Si un texto escapado supera el limite de Excel de 32767 unidades UTF-16, la
exportacion falla con un error: nunca lo trunca silenciosamente. Cierra libros
abiertos si Windows informa un problema de permisos al guardar.

## Analizar Archivos Existentes

No requiere visitar TikTok ni tener Chromium abierto. Indica los tres archivos
originales reales; se admiten Excel y CSV, leyendo la primera hoja en Excel:

```powershell
.\.venv\Scripts\python.exe analisis_bigfive.py --perfil "demo\demo_perfil_TIMESTAMP.xlsx" --comentarios "demo\demo_comentarios_TIMESTAMP.xlsx" --posts "demo\demo_post_TIMESTAMP.xlsx" --salida "resultados\offline" --comentarios-objetivo 20 --videos-objetivo 10
```

`--perfil`, `--comentarios` y `--posts` son obligatorios. Sustituye `TIMESTAMP`
por la marca de tus archivos. `--salida` es opcional; por defecto se escribe
junto al archivo de perfil. Los objetivos predeterminados son 20 y 10: sirven
para describir cobertura, no recortan la entrada offline. Se crea un nuevo
Excel Big Five sin modificar los originales.

El perfil debe contener exactamente una fila con `id_perfil` y `Bio`; posts
requiere `Video Links`; comentarios requiere `Video Links`, `Comment ID` y
`Comment Text`. Los archivos vacios de posts o comentarios necesitan sus
cabeceras. Se comprueban URLs del propietario, correspondencia de IDs y videos,
y duplicados conflictivos. Duplicados identicos de comentarios se descartan y
se contabilizan. En archivos antiguos sin `Comments Status`, el estado se
infiere segun el objetivo y se advierte esa limitacion.

## Como Se Interpreta

La biografia se analiza por separado, con un resultado independiente por cada
dimension. Es autopresentacion, no evidencia equivalente a comentarios de la
audiencia. Una biografia ausente o corta incluye advertencias de contexto; el
umbral descriptivo de texto corto no es una validacion de suficiencia.

Los comentarios se separan en `propietario`, `audiencia` y `sin_identificar`.
Solo `Author Handle` identifica al autor: se compara con `id_perfil` ignorando
mayusculas y el `@` inicial. `Author` es un nombre visible o nickname y NUNCA
identifica al propietario. Un archivo antiguo con solo `Author`, o con handle
ausente/no fiable, va a `sin_identificar`, no automaticamente a audiencia.

El origen indica quien escribio, no a quien describe el texto. `referencia`
distingue `autorreferencia`, `percepcion_tercero`, `autopresentacion`,
`opinion_video` e `irrelevante`. Un comentario de audiencia puede describir a
otra persona; no se transforma en personalidad del propietario ni del grupo.

### Motor Predeterminado

La heuristica usa frases y reglas publicas inspeccionables en `motor_bigfive.py`:
`RULES`, `_ADJECTIVES` y `_make_rules`, version `heuristica_v1`. Es un diccionario
de patrones del proyecto, no un instrumento cientificamente validado. Cubre
expresiones concretas en espanol y un subconjunto limitado en ingles, no todas
las formas de decir lo mismo ni todos los idiomas.

Normaliza mayusculas, acentos y espacios para buscar, conservando intervalos
(offsets) hacia el original para devolver citas literales sin reescribirlas.
Trata negaciones simples, se abstiene ante varios contextos ambiguos y marca
`mixta` cuando encuentra ambos polos de una dimension con referencia compatible.
No mezcla referencias a sujetos distintos en una misma dimension. Ironia,
sarcasmo, negaciones complejas y contexto siguen siendo limites: revisa las citas.

Emojis solos, una profesion sola o una palabra aislada no justifican inferir
rasgos. `Hoy estoy triste` no demuestra neuroticismo; un mensaje positivo o
`Buen video` no demuestra amabilidad. Por ejemplo, `Soy sociable` puede producir
una senal de extraversion con cita literal, mientras `Soy sociable, soy reservado`
puede dar direccion mixta. La biografia `Creativa, organizada` puede contener
senales independientes de apertura y responsabilidad.

`positiva` y `negativa` indican el polo textual alto o bajo de la dimension,
no sentimiento positivo/negativo, valor moral ni una puntuacion de la persona.
`sin evidencia suficiente` es abstencion, no prueba de ausencia del rasgo.
`Comment Likes` se conserva como metadato: no se envia al motor ni pondera
senales o porcentajes.

### Hojas Del Analisis

- `Biografia`: cinco filas con `Bio`, `dimension`, `senal`, `direccion`, `evidencia`, `explicacion`, `metodo`, `estado` y `referencia`; tambien `Estado_Analisis`, longitudes, `Bio_Ausente`, `Error_Motor` y `Limitaciones`.
- `Comentarios_Analizados`: una fila por comentario deduplicado, con texto original, video, ID, autor, likes, `Origen`, `Estado_Analisis` y `Error_Motor`. Cada dimension tiene columnas con sufijos `_senal`, `_direccion`, `_evidencia`, `_explicacion`, `_metodo`, `_estado` y `_referencia`.
- `Resultados_por_Video`: formato largo, 15 filas por video (cinco dimensiones por tres origenes), con `Dimension`, `Origen`, disponibilidad, contador reportado, objetivo, estado de captura, duplicados, conteos de analisis, porcentajes, `Ejemplos_Literales` y limitaciones.
- `Resumen_General`: 15 filas en total (cinco dimensiones por tres origenes) para toda la muestra; incluye objetivos, videos, totales conocidos/desconocidos, captura global, cobertura, conteos del grupo y ejemplos literales.
- `Metodologia`: pares `Campo`/`Valor` con motor, modelo, endpoint, fecha UTC, configuracion, version y ubicacion de reglas, dimensiones, fuentes de texto, denominadores, errores, codificacion Excel y limites de interpretacion.

`evidencia` y `Ejemplos_Literales` contienen listas JSON de citas del original;
los ejemplos de comentarios incluyen su `Comment ID` y hasta tres comentarios
con senales por grupo/dimension. No hay citas inventadas ni intervalos numericos
exportados como si fueran mediciones; los offsets se usan internamente para
recuperar el fragmento literal.

### Porcentajes Y Cobertura

Para cada dimension y grupo, `Proporcion = Con_Senales / Analizados` y
`Porcentaje = 100 * Con_Senales / Analizados`. Solo entran en el denominador
comentarios no vacios cuyo analisis termino correctamente. Un mismo comentario
puede tener senales en las cinco dimensiones; los porcentajes no tienen que
sumar 100. Sin denominador, la celda queda vacia, no en cero.

`Estado_Analisis` distingue `analizado`, `sin_texto` y `error_motor`.
`Errores_Motor` y `Error_Motor` registran fallos aparte: no se cuentan como
analisis validos sin senales, no se fabrica evidencia y no se presenta el fallo
como una abstencion sustantiva. Consulta el estado y el error antes de interpretar
las columnas de cada dimension.

`Cobertura_Analisis = Analizados / Capturados` corresponde al grupo.
`Cobertura_Captura_Objetivo = Capturados_Total / (Videos_Objetivo *
Comentarios_Objetivo_Por_Video)` compara la captura con el objetivo global,
normalmente 200 comentarios. Es una razon descriptiva, no una probabilidad,
confianza estadistica ni cobertura de todos los comentarios disponibles. Puede
superar 1 (100%) si la entrada offline supera los objetivos.

`Comments_Reportados`, `Subtotal_Reportado_Conocido`, `Videos_Total_Desconocido`
y `Disponibilidad` separan totales conocidos de disponibilidad desconocida.
Capturar 12 de 12 disponibles no equivale a fallar la captura, aunque sea menos
que el objetivo de 20. No se inventa el resto hasta llegar a 200.

Los totales de video/globales se repiten en las filas por dimension y origen;
los conteos del grupo tambien se repiten por dimension. NO sumes esos valores
repetidos como si fueran comentarios o videos distintos. La muestra es de
conveniencia, sesgada por lo que TikTok muestra y permite cargar; no permite
generalizar prevalencias ni estimar personalidad.

## Ollama Opcional

El proyecto no instala Ollama, no inicia su servicio y no descarga modelos.
No requiere APIs pagadas. Para usarlo, instala y prepara manualmente Ollama
fuera de este flujo, con un modelo ya disponible en tu equipo. Consulta los
nombres locales y, si el servicio no esta iniciado, arrancalo:

```powershell
ollama list
ollama serve
```

Si `ollama serve` queda en primer plano, usa otra terminal para el proyecto.
Elige un nombre exacto de `ollama list`; `NOMBRE_LOCAL` es un marcador, no un
modelo que el programa vaya a instalar. En la captura automatica:

```powershell
.\.venv\Scripts\python.exe main.py --usuario demo --motor ollama --modelo NOMBRE_LOCAL --ollama-url http://127.0.0.1:11434
```

Para los mismos archivos originales en modo offline:

```powershell
.\.venv\Scripts\python.exe analisis_bigfive.py --perfil "demo\demo_perfil_TIMESTAMP.xlsx" --comentarios "demo\demo_comentarios_TIMESTAMP.xlsx" --posts "demo\demo_post_TIMESTAMP.xlsx" --motor ollama --modelo NOMBRE_LOCAL --ollama-url http://127.0.0.1:11434
```

Ambas CLI aceptan las mismas opciones de motor. Solo se admiten endpoints
HTTP/HTTPS loopback (`localhost`, `127.0.0.1` o `::1`), sin credenciales, query
ni fragmento. Se rechazan redirecciones y se deshabilitan proxies de entorno.
El texto se envia al servicio local elegido; no a un proveedor externo.

Se solicita temperatura 0, semilla 42 y salida JSON estructurada con exactamente
cinco dimensiones. El backend valida tipos, coherencia y citas literales del
original de al menos dos palabras. Los comentarios se presentan como datos no
confiables, no como instrucciones; no se ejecutan instrucciones incluidas en
ellos. Estas medidas no garantizan que el modelo interprete bien cada texto ni
eliminan todos los riesgos de instrucciones maliciosas o errores semanticos.

Si el servicio, el modelo o la respuesta fallan, las filas muestran `error_motor`
y su detalle, con recuentos en las hojas y metodologia. No hay sustitucion
silenciosa por heuristica. Temperatura y semilla no garantizan resultados
identicos entre modelos, versiones o equipos, ni validez psicometrica.

## Pruebas

Con las dependencias y Chromium ya instalados:

```powershell
.\.venv\Scripts\python.exe -B -W error::RuntimeWarning -m unittest discover -s tests -v
```

La suite usa respuestas simuladas e interceptadas, sin contactar TikTok. Incluye
una prueba con Chromium real y paginas interceptadas, por lo que requiere el
navegador instalado por Playwright. Comprueba recopilacion, orden, deduplicacion,
restricciones, pausas, rescate de enlaces, exportacion segura, analisis y CLI.
Ollama se prueba con mocks, no con modelos reales. Aprobar estas pruebas no
garantiza que TikTok permita la captura ni que sus selectores o respuestas no
cambien, y tampoco demuestra exactitud psicologica del analisis.

## Archivos Del Proyecto

- `main.py`: CLI de recopilacion y coordinacion de los cuatro Excel.
- `configuracion.py`: valores predeterminados y validacion de limites y pausas.
- `scraper.py`: paginas publicas, enlaces, interacciones y comentarios.
- `exportacion.py`: Excel originales, nombres unicos y texto reversible seguro.
- `analisis_bigfive.py`: analisis compartido, lectura offline, grupos, resumenes y cinco hojas.
- `motor_bigfive.py`: reglas publicas y motor heuristico sin red.
- `ollama_bigfive.py`: adaptador local opcional y validacion de respuestas.
- `requirements.txt`: las cuatro dependencias directas.
- `tests/`: pruebas unitarias y flujo de navegador con datos simulados.
