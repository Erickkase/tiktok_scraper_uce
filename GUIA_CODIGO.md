# Guia del codigo para explicar el proyecto

Esta guia explica el programa que realmente se ejecuta: [`main.py`](main.py).
Esta basada en su version de 317 lineas. No se modifico el programa para escribir
esta explicacion. Si mas adelante se agregan lineas, habra que actualizar las
referencias. Puedes activar los numeros de linea en tu editor para seguirla.

Se explica cada linea no vacia, incluidas las que cierran estructuras. Las lineas
en blanco solo separan bloques para facilitar la lectura y no realizan acciones.
La instalacion y los ejemplos de uso estan en el [README](README.md).

## 1. Que puedes decir al presentar el proyecto

> Mi programa recibe un usuario de TikTok, abre su perfil publico con un navegador
> controlado desde Python y recopila sus seguidores, seguidos y hasta diez videos
> recientes. Para cada video intenta obtener visualizaciones, corazones, cantidad
> de comentarios, compartidos y guardados. Guarda los resultados en dos archivos
> Excel y descarga las miniaturas y la imagen del perfil. Espera al menos dos
> segundos entre las consultas de videos. No utiliza extensiones y no intenta
> evitar restricciones de TikTok.

La palabra "comentarios" significa por ahora **cantidad de comentarios**. No se
descargan sus textos. Tampoco se descargan los archivos de los videos completos.
Los datos estructurados de la propia pagina son una fuente para los contadores;
no estamos utilizando una API oficial ni calculando interacciones nuevas.

## 2. Conceptos necesarios

| Concepto | Explicacion sencilla |
| --- | --- |
| Scraping | Recopilar informacion de una pagina mediante un programa. |
| Playwright | Biblioteca que permite controlar un navegador: abrir paginas, desplazarse y leer elementos. |
| Chromium | Navegador que controla Playwright. No es una extension. |
| HTML y DOM | HTML describe la pagina; el DOM es la estructura de elementos que el navegador permite consultar. |
| Selector | Regla para encontrar un elemento. Por ejemplo, `[data-e2e="like-count"]` busca el elemento con ese atributo. |
| `data-e2e` | Atributo que TikTok coloca en algunos elementos. El programa lo usa para localizarlos; puede cambiar. |
| JSON | Texto con datos organizados en objetos y listas. TikTok incluye datos de este tipo dentro de la pagina. |
| Variable | Nombre asociado a un valor, como `username` o `videos`. |
| Lista | Coleccion ordenada de elementos, como los diez videos elegidos. |
| Diccionario | Coleccion de claves y valores. Por ejemplo, `{'Likes': 20}`. |
| Tupla | Grupo de valores que se usan juntos. Cada interaccion tiene una clave JSON y un selector. |
| `None` | Ausencia de dato; no significa cero. |
| Funcion | Bloque con nombre que realiza una tarea cuando se llama. Definirla no la ejecuta. |
| `async def` | Define una funcion asincrona, que puede esperar operaciones sin bloquear el bucle de eventos. |
| `await` | Espera el resultado de una operacion asincrona antes de seguir esa secuencia. |
| Bucle de eventos | Mecanismo que coordina las operaciones asincronas de `asyncio`. |
| `try` y `except` | Intentan una operacion y atienden errores determinados. |
| `raise` | Comunica un error para que otra parte del programa lo gestione. |
| `finally` | Ejecuta la limpieza al salir de un bloque, incluso si hubo un error. |
| `with` y `async with` | Administran recursos y su limpieza al terminar de usarlos. |
| `return` | Termina una funcion y devuelve un resultado. |
| `break` | Sale del bucle actual. |
| DataFrame | Tabla de pandas que luego se puede guardar en Excel. |
| HTTP 200 | La solicitud recibio una respuesta satisfactoria; no garantiza que contenga los datos esperados. |
| HTTP 403 | Acceso rechazado. |
| HTTP 429 | Demasiadas solicitudes o limitacion de frecuencia. |
| Tiempo de espera | Limite para esperar una operacion; no es una pausa obligatoria. |

Aunque se usa `asyncio`, las consultas de estos videos se hacen **una por una**.
No se lanzan diez consultas simultaneas. La pausa de dos segundos y los tiempos
maximos de espera son cosas diferentes: una pausa espera deliberadamente;
un tiempo maximo permite continuar antes si la operacion ya termino.

## 3. Orden real de ejecucion

Python primero carga las importaciones, constantes y definiciones. Al ejecutar
`python main.py`, llega al bloque de la linea 298 y sigue este recorrido:

```text
Pedir usuario y validarlo (lineas 298-305)
    |
    v
asyncio.run(main(username)) (linea 306)
    |
    v
main: iniciar Playwright (lineas 294-296)
    |
    v
run: abrir Chromium y garantizar su cierre (lineas 287-292)
    |
    v
scrape_profile (lineas 203-285)
    |
    +--> Abrir y comprobar el perfil
    +--> collect_recent_videos: elegir hasta 10 videos
    +--> Crear la carpeta y una pagina para las metricas
    +--> collect_video_interactions: consultar los videos con pausas
    +--> Descargar miniaturas y armar las filas
    +--> Guardar el Excel de publicaciones
    +--> Leer los datos del perfil y descargar su avatar
    +--> Guardar el Excel del perfil
    |
    v
Cerrar Chromium en finally
```

Las funciones auxiliares pueden aparecer antes que `main` en el archivo, pero
no se ejecutan en ese orden: se ejecutan cuando otra funcion las llama.

