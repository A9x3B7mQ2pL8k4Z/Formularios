const VISTA = Object.freeze({
    FORMULARIO: 'formulario',
    RESULTADO: 'resultado',
    REVISION: 'revision'
});

function crearEstadoInicial() {
    return {
        vista: VISTA.FORMULARIO,
        indiceSeccion: 0,
        respuestas: {},    // { [idPregunta]: string | string[] }
        errores: {},       // { [idPregunta]: mensaje }
        resultado: null,   // respuesta del servidor
        enviando: false,
        errorEnvio: ''
    };
}

function obtenerMensajeResultado(resultado, formulario) {
    const puntaje = formulario.puntajeAprobacion;

    if (!resultado.aprobado) {
        return `Obtuviste ${resultado.puntaje}/${formulario.puntajeTotal} puntos. Necesitas ${puntaje} para obtener el certificado. Puedes revisar tus resultados y repetir la prueba.`;
    }
    if (resultado.duplicado) {
        return `¡Aprobaste con ${puntaje} puntos! Ya registramos una solicitud de certificado para tu RUT hoy.`;
    }
    if (resultado.enviado) {
        return `¡Aprobaste con ${puntaje} puntos! Te enviaremos el certificado al correo que ingresaste.`;
    }
    return `¡Aprobaste con ${puntaje} puntos! No pudimos procesar el certificado. Vuelve a enviar tus respuestas o avisa a tu instructor.`;
}

class AppFormulario {
    constructor(raiz, formulario) {
        this.raiz = raiz;
        this.formulario = formulario;
        this.estado = crearEstadoInicial();
        this.enlazarEventos();
    }

    get seccionActual() {
        return this.formulario.secciones[this.estado.indiceSeccion];
    }

    /* ---------- Renderizado ---------- */

    renderizar({ reiniciarScroll = true } = {}) {
        const posiciones = ['.page-container', '.form-card'].map(selector => ({
            selector,
            top: this.raiz.querySelector(selector)?.scrollTop || 0
        }));
        this.raiz.innerHTML = this.crearVista();
        if (reiniciarScroll) {
            this.irArriba();
        } else {
            this.raiz.querySelector('.page-container')?.classList.add('sin-animacion');
            posiciones.forEach(({ selector, top }) => {
                this.raiz.querySelector(selector)?.scrollTo({ top, behavior: 'instant' });
            });
        }
    }

    crearVista() {
        const { vista, respuestas, resultado } = this.estado;

        switch (vista) {
            case VISTA.REVISION:
                return crearPaginaDeRevision(this.formulario, { respuestas, resultado });
            case VISTA.RESULTADO:
                return crearPaginaDeResultado({
                    aprobado: resultado.aprobado,
                    enviando: this.estado.enviando,
                    mensaje: obtenerMensajeResultado(resultado, this.formulario),
                    puedeReintentar: !resultado.aprobado,
                    puedeReenviar: !resultado.enviado
                });
            default:
                return crearPaginaDeFormulario(this.formulario, this.estado);
        }
    }

    irArriba() {
        window.scrollTo({ top: 0, behavior: 'instant' });
        this.raiz.querySelector('.page-container')?.scrollTo({ top: 0, behavior: 'instant' });
        this.raiz.querySelector('.form-card')?.scrollTo({ top: 0, behavior: 'instant' });
    }

    /* ---------- Navegación ---------- */

    cambiarVista(vista) {
        this.estado.vista = vista;
        this.renderizar();
    }

    irASeccion(indice) {
        this.estado.indiceSeccion = indice;
        this.cambiarVista(VISTA.FORMULARIO);
    }

    irASiguienteSeccion() {
        const errores = validarPreguntas(this.seccionActual.preguntas, this.estado.respuestas);

        if (Object.keys(errores).length > 0) {
            this.mostrarErrores(errores);
            return;
        }

        this.irASeccion(this.estado.indiceSeccion + 1);
    }

    irASeccionAnterior() {
        this.irASeccion(this.estado.indiceSeccion - 1);
    }

    /* ---------- Errores ---------- */

