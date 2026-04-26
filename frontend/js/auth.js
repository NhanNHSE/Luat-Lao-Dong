/**
 * Authentication module: login/register form handling.
 */
const Auth = {
    init() {
        this.loginForm = document.getElementById('login-form');
        this.registerForm = document.getElementById('register-form');
        this.loginError = document.getElementById('login-error');
        this.registerError = document.getElementById('register-error');

        // Toggle forms
        document.getElementById('show-register').addEventListener('click', (e) => {
            e.preventDefault();
            this.showForm('register');
        });
        document.getElementById('show-login').addEventListener('click', (e) => {
            e.preventDefault();
            this.showForm('login');
        });

        // Submit handlers
        this.loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        this.registerForm.addEventListener('submit', (e) => this.handleRegister(e));
    },

    showForm(type) {
        this.loginError.textContent = '';
        this.registerError.textContent = '';

        if (type === 'register') {
            this.loginForm.classList.remove('active');
            this.registerForm.classList.add('active');
        } else {
            this.registerForm.classList.remove('active');
            this.loginForm.classList.add('active');
        }
    },

    async handleLogin(e) {
        e.preventDefault();
        const btn = document.getElementById('login-btn');
        const username = document.getElementById('login-username').value.trim();
        const password = document.getElementById('login-password').value;

        this.loginError.textContent = '';
        btn.classList.add('loading');
        btn.disabled = true;

        try {
            await API.login(username, password);
            App.showChat();
        } catch (err) {
            this.loginError.textContent = err.message;
        } finally {
            btn.classList.remove('loading');
            btn.disabled = false;
        }
    },

    async handleRegister(e) {
        e.preventDefault();
        const btn = document.getElementById('register-btn');
        const username = document.getElementById('register-username').value.trim();
        const email = document.getElementById('register-email').value.trim();
        const password = document.getElementById('register-password').value;

        this.registerError.textContent = '';
        btn.classList.add('loading');
        btn.disabled = true;

        try {
            await API.register(username, email, password);
            App.showChat();
        } catch (err) {
            this.registerError.textContent = err.message;
        } finally {
            btn.classList.remove('loading');
            btn.disabled = false;
        }
    },
};