## 4. Importaciones y configuracion: lineas 1-22

| Linea | Que hace y para que sirve |
| --- | --- |
| 1 | Importa `asyncio`, usado para iniciar el bucle de eventos y esperar entre videos. |
| 2 | Importa `json`, que convierte el texto JSON de la pagina en datos de Python. |
| 3 | Importa `re`, para buscar y validar patrones de texto mediante expresiones regulares. |
| 4 | Importa `sys`, utilizado para terminar el programa con un codigo de error. |
| 5 | Importa el administrador asincrono de Playwright y sus errores. Los alias `PlaywrightError` y `PlaywrightTimeoutError` permiten reconocerlos con nombres claros. |
| 6 | Importa `os`, que permite construir rutas y crear carpetas. |
| 7 | Importa `aiohttp`, usado para descargar imagenes mediante solicitudes HTTP asincronas. |
| 8 | Importa `aiofiles`, usado para escribir las imagenes en disco de forma asincrona. |
| 9 | Importa pandas con el alias `pd`, usado para construir tablas y exportarlas. |
| 10 | Importa `datetime`, para obtener la fecha local del equipo. |
| 12 | Define `VIDEO_DELAY_SECONDS = 2`: la espera entre consultas de videos. No controla todas las solicitudes internas del navegador. |
| 13 | Abre `INTERACTION_FIELDS`, un diccionario que relaciona las columnas del Excel con las fuentes de datos de TikTok. |
| 14 | Para `Likes`, establece `diggCount` como clave JSON y `like-count` como atributo del contador visible. |
| 15 | Para `Comments`, establece `commentCount` y `comment-count`. Se trata de una cantidad, no del texto de comentarios. |
| 16 | Para `Shares`, establece `shareCount` y `share-count`. |
| 17 | Para `Saves`, establece `collectCount` y `favorite-count`. Este ultimo identifica el contador visible de guardados. |
| 18 | Cierra el diccionario de interacciones. |
| 21 | Define una clase de error propia llamada `ScrapingRestrictedError`, derivada de `RuntimeError`. Permite distinguir una restriccion de un fallo recuperable de un video. |
| 22 | `pass` indica que la clase no necesita instrucciones adicionales; su utilidad esta en su tipo y nombre. |

Por ejemplo, la relacion de `Likes` se puede leer asi:

```text
Columna que guardo: Likes
Clave que busco en los datos JSON: diggCount
Atributo que busco si necesito leer el contador visible: like-count
```

## 5. Comprobar acceso: lineas 25-48

| Linea | Que hace y para que sirve |
| --- | --- |
| 25 | Define `check_page_access`. Recibe una pagina y, opcionalmente, la respuesta HTTP de su navegacion. |
| 26 | Comprueba si existe una respuesta y si su estado es 403 o 429. |
| 27 | Empieza a lanzar un error especial de restriccion. |
| 28 | Construye el mensaje con el codigo HTTP. La `f` permite insertar `response.status` en el texto. |
| 29 | Cierra la construccion del error iniciado en la linea 27. |
| 30 | Comprueba otros estados HTTP de error, desde 400 en adelante. Los casos 403/429 ya se trataron antes. |
| 31 | Lanza un error de pagina no disponible para esos otros estados. |
| 32 | Empieza a construir un localizador para elementos conocidos de verificacion. Un localizador representa una busqueda, no una descarga. |
| 33 | Indica varios selectores de CAPTCHA separados por comas; basta con que un elemento corresponda a alguno de ellos. |
| 34 | Termina el localizador y selecciona su primera coincidencia con `.first`. |
| 35 | Espera la comprobacion de si esa coincidencia es visible. |
| 36 | Si la verificacion es visible, lanza el error especial para detener las consultas de videos. No intenta resolver el CAPTCHA. |
| 37 | Comprueba si la URL actual contiene `/login`. |
| 38 | Si TikTok redirigio al inicio de sesion, comunica una restriccion. No ingresa credenciales automaticamente. |
| 39 | Empieza a buscar un mensaje de cuenta privada. |
| 40 | Define variantes del mensaje en ingles y espanol. `re.I` ignora mayusculas; `(?:currently )?` permite esa palabra opcional. |
| 41 | Selecciona la primera coincidencia del mensaje. |
| 42 | Comprueba si el mensaje es visible. |
| 43 | Si lo es, informa que el perfil es privado mediante `ValueError`. |
| 44 | Empieza a buscar mensajes de cuenta inexistente. |
| 45 | Define algunas variantes conocidas de ese mensaje y vuelve a ignorar mayusculas. |
| 46 | Selecciona la primera coincidencia. |
| 47 | Comprueba si el mensaje de cuenta inexistente es visible. |
| 48 | Si lo es, informa que se debe comprobar el usuario. |

Esta funcion no puede reconocer todos los bloqueos posibles. TikTok puede cambiar
sus selectores o sus mensajes. Tampoco inspecciona todos los errores de cada
solicitud interna de la pagina: comprueba la respuesta de navegacion recibida y
algunas senales conocidas del contenido.

## 6. Validar el usuario: lineas 50-57

