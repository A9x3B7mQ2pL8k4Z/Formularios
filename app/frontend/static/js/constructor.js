/**
 * Constructor de HTML.
 *
 * Funciones puras: reciben datos y devuelven un string HTML.
 * No tienen estado, no tocan el DOM y no manejan eventos.
 *
 * Cada función de pregunta recibe la pregunta y un contexto:
 *   respuesta  lo que eligió o escribió la persona (string, arreglo o undefined)
 *   error      mensaje de validación ('' si es válida)
 *   revision   null al responder, o { esCorrecta } al mostrar resultados
 */

function escaparHtml(valor) {
    const entidades = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    };

    return String(valor ?? '').replace(/[&<>"']/g, caracter => entidades[caracter]);
}

/* ==========================================================================
   Piezas compartidas por todas las preguntas
   ========================================================================== */

function crearImagenDePregunta(imagen) {
    return `
        <img class="question-image" src="${escaparHtml(imagen.src)}" alt="${escaparHtml(imagen.alt)}"
            width="${imagen.ancho}" height="${imagen.alto}">
    `;
}

function crearInsigniaDeRevision(pregunta, { esCorrecta }) {
    const estado = esCorrecta ? 'correct' : 'incorrect';
    const etiqueta = esCorrecta ? 'Correcto' : 'Incorrecto';
    const icono = esCorrecta ? 'check-circle-fill' : 'x-circle-fill';
    const puntosObtenidos = esCorrecta ? pregunta.puntos : 0;

    return `
        <div class="review-badge review-badge--${estado}">
            <i class="bi bi-${icono}" aria-hidden="true"></i>
            <strong>${etiqueta}</strong>
            <span>${puntosObtenidos}/${pregunta.puntos} puntos</span>
        </div>
    `;
}

/** Envuelve el campo propio de cada tipo con el encabezado, el puntaje y el error. */
function armarPregunta(pregunta, { error = '', revision = null }, campo) {
    const idTitulo = `titulo-pregunta-${pregunta.id}`;
    const clases = ['question', error && 'question--invalid'].filter(Boolean).join(' ');
    const puntos = pregunta.puntos
        ? `<span class="question-points">(${pregunta.puntos} puntos)</span>`
        : '';

    return `
        <section class="${clases}" id="pregunta-${pregunta.id}" aria-labelledby="${idTitulo}">
            ${revision && pregunta.puntos ? crearInsigniaDeRevision(pregunta, revision) : ''}
            <div class="question-header">
                <span class="question-number">${pregunta.numero}</span>
                <p class="question-title" id="${idTitulo}">
                    ${escaparHtml(pregunta.titulo)}
                    <span class="question-required">*</span>
                    ${puntos}
                </p>
                ${pregunta.imagen ? crearImagenDePregunta(pregunta.imagen) : ''}
            </div>
            ${campo}
            <p class="question-error" role="alert">${escaparHtml(error)}</p>
        </section>
    `;
}

/* ==========================================================================
   Una función por tipo de pregunta
   ========================================================================== */

function crearPreguntaDeInformacion(pregunta, contexto) {
    const { respuesta, revision } = contexto;
    const tipoInput = pregunta.validacion === 'email' ? 'email' : 'text';

    const campo = `
        <input class="text-field" type="${tipoInput}" name="pregunta-${pregunta.id}"
            data-id-pregunta="${pregunta.id}" value="${escaparHtml(respuesta)}"
            placeholder="Escriba su respuesta" autocomplete="off"
            ${revision ? 'disabled' : ''}>
    `;

    return armarPregunta(pregunta, contexto, campo);
}

function crearOpciones(pregunta, { respuesta, revision }, tipoInput) {
    const seleccionadas = Array.isArray(respuesta) ? respuesta : [respuesta];

    const opciones = pregunta.opciones.map(opcion => {
        const estaSeleccionada = seleccionadas.includes(opcion);
        const mostrarMarca = revision?.esCorrecta && estaSeleccionada;

        return `
            <label class="option">
                <input class="option-input" type="${tipoInput}" name="pregunta-${pregunta.id}"
                    data-id-pregunta="${pregunta.id}" value="${escaparHtml(opcion)}"
                    ${estaSeleccionada ? 'checked' : ''} ${revision ? 'disabled' : ''}>
                <span class="option-label">${escaparHtml(opcion)}</span>
                ${mostrarMarca ? '<i class="bi bi-check-circle-fill option-mark" role="img" aria-label="Respuesta correcta"></i>' : ''}
            </label>
        `;
    });

    return `<div class="options">${opciones.join('')}</div>`;
}

function crearPreguntaDeSeleccionUnica(pregunta, contexto) {
    return armarPregunta(pregunta, contexto, crearOpciones(pregunta, contexto, 'radio'));
}

function crearPreguntaDeSeleccionMultiple(pregunta, contexto) {
    return armarPregunta(pregunta, contexto, crearOpciones(pregunta, contexto, 'checkbox'));
}

const CREADORES_DE_PREGUNTA = {
    informacion: crearPreguntaDeInformacion,
    seleccion_unica: crearPreguntaDeSeleccionUnica,
    seleccion_multiple: crearPreguntaDeSeleccionMultiple
};

function crearPregunta(pregunta, contexto = {}) {
    const crear = CREADORES_DE_PREGUNTA[pregunta.tipo];
    if (!crear) throw new Error(`Tipo de pregunta desconocido: "${pregunta.tipo}"`);

    return crear(pregunta, contexto);
}

/* ==========================================================================
   Sección
   ========================================================================== */

/**
 * `detalle` es el resultado por pregunta que entrega el servidor ({ [id]: boolean }).
 * Si se pasa, la sección se pinta en modo revisión; si no, para responder.
 */
function crearSeccion(seccion, { respuestas, errores = {}, detalle = null }) {
    const preguntas = seccion.preguntas.map(pregunta => crearPregunta(pregunta, {
        respuesta: respuestas[pregunta.id],
        error: errores[pregunta.id],
        revision: detalle ? { esCorrecta: Boolean(detalle[pregunta.id]) } : null
    }));

    return `
        <div class="section">
            <h2 class="section-title">${escaparHtml(seccion.titulo)}</h2>
            ${preguntas.join('')}
        </div>
    `;
}

/* ==========================================================================
   Páginas
   ========================================================================== */

function crearEncabezado(formulario, { mostrarIntroduccion, paso = null }) {
    // `instrucciones` es HTML de confianza escrito por el administrador (usa <strong>)
    const introduccion = `
        <ol class="instructions">
            ${formulario.instrucciones.map(instruccion => `<li>${instruccion}</li>`).join('')}
        </ol>
        <p class="privacy-notice">${escaparHtml(formulario.avisoPrivacidad)}</p>
        <p class="required-notice"><span class="question-required">* Obligatorio</span></p>
    `;

    return `
        <header class="form-header">
            <h1 class="form-title">${escaparHtml(formulario.titulo)}</h1>
            ${paso ? `
                <div class="progress">
                    <div class="progress-text">Paso ${paso.actual} de ${paso.total}</div>
                    <div class="progress-bar" role="progressbar" aria-label="Progreso del formulario"
                        aria-valuemin="0" aria-valuemax="${paso.total}" aria-valuenow="${paso.actual}">
                        <i style="width:${paso.actual / paso.total * 100}%"></i>
                    </div>
                </div>
            ` : ''}
            ${mostrarIntroduccion ? introduccion : ''}
        </header>
    `;
}

function crearNavegacion({ esPrimera, esUltima, enviando, errorEnvio }) {
    const botonAnterior = esPrimera
        ? ''
        : '<button class="button button--secondary" type="button" data-accion="anterior">Anterior</button>';

    const botonAvanzar = esUltima
        ? `<button class="button" type="button" data-accion="enviar" ${enviando ? 'disabled' : ''}>
               ${enviando ? 'Enviando...' : 'Enviar'}
           </button>`
        : '<button class="button" type="button" data-accion="siguiente">Siguiente</button>';

    return `
        <div class="form-actions">${botonAnterior}${botonAvanzar}</div>
        <p class="submit-error" role="alert">${escaparHtml(errorEnvio)}</p>
    `;
}

function crearPagina(contenido, modificador = '') {
    return `
        <div class="page-container">
            <article class="form-card ${modificador}"><div class="form-card-content">${contenido}</div></article>
        </div>
    `;
}

function crearPaginaDeFormulario(formulario, { indiceSeccion, respuestas, errores, enviando, errorEnvio }) {
    const seccion = formulario.secciones[indiceSeccion];

    return crearPagina(`
        ${crearEncabezado(formulario, {
            mostrarIntroduccion: indiceSeccion === 0,
            paso: { actual: indiceSeccion + 1, total: formulario.secciones.length }
        })}
        ${crearSeccion(seccion, { respuestas, errores })}
        ${crearNavegacion({
            esPrimera: indiceSeccion === 0,
            esUltima: indiceSeccion === formulario.secciones.length - 1,
            enviando,
            errorEnvio
        })}
    `);
}

function crearPaginaDeRevision(formulario, { respuestas, resultado }) {
    const secciones = formulario.secciones.map(seccion =>
        crearSeccion(seccion, { respuestas, detalle: resultado.detalle })
    );

    return crearPagina(`
        ${crearEncabezado(formulario, { mostrarIntroduccion: false })}
        <div class="score-summary">
            Puntaje <strong>${resultado.puntaje}/${formulario.puntajeTotal}</strong>
        </div>
        ${secciones.join('')}
        <div class="form-actions">
            <button class="button button--secondary" type="button" data-accion="volver-al-resultado">Atrás</button>
        </div>
    `, 'form-card--review');
}

function crearPaginaDeResultado({ mensaje, aprobado, puedeReintentar, puedeReenviar, enviando = false }) {
    const botonReintentar = puedeReintentar
        ? '<button class="final-button" type="button" data-accion="reintentar">Repetir la prueba</button>'
        : '';

    return `
        <div class="page-container">
        <div class="final-screen final-screen--${aprobado ? 'passed' : 'failed'}">
            <div class="final-status" aria-hidden="true">
                <i class="bi bi-${aprobado ? 'check-circle-fill' : 'x-circle-fill'}"></i>
            </div>
            <h2 class="final-title">${aprobado ? '¡Prueba aprobada!' : 'Prueba reprobada'}</h2>
            <p class="final-message">${escaparHtml(mensaje)}</p>
            <div class="final-actions">
            ${botonReintentar}
            ${puedeReenviar ? `<button class="final-button" type="button" data-accion="reenviar" ${enviando ? 'disabled' : ''}>${enviando ? 'Enviando...' : 'Reenviar respuestas'}</button>` : ''}
            <button class="final-button final-button--ghost" type="button" data-accion="ver-revision">Ver mis resultados</button>
            </div>
        </div>
        </div>
    `;
}
