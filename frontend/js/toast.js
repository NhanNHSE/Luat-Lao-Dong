/**
 * Toast notification system.
 */
const Toast = {
    container: null,

    init() {
        this.container = document.getElementById('toast-container');
    },

    /**
     * Show a toast notification.
     * @param {string} message - Message to display
     * @param {'success'|'error'|'warning'} type - Toast type
     * @param {number} duration - Auto-dismiss time in ms (default 4000)
     */
    show(message, type = 'error', duration = 4000) {
        const icons = { success: '✅', error: '❌', warning: '⚠️' };
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <span class="toast-icon">${icons[type]}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="Toast.dismiss(this.parentElement)">✕</button>
        `;
        this.container.appendChild(toast);

        // Auto-dismiss
        setTimeout(() => this.dismiss(toast), duration);
    },

    /**
     * Dismiss a toast with animation.
     */
    dismiss(toast) {
        if (!toast || !toast.parentElement) return;
        toast.classList.add('hiding');
        setTimeout(() => toast.remove(), 300);
    },

    success(message) { this.show(message, 'success'); },
    error(message) { this.show(message, 'error'); },
    warning(message) { this.show(message, 'warning'); },
};