| Linea | Que hace y para que sirve |
| --- | --- |
| 50 | Define la funcion normal `normalize_username`, que recibe el texto ingresado. No necesita `async` porque solo trabaja con texto. |
| 51 | `strip()` elimina espacios al principio y al final. `removeprefix('@')` quita un unico `@` inicial si existe. |
| 52 | Exige de 1 a 24 caracteres. El primero debe ser letra ASCII, numero o guion bajo; los restantes tambien pueden ser puntos. Rechaza un punto final. |
| 53 | Empieza a lanzar `ValueError` cuando la validacion falla. |
| 54 | Primera parte del mensaje que explica longitud y caracteres permitidos. |
| 55 | Segunda parte del mensaje: no acepta enlaces ni un punto inicial o final. Las dos cadenas consecutivas se unen en Python. |
| 56 | Cierra la construccion del error. |
| 57 | Devuelve el usuario sin espacios externos ni `@` inicial. |

Ejemplos: ` @tiktok ` se convierte en `tiktok`; `@@tiktok` y una URL completa se
rechazan. La validacion solo comprueba el formato: **no demuestra que la cuenta
exista**. La existencia se intenta comprobar al visitar TikTok.

## 7. Convertir contadores: lineas 59-65

| Linea | Que hace y para que sirve |
| --- | --- |
| 59 | Define `convert_views`. Aunque conserva ese nombre, tambien convierte seguidores e interacciones. |
| 60 | Convierte el dato a texto, quita espacios externos, pasa letras a mayusculas y elimina comas usadas como separadores de miles en formato ingles. |
| 61 | Busca un numero con parte decimal opcional y un sufijo opcional K, M o B. Los parentesis capturan numero y sufijo por separado. |
| 62 | Rechaza formatos no reconocidos y decimales sin sufijo, porque un contador entero no deberia ser `1.5`. La segunda condicion solo se evalua si hubo coincidencia. |
| 63 | Comunica el texto que no pudo convertir. No lo reemplaza por cero. |
| 64 | Separa la coincidencia en `number` y `suffix`. |
| 65 | Si hay sufijo, multiplica por mil, un millon o mil millones y convierte a entero. Si no hay sufijo, convierte directamente a entero. |

```text
"1.2K"  -> 1200
"2M"    -> 2000000
"1,234" -> 1234
"0"     -> 0
None    -> error de conversion, no cero
```

La conversion no recupera precision perdida: si TikTok muestra `1.2K`, el resultado
es una aproximacion de lo mostrado. Se utiliza formato numerico ingles; no debe
interpretarse `1,2K` como un decimal con coma. No admite todos los idiomas o sufijos.

## 8. Descargar imagenes: lineas 67-84

| Linea | Que hace y para que sirve |
| --- | --- |
| 67 | Define `download_image`, que recibe la URL de una imagen, su carpeta de destino y el nombre del archivo. |
| 68 | Rechaza una direccion de texto que no comience por `http`. Los llamadores comprueban que exista una URL antes de llamar a esta funcion. |
| 69 | Muestra la direccion invalida. Este mensaje del codigo original sigue en ingles. |
| 70 | Devuelve `None` para indicar que no se descargo una imagen. |
| 71 | Inicia el bloque que controla los errores de descarga y escritura. |
| 72 | Crea una sesion HTTP asincrona. El administrador de contexto la libera al salir del bloque. Se crea una por llamada, no una sesion compartida para todas las imagenes. |
| 73 | Solicita la imagen mediante GET y administra la respuesta dentro de otro contexto. |
| 74 | Comprueba si la respuesta fue HTTP 200. |
| 75 | Lee el contenido de la respuesta como bytes, que son los datos binarios del archivo. |
| 76 | Une carpeta y nombre con `os.path.join`; abre el archivo en modo `wb`, escritura binaria. Si ya existe, se sobrescribe. |
| 77 | Escribe los bytes descargados. No transforma ni convierte la imagen. |
| 78 | Devuelve el nombre del archivo guardado para referenciarlo en Excel. |
| 79 | Abre la alternativa para respuestas distintas de 200. |
| 80 | Muestra el codigo HTTP de la descarga fallida. |
| 81 | Devuelve `None` porque no se guardo una imagen valida. |
| 82 | Captura errores ordinarios de la solicitud o del archivo. |
| 83 | Muestra la explicacion del error. |
| 84 | Devuelve `None` para que la falta de una imagen no interrumpa por si sola la recopilacion. |

Los nombres terminan en `.jpg`, pero esta funcion guarda los bytes tal como llegan:
**no convierte el formato de la imagen a JPEG**. Tampoco descarga el archivo MP4
del video. Descarga la miniatura o el avatar.

## 9. Elegir videos recientes: lineas 86-128

