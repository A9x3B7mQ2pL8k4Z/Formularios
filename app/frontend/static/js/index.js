// 1. Función para mostrar la vista de Login
function mostrarLogin() {
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
    const login = document.getElementById('view-login');
    if (login) login.classList.add('active');
}

// 2. Función para mostrar la vista de Error
function mostrarError() {
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
    const error = document.getElementById('view-error');
    if (error) error.classList.add('active');
}

// Por defecto se muestra el error de acceso (el servidor entrega esta página
// cuando el token falta, expiró o no es válido). El login admin: /?vista=login
if (new URLSearchParams(window.location.search).get('vista') === 'login') {
    mostrarLogin();
} else {
    mostrarError();
}