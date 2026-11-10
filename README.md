# Pruebas Academia

Formularios de evaluación con acceso por QR, validación y puntaje en el servidor y envío de resultados a Make. Los formularios viven en Upstash Redis y se administran con una API (sin panel visual).

## Local

Para administrar Redis desde la raíz, usa `python redis_crud.py`.
La [guía de redis_crud.py](REDIS_CRUD.md) explica cómo sembrar, editar preguntas,
crear o eliminar formularios, reiniciar contadores y cambiar códigos de URL,
además de respaldar y gestionar el fondo y los errores.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python server.py
```

Configura `.env` a partir de `.env.example`. En desarrollo, si `MAKE_WEBHOOK_URL` está vacío, el envío se simula en la consola, y si no configuras Redis los formularios se leen (solo lectura) de `app/backend/data/formularios.json`.

Formulario 1 (código permanente):

`http://127.0.0.1:5000/?f=6gxxhfp5dy`

Ese enlace emite una cookie HttpOnly de acceso y redirige a `/formulario/6gxxhfp5dy`. El acceso dura cinco días por defecto. Las URLs antiguas con `formulario_1` dejan de existir: actualiza los QR que las utilicen.

## Imágenes en Vercel Blob

Usa un Blob Store **público** conectado al proyecto y configura
`BLOB_READ_WRITE_TOKEN` en el servidor. Sube imágenes PNG, JPG o WebP con
`POST /admin/imagenes`, autenticado con `X-Admin-Key`, usando el campo multipart
`archivo` (máximo 4 MB). El servidor optimiza a WebP y devuelve `src`, `ancho`
y `alto`. Guarda esos valores junto con `alt` dentro de `imagen` en la pregunta:

```json
{
  "imagen": {
    "src": "https://<store-id>.public.blob.vercel-storage.com/preguntas/imagen.webp",
    "ancho": 800,
    "alto": 450,
    "alt": "Descripción de la imagen"
  }
}
```

También puedes usar URLs de imágenes subidas desde el panel de Vercel Blob.
El fondo es global para todos los formularios. El archivo vive en Vercel Blob;
Redis guarda la URL elegida en `configuracion:fondo_formularios`.

Para cambiar el fondo desde el programa administrador:

1. Sube la imagen con `POST /admin/imagenes` (campo multipart `archivo`).
2. Envía `PUT /admin/fondo` con JSON `{"src": "URL pública devuelta por Blob"}`.
3. Al abrir o recargar un formulario, aparece el nuevo fondo sin volver a desplegar.

Las rutas exigen `X-Admin-Key`. `GET /admin/fondo` devuelve `{"src": "..."}`;
`DELETE /admin/fondo` vuelve al degradado sin borrar el archivo de Blob.
Cambiar el fondo tampoco borra el archivo anterior de Blob.

Inicialización segura de Redis (conserva un fondo ya configurado):

```powershell
python -B -m app.backend.functions.inicializar_fondo
```

El comando crea la clave con `SET NX`. Si todavía existe `FONDO_FORMULARIOS_URL`
en el entorno anterior, migra su valor al crear la clave; después puede retirarse.
Sin esa variable, empieza sin imagen elegida. Sin Redis, se muestra el degradado
y la modificación se rechaza, igual que la edición de formularios.

Logo y firma del certificado permanecen en texto. El favicon sigue siendo local.
El token de Blob permanece en el servidor. Los archivos eliminados deben subirse
a Blob y sus referencias deben actualizarse en los formularios guardados en Redis.

## Estructura del código

- `server.py`: entrada Flask para local y Vercel.
- `app/backend/functions/`: configuración, tokens, repositorio (Redis), validación de formularios (`esquema.py`), imágenes, evaluación, formato de datos (`formato.py`), registro de errores (`errores.py`), webhook y módulo de duplicados.
- `app/backend/routes/`: páginas, API pública y API de administración (`admin.py`).
- `app/backend/data/formularios.json`: formulario inicial; se carga a Redis con `app/backend/functions/sembrar_formularios.py` y sirve de respaldo de solo lectura en local.
- `app/backend/functions/sembrar_formularios.py`: carga única del JSON a Redis.
- `app/frontend/`: templates y archivos estáticos en sus carpetas originales.
- `vercel.json`: empaqueta el backend/templates y publica los estáticos sin mover el frontend.