| Linea | Que hace y para que sirve |
| --- | --- |
| 86 | Define `collect_recent_videos`, que trabaja en la pagina del perfil solicitado. |
| 87 | Inicia el intento de esperar enlaces de videos. |
| 88 | Espera hasta 60000 milisegundos, es decir, 60 segundos, por un enlace cuyo `href` contenga `/video/`. Puede continuar antes si ya aparece. |
| 89 | Atiende el caso en que esa espera alcanza su limite. |
| 90 | Vuelve a comprobar restricciones o mensajes del perfil antes de interpretar la ausencia de enlaces. |
| 91 | Informa que no se cargaron videos publicos, sin afirmar que la cuenta este vacia. |
| 92 | Devuelve una lista vacia. Si la comprobacion anterior lanzo un error, no se llega a esta linea. |
| 93 | Crea el diccionario `videos`, que usara el ID numerico como clave para no repetir videos. |
| 94 | Inicia el contador de lecturas consecutivas que no agregan videos nuevos. |
| 95 | Empieza a compilar el patron de URL permitido. |
| 96 | Exige el dominio y la ruta del usuario solicitado, captura el ID numerico y permite una parte final de parametros o fragmento. `re.escape(username)` evita interpretar los puntos del usuario como reglas de la expresion regular. |
| 97 | Hace que la comparacion ignore mayusculas y minusculas. |
| 98 | Termina la construccion del patron. |
| 99 | Limita el proceso a 30 lecturas del contenido. `_` indica que no se usa el numero de iteracion. |
| 100 | Comprueba restricciones antes de cada lectura del perfil. |
| 101 | Encuentra enlaces de videos y ejecuta una funcion JavaScript en el navegador para leerlos juntos. |
| 102 | `map` transforma cada enlace en un objeto con la informacion que interesa. Es JavaScript, no Python. |
| 103 | Busca el contenedor de publicacion mas cercano al enlace mediante el atributo `user-post-item`. |
| 104 | Si no lo encuentra, intenta un contenedor con clase que contenga `DivContainer`; si tampoco existe, usa el enlace como ultimo recurso. El operador OR de JavaScript representa estas alternativas. |
| 105 | Busca el contador de visualizaciones dentro de ese contenedor. |
| 106 | Busca una etiqueta de imagen dentro del mismo contenedor. |
| 107 | Empieza a devolver el objeto de datos de ese enlace. |
| 108 | Guarda la direccion absoluta del enlace. |
| 109 | Si existe contador, obtiene su texto sin espacios externos; si no, utiliza `null`, que llegara a Python como `None`. |
| 110 | Si existe imagen, toma la URL que esta usando el navegador o su `src`; si no, guarda `null`. |
| 111 | Cierra el objeto JavaScript. |
| 112 | Cierra la transformacion y la llamada. Playwright convierte el resultado en listas y diccionarios de Python. |
| 113 | Recuerda cuantos videos unicos habia antes de procesar los candidatos de esta lectura. |
| 114 | Recorre los candidatos extraidos del DOM. |
| 115 | Comprueba la URL completa contra el patron permitido. |
| 116 | Solo procesa la URL si coincide con el dominio, usuario y ruta esperados. |
| 117 | Convierte a entero el ID capturado. Ordenar numeros evita errores del orden alfabetico de las cadenas. |
| 118 | Reconstruye una URL limpia, sin parametros de seguimiento. |
| 119 | Guarda el candidato bajo su ID. Si ya estaba, actualiza esa entrada en lugar de duplicarla. |
| 120 | Si no crecio el diccionario, aumenta `unchanged`; si aparecieron videos nuevos, reinicia el contador a cero. |
| 121 | Comentario que explica por que se cargan candidatos adicionales: contemplar publicaciones fijadas antiguas. |
| 122 | Comprueba si hay al menos 20 candidatos unicos o si hubo tres lecturas consecutivas sin nuevos videos. |
| 123 | Si se cumple alguna condicion, termina el bucle. |
| 124 | Si se necesita seguir, desplaza la pagina verticalmente 2000 unidades. |
| 125 | Espera 2000 milisegundos para dar tiempo a que se cargue contenido adicional. Esta espera es distinta de la pausa entre consultas de videos. |
| 127 | Comentario que explica el criterio temporal de los IDs y por que la posicion de un video fijado no basta para ordenarlo. |
| 128 | Ordena los IDs de mayor a menor, toma como maximo diez y devuelve sus diccionarios. `[:10]` es el recorte que limita la cantidad exportada. |

La lectura puede encontrar mas de 20 candidatos de una sola vez; 20 es una
condicion para dejar de cargar, no un recorte previo de cada lectura. El limite de
diez se aplica al final. Un video sin vistas o imagen sigue siendo candidato.

Este criterio supone que el perfil carga en el orden habitual de publicaciones
recientes. Ordena los **candidatos recopilados**, no demuestra que TikTok haya
entregado todos los videos mas recientes. No se descarga una fecha de publicacion
para verificar independientemente ese orden.

## 10. Leer interacciones de un video: lineas 130-180