    mostrarErrores(errores) {
        this.estado.errores = errores;
        this.renderizar({ reiniciarScroll: false });

        this.raiz
            .querySelector('.question--invalid')
            ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    limpiarError(idPregunta) {
        delete this.estado.errores[idPregunta];

        const pregunta = this.raiz.querySelector(`#pregunta-${idPregunta}`);
        if (!pregunta) return; // Evita fallar si el elemento no existe en el DOM

        pregunta.classList.remove('question--invalid');

        const mensajeError = pregunta.querySelector('.question-error');
        if (mensajeError) mensajeError.textContent = '';
    }

    buscarIndiceDeSeccion(idPregunta) {
        return this.formulario.secciones.findIndex(seccion =>
            seccion.preguntas.some(pregunta => pregunta.id === idPregunta)
        );
    }

    /* ---------- Envío ---------- */

    async enviar() {
        if (this.estado.enviando) return;
        const todasLasPreguntas = this.formulario.secciones.flatMap(seccion => seccion.preguntas);
        const errores = validarPreguntas(todasLasPreguntas, this.estado.respuestas);
        const [idPrimerError] = Object.keys(errores);

        if (idPrimerError !== undefined) {
            this.estado.indiceSeccion = this.buscarIndiceDeSeccion(idPrimerError);
            this.mostrarErrores(errores);
            return;
        }

        this.estado.enviando = true;
        this.estado.errorEnvio = '';
        this.renderizar({ reiniciarScroll: false });

        try {
            const { ok, estado, datos } = await enviarRespuestas(this.formulario.id, this.estado.respuestas);
            this.estado.enviando = false;

            if (ok) {
                this.estado.resultado = datos;
                this.cambiarVista(VISTA.RESULTADO);
                return;
            }

            if (estado === 422 && datos.errores) {
                // El servidor rechazó respuestas: se muestran igual que los errores locales
                const errores = datos.errores;
                const [idPrimerErrorServidor] = Object.keys(errores);
                this.estado.indiceSeccion = Math.max(this.buscarIndiceDeSeccion(idPrimerErrorServidor), 0);
                this.mostrarErrores(errores);
                return;
            }

            this.estado.errorEnvio = datos.error || 'No pudimos enviar tus respuestas. Inténtalo nuevamente.';
        } catch (error) {
            this.estado.enviando = false;
            this.estado.errorEnvio = 'No hay conexión con el servidor. Inténtalo nuevamente.';
        }

        this.renderizar({ reiniciarScroll: false });
    }

    reintentar() {
        this.estado = crearEstadoInicial();
        this.renderizar();
    }

    /* ---------- Eventos ---------- */

    enlazarEventos() {
        this.raiz.addEventListener('input', evento => this.alEscribir(evento));
        this.raiz.addEventListener('change', evento => this.alElegirOpcion(evento));
        this.raiz.addEventListener('click', evento => this.alHacerClic(evento));
    }

    alEscribir(evento) {
        const campo = evento.target.closest('.text-field');
        if (!campo) return;

        const idPregunta = campo.dataset.idPregunta;

        this.estado.respuestas[idPregunta] = campo.value;
        this.limpiarError(idPregunta);
    }

    alElegirOpcion(evento) {
        const input = evento.target.closest('.option-input');
        if (!input) return;

        const idPregunta = input.dataset.idPregunta;
        const valoresMarcados = [...this.raiz.querySelectorAll(`input[name="pregunta-${idPregunta}"]:checked`)]
            .map(marcado => marcado.value);

        this.estado.respuestas[idPregunta] = input.type === 'checkbox'
            ? valoresMarcados
            : valoresMarcados[0];

        this.limpiarError(idPregunta);
    }

    alHacerClic(evento) {
        const boton = evento.target.closest('[data-accion]');
        if (!boton) return;

        switch (boton.dataset.accion) {
            case 'siguiente':
                this.irASiguienteSeccion();
                break;
            case 'anterior':
                this.irASeccionAnterior();
                break;
            case 'enviar':
            case 'reenviar':
                this.enviar();
                break;
            case 'ver-revision':
                this.cambiarVista(VISTA.REVISION);
                break;
            case 'volver-al-resultado':
                this.cambiarVista(VISTA.RESULTADO);
                break;
            case 'reintentar':
                this.reintentar();
                break;
        }
    }
}

/* ---------- Arranque ---------- */

/**
 * Muestra un error visible en la página (además de la consola),
 * para no depender de abrir las DevTools.
 */
function mostrarErrorDeArranque(raiz, titulo, detalle) {
    console.error(`[Arranque] ${titulo}`, detalle ?? '');

    const destino = raiz ?? document.body;
    destino.innerHTML = `
        <div class="app-error" style="padding:16px;border:1px solid #c00;color:#c00;font-family:monospace;">
            <strong>${titulo}</strong>
            ${detalle ? `<pre style="white-space:pre-wrap;">${String(detalle)}</pre>` : ''}
        </div>`;
}

async function iniciarApp() {
    console.group('Diagnóstico de arranque');

    // 1. ¿Existe el contenedor #app?
    const raiz = document.getElementById('app');
    console.log('1. Elemento #app:', raiz);

    if (!raiz) {
        console.groupEnd();
        mostrarErrorDeArranque(null, 'No existe el elemento con id="app" en el HTML.');
        return;
    }

    // 2. ¿Llega el id del formulario? (requiere data-id-formulario="..." en el HTML)
    const idFormulario = raiz.dataset.idFormulario;
    console.log('2. data-id-formulario:', idFormulario, '| dataset completo:', { ...raiz.dataset });

    if (idFormulario === undefined) {
        console.groupEnd();
        mostrarErrorDeArranque(
            raiz,
            'Falta el atributo data-id-formulario en #app.',
            'Debe verse así: <div id="app" data-id-formulario="1"></div>'
        );
        return;
    }

    // 3. ¿Están cargadas las funciones de los otros scripts?
    const dependencias = {
        cargarFormulario: typeof cargarFormulario,
        validarPreguntas: typeof validarPreguntas,
        crearPaginaDeFormulario: typeof crearPaginaDeFormulario,
        crearPaginaDeResultado: typeof crearPaginaDeResultado,
        crearPaginaDeRevision: typeof crearPaginaDeRevision
    };
    console.log('3. Dependencias (deben ser "function"):', dependencias);

    const faltantes = Object.entries(dependencias)
        .filter(([, tipo]) => tipo !== 'function')
        .map(([nombre]) => nombre);

    if (faltantes.length > 0) {
        console.groupEnd();
        mostrarErrorDeArranque(
            raiz,
            'Faltan funciones: revisa que los <script> estén cargados y en orden.',
            `No definidas: ${faltantes.join(', ')}\n\n` +
            'El orden correcto es: validadores.js → constructor.js → api.js → app-formulario.js'
        );
        return;
    }

    // 4. Cargar el formulario capturando cualquier error que lance la función
    let formulario = null;
    try {
        formulario = await cargarFormulario(idFormulario);
        console.log('4. Formulario cargado:', formulario);
    } catch (error) {
        console.groupEnd();
        mostrarErrorDeArranque(
            raiz,
            'cargarFormulario() lanzó un error.',
            `${error?.name ?? 'Error'}: ${error?.message || '(sin mensaje)'}\n\n${error?.stack ?? ''}`
        );
        return;
    }

    // 5. Verificar que el formulario tenga la estructura esperada
    if (!formulario) {
        console.groupEnd();
        mostrarErrorDeArranque(raiz, `Formulario no encontrado (id: "${idFormulario}").`);
        return;
    }

    if (!Array.isArray(formulario.secciones) || formulario.secciones.length === 0) {
        console.groupEnd();
        mostrarErrorDeArranque(
            raiz,
            'El formulario no tiene "secciones" válidas.',
            JSON.stringify(formulario, null, 2)
        );
        return;
    }

    console.groupEnd();

    // 6. Arrancar la aplicación, también protegida
    try {
        document.title = formulario.titulo;
        new AppFormulario(raiz, formulario).renderizar();
    } catch (error) {
        mostrarErrorDeArranque(
            raiz,
            'Error al renderizar el formulario.',
            `${error?.name ?? 'Error'}: ${error?.message || '(sin mensaje)'}\n\n${error?.stack ?? ''}`
        );
    }
}

// Espera a que el DOM esté listo (por si el script se carga en <head>)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciarApp);
} else {
    iniciarApp();
}
