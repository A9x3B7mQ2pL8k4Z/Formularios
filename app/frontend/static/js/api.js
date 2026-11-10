/**
 * Comunicación con el backend.
 * El navegador solo pide el formulario (sin respuestas correctas) y envía lo que
 * respondió la persona. El puntaje y la validación los decide siempre el servidor.
 * El token de acceso viaja en una cookie HttpOnly: este código nunca lo ve.
 */

async function pedirJson(url, opciones = {}) {
    const respuesta = await fetch(url, {
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        ...opciones
    });
    const datos = await respuesta.json().catch(() => ({}));
    return { ok: respuesta.ok, estado: respuesta.status, datos };
}

/** Devuelve el formulario listo para pintar, o null si no existe / no hay acceso. */
async function cargarFormulario(idFormulario) {
    const { ok, estado, datos } = await pedirJson(`/api/formularios/${encodeURIComponent(idFormulario)}`);

    if (ok) return datos;
    if (estado === 401 || estado === 404) return null;
    throw new Error(datos.error || `Error ${estado} al cargar el formulario`);
}

/** Envía las respuestas. Devuelve { ok, estado, datos } para que la app decida qué mostrar. */
function enviarRespuestas(idFormulario, respuestas) {
    return pedirJson(`/api/formularios/${encodeURIComponent(idFormulario)}/enviar`, {
        method: 'POST',
        body: JSON.stringify({ respuestas })
    });
}
