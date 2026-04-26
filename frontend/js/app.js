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
