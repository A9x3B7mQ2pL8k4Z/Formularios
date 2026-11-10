/**
 * Reglas de validación.
 * Cada función devuelve un mensaje de error, o '' cuando la respuesta es válida.
 */

const PONDERADORES_RUT = [2, 3, 4, 5, 6, 7];
const PATRON_CORREO = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function esRutValido(valor) {
    const coincidencia = /^(\d{7,8})-([\dkK])$/.exec(valor);
    if (!coincidencia) return false;

    const [, cuerpo, digitoVerificador] = coincidencia;

    const suma = [...cuerpo]
        .reverse()
        .reduce((total, digito, indice) => total + Number(digito) * PONDERADORES_RUT[indice % PONDERADORES_RUT.length], 0);

    const resto = 11 - (suma % 11);
    const esperado = resto === 11 ? '0' : resto === 10 ? 'K' : String(resto);

    return esperado === digitoVerificador.toUpperCase();
}

const REGLAS_DE_FORMATO = {
    rut: {
        esValido: esRutValido,
        mensaje: 'Ingrese un RUT válido (sin puntos y con guión). Ej: 12345678-5'
    },
    email: {
        esValido: valor => PATRON_CORREO.test(valor),
        mensaje: 'Ingrese un correo electrónico válido.'
    }
};

function estaVacia(respuesta) {
    return Array.isArray(respuesta)
        ? respuesta.length === 0
        : String(respuesta ?? '').trim() === '';
}

function validarRespuesta(pregunta, respuesta) {
    if (estaVacia(respuesta)) return 'Esta pregunta es obligatoria.';

    const regla = REGLAS_DE_FORMATO[pregunta.validacion];
    if (regla && !regla.esValido(String(respuesta).trim())) return regla.mensaje;

    return '';
}

/**
 * Valida una lista de preguntas.
 * Devuelve { [idPregunta]: mensaje } solo con las que tienen error.
 */
function validarPreguntas(preguntas, respuestas) {
    const errores = {};

    for (const pregunta of preguntas) {
        const mensaje = validarRespuesta(pregunta, respuestas[pregunta.id]);
        if (mensaje) errores[pregunta.id] = mensaje;
    }

    return errores;
}