| Linea | Que hace y para que sirve |
| --- | --- |
| 130 | Define `get_video_interactions`, que consulta un video en una pagina del navegador. |
| 131 | Crea un resultado con las cuatro interacciones inicialmente en `None`. |
| 132 | Inicia `Metrics Error` como texto vacio: aun no se ha registrado ningun problema. |
| 133 | Abre el bloque que intenta navegar y extraer los datos. |
| 134 | Visita el video con un limite de 30 segundos. `domcontentloaded` espera que el documento inicial este listo, no que terminen todas las solicitudes de la pagina. |
| 135 | Comprueba la respuesta y las senales conocidas de restriccion. |
| 136 | Empieza una espera por los datos necesarios para intentar la extraccion. |
| 137 | Acepta como senal el bloque JSON de rehidratacion de TikTok o el contador visible de corazones. |
| 138 | Espera que alguna senal exista en el DOM, aunque no sea visible, durante un maximo de 15 segundos. |
| 139 | Cierra la llamada de espera. |
| 140 | Comprueba de nuevo si aparecio una restriccion durante la carga. |
| 141 | Extrae el ID esperado del ultimo segmento de la URL recibida. Las URL vienen limpias desde la seleccion del perfil. |
| 142 | Busca un ID de video en la URL actual del navegador. |
| 143 | Detecta que no hay ID o que no coincide con el solicitado. |
| 144 | En ese caso, evita atribuir al video contadores de una pagina diferente. |
| 146 | Inicia el diccionario de estadisticas encontradas en datos estructurados. |
| 147 | Busca el elemento que contiene el JSON incluido por TikTok. |
| 148 | Solo intenta interpretarlo si existe. |
| 149 | Inicia el control local de errores del JSON. Un JSON inutilizable no impide intentar leer los contadores visibles. |
| 150 | Lee el texto del elemento y usa `json.loads` para convertirlo en datos de Python. |
| 151 | Recorre las claves de la estructura hasta `itemStruct`, el objeto del video. Los valores por defecto `{}` permiten tratar claves ausentes sin usar indices obligatorios. |
| 152 | Verifica que el objeto JSON corresponda al ID del video solicitado. |
| 153 | Combina `stats` y `statsV2`. `**` incorpora las entradas de cada diccionario; si hay una clave repetida, prevalece la de `statsV2`. `or {}` permite tratar un bloque nulo como vacio. |
| 154 | Captura errores de JSON o de estructura que no tenga el tipo esperado. |
| 155 | Omite esos datos defectuosos y permite seguir con el intento de lectura visible. |
| 157 | Crea una lista para los nombres de contadores que no se pudieron obtener. |
| 158 | Recorre la configuracion y separa nombre de columna, clave JSON y selector visible. |
| 159 | Intenta obtener el contador del diccionario de estadisticas. |
| 160 | Solo busca en el DOM si el valor es `None`; un cero real no se considera ausente. |
| 161 | Construye el localizador del contador visible y toma su primera coincidencia. |
| 162 | Inicia el intento de leer ese contador. |
| 163 | Espera hasta tres segundos para obtener su texto. |
| 164 | Captura un fallo de esa lectura, por ejemplo, que el elemento no aparezca. |
| 165 | Marca el valor como ausente. |
| 166 | Inicia el intento de conversion a numero. |
| 167 | Convierte y guarda la interaccion en la columna correspondiente. |
| 168 | Atiende un formato invalido o un dato ausente. |
| 169 | Registra el nombre del contador faltante. El valor del resultado permanece en `None`. |
| 170 | Comprueba si hubo contadores no disponibles. |
| 171 | Escribe sus nombres unidos por comas dentro de `Metrics Error`. |
| 172 | Distingue el error especial de restriccion de los demas errores. |
| 173 | Lo vuelve a lanzar para que el proceso de varios videos deje de consultar. No lo convierte en un simple fallo recuperable. |
| 174 | Captura otros errores ordinarios de este video. |
| 175 | Inicia un ultimo intento de comprobar si el fallo estuvo relacionado con una restriccion visible. |
| 176 | Ejecuta esa comprobacion. Si lanza `ScrapingRestrictedError`, se propaga y detiene la secuencia de videos. |
| 177 | Atiende los errores `ValueError` de esa comprobacion, que no representan el tipo especial de restriccion. |
| 178 | Evita que ese error secundario reemplace el problema original del video. |
| 179 | Guarda el tipo y mensaje del fallo original en `Metrics Error`. |
| 180 | Devuelve las interacciones disponibles y el estado del video. |

La primera fuente es el JSON publico que forma parte de la pagina, no una
solicitud a un servicio externo inventado por el proyecto. Si el dato no esta en
ese bloque, se intenta leer el contador visible. Ninguna fuente garantiza que
TikTok entregue valores exactos o actualizados en tiempo real.

## 11. Pausar y recorrer videos: lineas 182-201

| Linea | Que hace y para que sirve |
| --- | --- |
| 182 | Define `collect_video_interactions`, que coordina la secuencia de videos. |
| 183 | Crea la lista de resultados, en el mismo orden de los videos recibidos. |
| 184 | Recorre los videos con `enumerate`; el indice comienza en cero. |
| 185 | Es verdadero desde el segundo video: el primer indice, cero, no entra en este bloque. |
| 186 | Informa la pausa que se aplicara antes de la siguiente consulta. |
| 187 | Espera al menos los dos segundos configurados con `asyncio.sleep`. El evento puede reanudarse mas tarde, no se promete un tiempo total exacto. |
| 188 | Muestra el avance con un contador para personas, empezando en uno, y el total. |
| 189 | Inicia el intento de obtener las interacciones del video actual. |
| 190 | Espera que termine la consulta antes de pasar a otro video. No usa `gather` ni abre todas las consultas simultaneamente. |
| 191 | Atiende una restriccion que obliga a interrumpir la secuencia. |
| 192 | Muestra el motivo de la detencion. |
| 193 | Empieza a agregar filas de estado para el video que encontro la restriccion y los siguientes. |
| 194 | Inicializa sus cuatro contadores en `None`; no inventa ceros. |
| 195 | Agrega a cada fila una explicacion de la restriccion. |
| 196 | Genera una fila independiente por cada video desde `index` hasta el final y la incorpora a los resultados. No visita esos videos pendientes. |
| 197 | Sale del bucle sin realizar las consultas restantes. |
| 198 | Para un resultado normal, comprueba si hubo fallos recuperables. |
| 199 | Muestra el aviso, sin detener por ello toda la secuencia. |
| 200 | Agrega el resultado del video consultado. |
| 201 | Devuelve la lista de resultados, alineada con la lista de videos. |

La espera se aplica despues de terminar la consulta anterior y antes de iniciar la
siguiente. Se conserva aunque el video anterior devuelva un error recuperable.
Para diez videos sin interrupcion hay nueve pausas, al menos 18 segundos mas el
tiempo de carga y extraccion. No hay una pausa antes del primer video ni despues
del ultimo. Esta medida **no garantiza evitar un bloqueo** y no controla otras
instancias del programa o todas las solicitudes internas del navegador.

