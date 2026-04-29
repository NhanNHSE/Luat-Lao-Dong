/**
 * Main application controller.
 */
const App = {
    init() {
        // Check if user is already logged in
        const token = API.getToken();
        const user = API.getUser();

        if (token && user) {
            this.showChat();
        } else {
            this.showAuth();
        }
        // Initialize toast notifications
        Toast.init();

        // Initialize auth module
        Auth.init();

        // Initialize theme
        this.initTheme();

        // Sidebar toggle for mobile
        const sidebarToggle = document.getElementById('sidebar-toggle');
        const sidebar = document.getElementById('sidebar');

        // Create overlay for mobile
        const overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        document.body.appendChild(overlay);

        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            overlay.classList.toggle('active');
        });

        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            overlay.classList.remove('active');
        });

        // Logout
        document.getElementById('logout-btn').addEventListener('click', () => {
            API.logout();
            this.showAuth();
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl+N: New chat
            if (e.ctrlKey && e.key === 'n') {
                e.preventDefault();
                if (typeof Chat !== 'undefined') Chat.newConversation();
            }
            // Escape: close modal or stop streaming
            if (e.key === 'Escape') {
                const modal = document.getElementById('source-modal');
                if (modal && !modal.classList.contains('hidden')) {
                    Chat.closeSourceModal();
                } else if (Chat.isStreaming) {
                    Chat.stopStreaming();
                }
                // Close mobile sidebar
                sidebar.classList.remove('open');
                overlay.classList.remove('active');
            }
        });
    },

    /**
     * Initialize theme from localStorage.
     */
    initTheme() {
        const saved = localStorage.getItem('theme') || 'dark';
        document.documentElement.setAttribute('data-theme', saved);
        this.updateThemeIcons(saved);

        document.getElementById('theme-toggle').addEventListener('click', () => {
            const current = document.documentElement.getAttribute('data-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('theme', next);
            this.updateThemeIcons(next);
        });
    },

    updateThemeIcons(theme) {
        const darkIcon = document.getElementById('theme-icon-dark');
        const lightIcon = document.getElementById('theme-icon-light');
        if (darkIcon && lightIcon) {
            darkIcon.style.display = theme === 'dark' ? 'block' : 'none';
            lightIcon.style.display = theme === 'light' ? 'block' : 'none';
        }
    },

    /**
     * Show the auth screen.
     */
    showAuth() {
        document.getElementById('auth-screen').classList.remove('hidden');
        document.getElementById('chat-screen').classList.add('hidden');
    },

    /**
     * Show the chat screen and initialize it.
     */
    showChat() {
        document.getElementById('auth-screen').classList.add('hidden');
        document.getElementById('chat-screen').classList.remove('hidden');

        // Set user info
        const user = API.getUser();
        if (user) {
            document.getElementById('user-name').textContent = user.username;
            document.getElementById('user-avatar').textContent = user.username[0].toUpperCase();
        }

        // Initialize chat
        Chat.init();
    },
};

// Start the app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