Los formularios se crean, editan y borran con la API de administración (ver [DEPLOY_VERCEL.md](DEPLOY_VERCEL.md)). Los IDs de pregunta (`P1-1`, `P1-2`…) los genera el backend según el orden; no se escriben a mano. El código de cada formulario (el del QR) se conserva al editarlo. Los nuevos tienen 10 caracteres alfanuméricos aleatorios; el Formulario 1 usa el código `6gxxhfp5dy`.

Si Redis todavía tiene el primer formulario con el UUID antiguo, ejecuta `python -m app.backend.functions.acortar_formulario` antes de volver a sembrar. Cambia únicamente su código a `6gxxhfp5dy`, conservando el contenido, número de prueba y contadores. El enlace anterior deja de funcionar: actualiza su QR.

## Verificación

```powershell
python -B -m unittest discover -s tests -v
```

Las pruebas verifican la API de administración, el formato de los datos, el ID de respuesta y el registro de errores y el JSON que se envía a Make (estructura en [DEPLOY_VERCEL.md](DEPLOY_VERCEL.md)). El webhook se sustituye en las pruebas: no envían datos reales a Make.

Con exactamente 100 puntos, `duplicados.py` calcula una huella SHA-256 de RUT empresa,
RUT conductor, modelo, tracción, año comercial y potencia. Normaliza formato y orden
de selecciones. La coincidencia se comparte entre formularios; otros datos no influyen.
Redis guarda la huella y el estado, sin datos del participante ni PDFs, en claves
`duplicados:certificados:v1:<huella>`. Las marcas vencen a los siete días (604800 segundos)
desde la confirmación de recepción de Make. Los duplicados no renuevan ese plazo.

El JSON enviado a Make incluye `duplicado` como entero: `0` para nuevos registros
y puntajes menores a 100; `1` para combinaciones de 100 puntos ya registradas.
Todos se envían a Make. Los duplicados llevan `certificado: null` y no consumen
otro número de certificado. En Make, la rama que emite certificados debe filtrar
por `puntuacion = 100` **y** `duplicado = 0`. La respuesta al navegador conserva
`duplicado: false`; el frontend no informa esta condición.

Una reserva atómica de 120 segundos evita emitir simultáneamente el mismo
certificado. Mientras está pendiente, otro envío recibe un error temporal para
reintentar. Los fallos de PDF y los envíos fallidos liberan la reserva; los envíos
simulados no dejan una marca de siete días. Sin Redis se usa memoria únicamente
en desarrollo local. Los fallos de Redis detienen la emisión.

Limitación: un timeout de Make no confirma si el escenario guardó el registro.
La reserva se libera para permitir reintentos, que podrían repetir la emisión
si Make sí lo recibió. Para garantizar deduplicación también en ese caso, Make
necesita su propio control; `duplicado` por sí solo no garantiza entrega única.

Para eliminar **todas las huellas y reservas**, conservando formularios, contadores
y errores (ejecutar sin alumnos enviando pruebas):

```powershell
python limpiar_huellas.py --ver
python limpiar_huellas.py
```

El segundo comando pide escribir `LIMPIAR`. Después se permitirá volver a emitir
certificados de esas combinaciones. No elimina registros de Make/Excel.

Para cambiar el código/URL de un formulario (no se puede renombrar), `python -m app.backend.functions.reiniciar_formularios --ver` muestra qué haría el script que borra los formularios de Redis y siembra el de `formularios.json` con un código nuevo; sin `--ver` pide confirmación. Lee el encabezado del archivo antes de usarlo (conserva por defecto los contadores de respuestas).

Para publicar, sigue [DEPLOY_VERCEL.md](DEPLOY_VERCEL.md).