## 12. Abrir el perfil y preparar datos: lineas 203-240

| Linea | Que hace y para que sirve |
| --- | --- |
| 203 | Define `scrape_profile`, que recibe un navegador ya abierto y coordina la recopilacion y los archivos. |
| 204 | Abre una pagina con idioma `en-US`, para favorecer los mensajes y formatos numericos ingleses esperados. No garantiza que todo el contenido tenga siempre ese idioma. |
| 205 | Empieza la navegacion al perfil y guarda su respuesta. |
| 206 | Construye la URL con el usuario limpio y configura documento inicial listo y limite de 30 segundos. |
| 207 | Cierra la llamada de navegacion. |
| 208 | Revisa si se puede continuar con ese perfil. |
| 210 | Muestra que el documento del perfil cargo y que se intentara obtener contenido; todavia no confirma que la extraccion haya terminado. |
| 212 | Llama a la funcion que recopila, elimina duplicados y selecciona hasta diez videos. |
| 213 | Vuelve a comprobar el acceso despues de esa carga del perfil. |
| 214 | Comprueba si se pudieron reunir menos de diez videos. |
| 215 | Muestra cuantos se obtuvieron y aclara que no se rellenara la lista repitiendo registros. |
| 217 | Obtiene la fecha local y la formatea como anio-mes-dia. No es la fecha de publicacion del video. |
| 218 | Elige el usuario como nombre de la carpeta de resultados. |
| 219 | Comprueba si esa carpeta ya existe en el directorio desde el que se ejecuto el programa. |
| 220 | La crea si hace falta. No agrega automaticamente una carpeta raiz llamada `resultados`. |
| 222 | Prepara la lista que contendra las filas del Excel de publicaciones. |
| 223 | Abre otra pagina para las consultas de videos, sin reemplazar la pagina del perfil. `browser.new_page` crea una pagina en su propio contexto. |
| 224 | Obtiene los resultados de interacciones, con pausas y manejo de restricciones. |
| 225 | Recorre los videos seleccionados con un contador que empieza en uno, utilizado en nombres de archivos. |
| 226 | Inicia el control de la conversion de visualizaciones. |
| 227 | Convierte el contador de vistas recopilado en el perfil si existe; de lo contrario usa `None`. |
| 228 | Atiende un formato de visualizaciones no reconocido. |
| 229 | Conserva la publicacion con vistas ausentes en vez de descartarla. |
| 230 | Construye un nombre de miniatura con fecha y contador, por ejemplo `2026-10-19_1.jpg`. |
| 231 | Inicia la referencia de imagen como ausente. |
| 232 | Comprueba si se recopilo una URL de miniatura. |
| 233 | Intenta descargarla y guarda el nombre retornado o `None` si fallo. |
| 234 | Recupera las interacciones de ese mismo video. Resta uno porque los indices de las listas empiezan en cero. |
| 235 | Empieza el diccionario de una fila del Excel. |
| 236 | Incluye URL del video y visualizaciones. |
| 237 | Incluye el archivo de miniatura o `Sin id`, y crea un identificador local de publicacion con fecha y contador. Ese `id_post` no es el ID original de TikTok. |
| 238 | Incorpora las cuatro interacciones y `Metrics Error` mediante `**interactions`. |
| 239 | Cierra el diccionario y lo agrega a `video_data`. |
| 240 | Cierra la pagina utilizada para los videos. El navegador todavia se necesita para leer la pagina del perfil. |

Si se detecto una restriccion durante la secuencia de videos, no se hacen mas
consultas de esos videos pendientes, pero esta funcion todavia prepara los
archivos y puede intentar descargar las miniaturas ya recopiladas y el avatar.
No debe afirmarse que se cancelan absolutamente todas las solicitudes de red.

## 13. Exportar publicaciones: lineas 242-253

| Linea | Que hace y para que sirve |
| --- | --- |
| 242 | Muestra el numero de publicaciones seleccionadas, no la cantidad total de videos del perfil. |
| 243 | Recorre las filas preparadas para mostrarlas en consola. |
| 244 | Imprime URL y las cuatro interacciones. Un `None` en consola representa un contador no disponible. |
| 246 | Construye la ruta del Excel de publicaciones: carpeta del usuario y nombre con usuario, `post` y fecha. |
| 247 | Empieza a convertir la lista de diccionarios en una tabla de pandas. |
| 248 | Establece el orden de las primeras columnas: enlace, vistas y referencias locales de imagen y publicacion. |
| 249 | Agrega las columnas de interacciones y error al orden de la tabla. |
| 250 | Cierra la construccion del DataFrame. Declarar columnas permite conservar los encabezados aunque no haya filas. |
| 251 | Agrega `id_perfil` a cada fila con el nombre del usuario. |
| 252 | Guarda el Excel. `index=False` evita incluir como columna adicional el indice numerico de pandas. Para escribir `.xlsx` se necesita un motor compatible, incluido `openpyxl` en las dependencias. |
| 253 | Muestra la ruta donde se guardo el archivo. |

El Excel no lleva las imagenes incrustadas: contiene el nombre de sus archivos.
Los contadores `None` se exportan normalmente como celdas vacias. Cuando todas las
filas tienen cero real, ese cero sigue siendo un dato valido, no un error.

## 14. Leer y exportar el perfil: lineas 255-285

