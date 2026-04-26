/**
 * API client for communicating with the backend.
 */
const API = {
    BASE_URL: '/api',

    /**
     * Get the stored auth token.
     */
    getToken() {
        return localStorage.getItem('auth_token');
    },

    /**
     * Get stored user info.
     */
    getUser() {
        const data = localStorage.getItem('auth_user');
        return data ? JSON.parse(data) : null;
    },

    /**
     * Save auth data to localStorage.
     */
    saveAuth(token, user) {
        localStorage.setItem('auth_token', token);
        localStorage.setItem('auth_user', JSON.stringify(user));
    },

    /**
     * Clear auth data.
     */
    clearAuth() {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user');
    },

    /**
     * Make an authenticated API request.
     */
    async request(endpoint, options = {}) {
        const token = this.getToken();
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...options.headers,
        };

        const response = await fetch(`${this.BASE_URL}${endpoint}`, {
            ...options,
            headers,
        });

        if (response.status === 401) {
            this.clearAuth();
            window.location.reload();
            throw new Error('Unauthorized');
        }

        return response;
    },

    /**
     * Register a new user.
     */
    async register(username, email, password) {
        const res = await this.request('/auth/register', {
            method: 'POST',
            body: JSON.stringify({ username, email, password }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Đăng ký thất bại');
        this.saveAuth(data.access_token, data.user);
        return data;
    },

    /**
     * Login with username and password.
     */
    async login(username, password) {
        const res = await this.request('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Đăng nhập thất bại');
        this.saveAuth(data.access_token, data.user);
        return data;
    },

    /**
     * Logout.
     */
    logout() {
        this.clearAuth();
    },

    /**
     * Get all conversations (with optional search).
     */
    async getConversations(search = '') {
        const params = search ? `?search=${encodeURIComponent(search)}` : '';
        const res = await this.request(`/chat/conversations${params}`);
        if (!res.ok) throw new Error('Không thể tải danh sách hội thoại');
        return res.json();
    },

    /**
     * Get conversation detail with messages.
     */
    async getConversation(id) {
        const res = await this.request(`/chat/conversations/${id}`);
        if (!res.ok) throw new Error('Không thể tải hội thoại');
        return res.json();
    },

    /**
     * Delete a conversation.
     */
    async deleteConversation(id) {
        const res = await this.request(`/chat/conversations/${id}`, {
            method: 'DELETE',
        });
        if (!res.ok) throw new Error('Không thể xóa hội thoại');
    },

    /**
     * Send a chat message with SSE streaming.
     * Returns an object to control the stream.
     */
    streamChat(message, conversationId = null) {
        const token = this.getToken();
        const body = JSON.stringify({
            message,
            conversation_id: conversationId,
        });

        const controller = new AbortController();

        const promise = fetch(`${this.BASE_URL}/chat/stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
            },
            body,
            signal: controller.signal,
        });

        return {
            promise,
            abort: () => controller.abort(),
        };
    },

    /**
     * Upload a contract file for analysis with SSE streaming.
     * Returns an object to control the stream.
     */
    uploadContract(file) {
        const token = this.getToken();
        const formData = new FormData();
        formData.append('file', file);

        const controller = new AbortController();

        const promise = fetch(`${this.BASE_URL}/contract/analyze`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
            },
            body: formData,
            signal: controller.signal,
        });

        return {
            promise,
            abort: () => controller.abort(),
        };
    },
};