| Linea | Que hace y para que sirve |
| --- | --- |
| 255 | Busca el elemento de cantidad de seguidores del perfil. |
| 256 | Busca el elemento de cantidad de cuentas seguidas. |
| 257 | Busca el contador de corazones acumulados del perfil. Es diferente de los corazones de un video. |
| 258 | Busca la biografia. |
| 259 | Busca la imagen del perfil por una clase que contenga `ImgAvatar`. Es un selector dependiente del HTML de TikTok. |
| 261 | Prepara la lista de los tres contadores del perfil. |
| 262 | Recorre, en orden, seguidores, seguidos y corazones acumulados. |
| 263 | Inicia el intento de conversion de cada contador. |
| 264 | Si existe el elemento, lee su texto y lo convierte; si no, agrega `None`. |
| 265 | Atiende un formato que no se puede convertir. |
| 266 | Agrega `None` para ese contador y continua con los otros. |
| 267 | Desempaqueta los tres resultados respetando su orden. |
| 268 | Lee la biografia o usa el texto `N/A` si no encontro el elemento. |
| 269 | Lee la URL `src` del avatar si existe el elemento; si no, usa `None`. |
| 271 | Inicia el nombre de archivo del avatar como ausente. |
| 272 | Comprueba si hay URL para intentar la descarga. |
| 273 | Descarga el avatar con nombre `imagen_cover.jpg`; solo conserva ese nombre si la funcion de descarga informa exito. |
| 275 | Construye la ruta del Excel del perfil, con usuario, `perfil` y fecha. |
| 276 | Crea un DataFrame a partir de una lista con un solo diccionario: sera una sola fila del perfil. |
| 277 | Agrega la cantidad de seguidores en `Followers`. |
| 278 | Agrega la cantidad de cuentas seguidas en `Following`. |
| 279 | Agrega los corazones acumulados del perfil en `Likes`. No es la suma calculada de los diez videos seleccionados. |
| 280 | Agrega la biografia en `Bio`. |
| 281 | Agrega el nombre del archivo del avatar o un valor ausente en `Profile Image`. |
| 282 | Agrega el usuario en `id_perfil`, permitiendo relacionar ambas tablas. |
| 283 | Cierra el diccionario, la lista y la construccion del DataFrame. |
| 284 | Guarda el Excel del perfil sin exportar el indice de pandas. |
| 285 | Muestra la ruta del segundo archivo. |

Los archivos usan la fecha local y nombres repetibles. Ejecutar el programa de
nuevo para el mismo usuario el mismo dia puede sobrescribir los Excel y las
miniaturas. El avatar siempre usa el mismo nombre dentro de esa carpeta.
La informacion del perfil puede cambiar mientras se procesan los videos.

## 15. Gestionar el navegador: lineas 287-296

| Linea | Que hace y para que sirve |
| --- | --- |
| 287 | Define `run`, responsable de abrir y cerrar el navegador para un usuario. |
| 288 | Inicia Chromium con ventana visible: `headless=False`. No abre una extension del navegador instalado. |
| 289 | Abre el bloque protegido de ejecucion. |
| 290 | Ejecuta y espera la recopilacion completa del perfil. |
| 291 | Define la limpieza que se intentara tanto si hubo exito como si hubo error o cancelacion durante la recopilacion. |
| 292 | Cierra el navegador y sus paginas. La proteccion empieza despues de haberlo abierto: no puede cerrar un navegador que no llego a iniciarse. |
| 294 | Define la funcion asincrona principal `main`. |
| 295 | Inicia Playwright dentro de un contexto que administra su ciclo de vida. Esto prepara la herramienta; Chromium se abre en `run`. |
| 296 | Llama a `run` y espera su finalizacion. |

No es lo mismo cerrar una pagina, cerrar Chromium y terminar Playwright: son
recursos distintos. El programa cierra la pagina de metricas al terminar de usarla
y garantiza la limpieza del navegador mediante `finally`.

## 16. Pedir el usuario y manejar errores: lineas 298-317

| Linea | Que hace y para que sirve |
| --- | --- |
| 298 | Ejecuta este bloque solo si `main.py` es el archivo iniciado directamente. Al importarlo desde las pruebas no pide usuario ni inicia scraping. |
| 299 | Inicia el control de errores de la entrada y de la ejecucion. |
| 300 | Repite la solicitud de usuario hasta recibir un formato valido o cancelar. |
| 301 | Inicia el intento de leer y validar la entrada. |
| 302 | Muestra la pregunta, recibe el texto con `input` y lo normaliza. Se aceptan nombres con o sin `@`. |
| 303 | Si la validacion termino correctamente, sale del bucle de entrada. |
| 304 | Atiende un usuario con formato invalido. |
| 305 | Muestra el motivo y deja que el bucle vuelva a pedir el usuario. |
| 306 | Crea el bucle de eventos y ejecuta `main(username)` hasta terminar. Este es el salto del codigo normal al flujo asincrono. |
| 307 | Atiende Ctrl+C o el fin de entrada en la consola. |
| 308 | Muestra que se cancelo la ejecucion. Si ya se habia abierto el navegador y se estaba recopilando, se intenta cerrarlo mediante `finally`. |
| 309 | Atiende los tiempos de espera de Playwright que no se resolvieron dentro de las funciones anteriores. |
| 310 | Sugiere comprobar conexion y probar mas tarde. |
| 311 | Termina con codigo 1, indicando un fallo al sistema operativo. |
| 312 | Atiende un error de permisos, como un Excel abierto que impida sobrescribir el archivo. |
| 313 | Muestra una instruccion para cerrar el Excel o revisar permisos. |
| 314 | Termina con codigo de error. |
| 315 | Atiende otros errores previstos de datos, restricciones, Playwright o sistema de archivos. `ScrapingRestrictedError` entra aqui por heredar de `RuntimeError` si no se resolvio en el proceso de videos. |
| 316 | Muestra el mensaje del problema sin presentar un rastreo completo de Python para esos casos. |
| 317 | Termina con codigo 1. No significa que se hayan deshecho archivos que ya se alcanzaron a guardar. |

Un error recuperable de un video se registra en su fila. Una restriccion durante
las consultas de videos interrumpe esa secuencia y permite preparar sus resultados
parciales. Un error anterior, por ejemplo un perfil privado detectado al abrirlo,
puede terminar la ejecucion sin crear los Excel. Un fallo de guardado tampoco
garantiza que ambos Excel se hayan creado.

## 17. Los otros archivos

### `requirements.txt`

Cada linea declara un paquete externo que `pip` debe instalar:

| Linea | Paquete | Uso |
| --- | --- | --- |
| 1 | `pandas` | Tablas de datos y exportacion a Excel. |
| 2 | `playwright` | Control del navegador. El navegador se instala con un comando adicional. |
| 3 | `aiohttp` | Solicitudes para descargar imagenes. |
| 4 | `aiofiles` | Escritura asincrona de las imagenes. |
| 5 | `openpyxl` | Motor para leer o escribir archivos `.xlsx`. |

`asyncio`, `json`, `re`, `sys`, `os` y `datetime` vienen con Python; no hace falta
instalarlos por separado. Las dependencias no estan fijadas a versiones concretas,
por lo que una instalacion futura podria requerir ajustes.

### Carpeta `tests`

| Archivo | Que comprueba |
| --- | --- |
| `test_recent_videos.py` | Limite de diez, orden numerico, candidatos fijados antiguos, duplicados, carga por desplazamientos y filtrado de otros perfiles. |
| `test_interactions.py` | Formatos numericos, cero real, JSON, lectura visible, datos parciales, redirecciones y fallos de navegacion. |
| `test_access_and_pacing.py` | Mensajes de acceso, restricciones, cierre ante error o cancelacion, pausas y conservacion de resultados parciales. |

Las pruebas usan objetos simulados para no consultar TikTok. Una de ellas espera
dos segundos reales y mide el intervalo con un reloj monotono, que sirve para
medir duraciones sin depender de ajustes de la hora del sistema. Las pruebas no
demuestran que los selectores de TikTok sigan funcionando despues de un cambio
de su pagina.

### `obtener_estadisticas.py`: archivo antiguo

Este archivo **no participa** en el recorrido explicado arriba. Se conserva de la
version inicial y no hay que ejecutarlo para obtener las cuatro interacciones.

Su idea original es leer un Excel con enlaces, visitar videos con la API sincrona
de Playwright, intentar agregar titulo, interacciones, fecha y audio, y guardar
otro Excel. Tiene rutas fijas de otro equipo, un selector antiguo para guardados
y ejecuta operaciones al importarse. No debe presentarse como una segunda parte
necesaria ni como un script actualizado. Su existencia tampoco significa que
`main.py` exporte titulo, audio o fecha de publicacion: actualmente no lo hace.

## 18. Preguntas para la exposicion

**Por que Playwright y no solo una solicitud HTTP?**

TikTok carga parte del contenido con JavaScript y al desplazarse. Un navegador
permite cargar y consultar ese contenido. Las solicitudes de `aiohttp` se reservan
para imagenes cuyas URL ya fueron obtenidas.

**Por que usar dos paginas?**

Una conserva el perfil mientras la otra navega por los videos. Asi se pueden leer
los datos del perfil al final sin volver a navegar a su URL.

**Como se evitan duplicados?**

Se almacena cada candidato en un diccionario cuya clave es su ID numerico. Varias
URL del mismo video con parametros distintos quedan bajo la misma clave.

**Como se decide cuales son los diez recientes?**

Se cargan candidatos adicionales del perfil, se ordenan sus IDs temporales de
mayor a menor y se toman diez. Esto contempla fijados antiguos, pero depende del
orden habitual y de lo que TikTok llegue a cargar. No es una garantia universal.

**Por que una celda vacia no es cero?**

Porque cero significa que el contador fue obtenido y vale cero. Vacio significa
que no se pudo obtener o interpretar. `Metrics Error` ayuda a distinguir el caso.

**La pausa evita que nos bloqueen?**

No hay esa garantia. Solo reduce la frecuencia de nuestras consultas de videos.
Si se reconoce una restriccion, se dejan de consultar los pendientes y no se
intenta resolver CAPTCHA, usar proxies o evadir controles.

**Que diferencia hay entre visualizaciones y corazones?**

`Views` es la cantidad mostrada de visualizaciones; `Likes` es la de corazones.
No son la misma interaccion y no se calcula una a partir de la otra.

**Ya se analizan tendencias o engagement?**

No. El programa recopila y organiza datos. No calcula engagement, tendencias,
sentimientos ni comparaciones entre cuentas. Ese seria otro trabajo posterior.

**Como se comprueba que funciona?**

Con las pruebas locales, una ejecucion controlada con un perfil publico y la
revision manual de sus Excel. Las pruebas con datos simulados y la comprobacion
en TikTok real cumplen objetivos distintos; ninguna permite prometer que todos
los perfiles funcionaran siempre.
