/**
 * Chat module: messaging, streaming, conversation management.
 * Uses marked.js for proper Markdown rendering.
 */
const Chat = {
    currentConversationId: null,
    isStreaming: false,
    currentStreamController: null,
    searchTimeout: null,

    init() {
        this.messagesContainer = document.getElementById('messages-container');
        this.messagesArea = document.getElementById('messages-area');
        this.welcomeScreen = document.getElementById('welcome-screen');
        this.messageInput = document.getElementById('message-input');
        this.sendBtn = document.getElementById('send-btn');
        this.conversationsList = document.getElementById('conversations-list');
        this.searchInput = document.getElementById('search-conversations');

        // Configure marked.js
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                breaks: true,
                gfm: true,
                headerIds: false,
                mangle: false,
            });
        }

        // Send message
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Auto-resize textarea
        this.messageInput.addEventListener('input', () => {
            this.messageInput.style.height = 'auto';
            this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 150) + 'px';
            this.sendBtn.disabled = !this.messageInput.value.trim();
        });

        // New chat button
        document.getElementById('new-chat-btn').addEventListener('click', () => {
            this.newConversation();
        });

        // Suggested questions
        document.querySelectorAll('.suggestion-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const question = chip.dataset.question;
                this.messageInput.value = question;
                this.sendBtn.disabled = false;
                this.sendMessage();
            });
        });

        // Search conversations with debounce
        if (this.searchInput) {
            this.searchInput.addEventListener('input', () => {
                clearTimeout(this.searchTimeout);
                this.searchTimeout = setTimeout(() => {
                    this.loadConversations(this.searchInput.value.trim());
                }, 300);
            });
        }

        this.loadConversations();
    },

    /**
     * Load conversation list in sidebar (with optional search).
     */
    async loadConversations(searchTerm = '') {
        try {
            const conversations = await API.getConversations(searchTerm);
            this.renderConversationsList(conversations);
        } catch (err) {
            console.error('Failed to load conversations:', err);
        }
    },

    renderConversationsList(conversations) {
        if (!conversations.length) {
            const msg = this.searchInput?.value?.trim()
                ? 'Không tìm thấy hội thoại phù hợp'
                : 'Chưa có cuộc trò chuyện nào';
            this.conversationsList.innerHTML = `
                <div style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 0.85rem;">
                    ${msg}
                </div>
            `;
            return;
        }

        this.conversationsList.innerHTML = conversations.map(conv => `
            <div class="conversation-item ${conv.id === this.currentConversationId ? 'active' : ''}"
                 data-id="${conv.id}" onclick="Chat.selectConversation('${conv.id}')">
                <span class="conv-icon">💬</span>
                <span class="conv-title">${this.escapeHtml(conv.title)}</span>
                <button class="conv-delete" onclick="event.stopPropagation(); Chat.deleteConversation('${conv.id}')" title="Xóa">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                </button>
            </div>
        `).join('');
    },

    /**
     * Select and load a conversation.
     */
    async selectConversation(id) {
        this.currentConversationId = id;

        // Update active state in sidebar
        document.querySelectorAll('.conversation-item').forEach(el => {
            el.classList.toggle('active', el.dataset.id === id);
        });

        // Show messages area
        this.welcomeScreen.classList.add('hidden');
        this.messagesArea.classList.remove('hidden');

        try {
            const conv = await API.getConversation(id);
            this.renderMessages(conv.messages);
        } catch (err) {
            Toast.error('Không thể tải hội thoại');
        }

        // Close sidebar on mobile
        document.getElementById('sidebar').classList.remove('open');
        const overlay = document.querySelector('.sidebar-overlay');
        if (overlay) overlay.classList.remove('active');
    },

    /**
     * Start a new conversation.
     */
    newConversation() {
        this.currentConversationId = null;
        this.messagesContainer.innerHTML = '';
        this.messagesArea.classList.add('hidden');
        this.welcomeScreen.classList.remove('hidden');

        // Clear active state
        document.querySelectorAll('.conversation-item').forEach(el => {
            el.classList.remove('active');
        });

        this.messageInput.focus();
    },

    /**
     * Delete a conversation.
     */
    async deleteConversation(id) {
        if (!confirm('Bạn có chắc muốn xóa cuộc trò chuyện này?')) return;

        try {
            await API.deleteConversation(id);
            if (this.currentConversationId === id) {
                this.newConversation();
            }
            this.loadConversations();
            Toast.success('Đã xóa cuộc trò chuyện');
        } catch (err) {
            Toast.error('Không thể xóa cuộc trò chuyện');
        }
    },

    /**
     * Render messages in the chat area.
     */
    renderMessages(messages) {
        const user = API.getUser();
        this.messagesContainer.innerHTML = messages.map(msg => {
            const avatar = msg.role === 'user'
                ? (user?.username?.[0]?.toUpperCase() || 'U')
                : '⚖️';
            const sources = msg.sources ? JSON.parse(msg.sources) : [];

            return `
                <div class="message ${msg.role}">
                    <div class="message-avatar">${avatar}</div>
                    <div class="message-body">
                        <div class="message-content">${msg.role === 'assistant' ? this.renderMarkdown(msg.content) : this.escapeHtml(msg.content)}</div>
                        ${sources.length ? this.renderSources(sources) : ''}
                    </div>
                </div>
            `;
        }).join('');

        this.scrollToBottom();
    },

    /**
     * Send a message and handle streaming response.
     */
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || this.isStreaming) return;

        this.isStreaming = true;
        this.sendBtn.disabled = true;
        this.messageInput.value = '';
        this.messageInput.style.height = 'auto';

        // Show messages area
        this.welcomeScreen.classList.add('hidden');
        this.messagesArea.classList.remove('hidden');

        // Render user message
        const user = API.getUser();
        const userAvatar = user?.username?.[0]?.toUpperCase() || 'U';
        this.messagesContainer.innerHTML += `
            <div class="message user">
                <div class="message-avatar">${userAvatar}</div>
                <div class="message-body">
                    <div class="message-content">${this.escapeHtml(message)}</div>
                </div>
            </div>
        `;

        // Render assistant placeholder with typing indicator
        const assistantMsgId = 'msg-' + Date.now();
        this.messagesContainer.innerHTML += `
            <div class="message assistant" id="${assistantMsgId}">
                <div class="message-avatar">⚖️</div>
                <div class="message-body">
                    <div class="message-content">
                        <div class="typing-indicator">
                            <span></span><span></span><span></span>
                        </div>
                    </div>
                    <div class="message-sources"></div>
                </div>
            </div>
        `;
        this.scrollToBottom();

        // Start streaming
        const { promise, abort } = API.streamChat(message, this.currentConversationId);
        this.currentStreamController = { abort };

        try {
            const response = await promise;

            if (response.status === 429) {
                Toast.warning('Bạn đang gửi quá nhanh. Vui lòng chờ một chút.');
                const msgEl = document.getElementById(assistantMsgId);
                if (msgEl) {
                    msgEl.querySelector('.message-content').innerHTML =
                        `<span style="color: var(--warning);">⚠️ Giới hạn tốc độ. Vui lòng thử lại sau.</span>`;
                }
                return;
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';
            const msgEl = document.getElementById(assistantMsgId);
            const contentEl = msgEl.querySelector('.message-content');
            const sourcesEl = msgEl.querySelector('.message-sources');

            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line in buffer

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const jsonStr = line.slice(6).trim();
                    if (!jsonStr) continue;

                    try {
                        const data = JSON.parse(jsonStr);

                        if (data.type === 'meta') {
                            this.currentConversationId = data.conversation_id;
                        } else if (data.type === 'chunk') {
                            fullText += data.content;
                            contentEl.innerHTML = this.renderMarkdown(fullText);
                            this.scrollToBottom();
                        } else if (data.type === 'sources') {
                            sourcesEl.innerHTML = this.renderSources(data.sources);
                        } else if (data.type === 'title_update') {
                            // Update conversation title in sidebar
                            this.updateConversationTitle(this.currentConversationId, data.title);
                        } else if (data.type === 'error') {
                            contentEl.innerHTML = `<span style="color: var(--error);">❌ Lỗi: ${this.escapeHtml(data.message)}</span>`;
                            Toast.error(data.message);
                        }
                    } catch (e) {
                        // Skip invalid JSON
                    }
                }
            }

            // Reload conversations to get updated list
            this.loadConversations();

        } catch (err) {
            if (err.name !== 'AbortError') {
                const msgEl = document.getElementById(assistantMsgId);
                if (msgEl) {
                    msgEl.querySelector('.message-content').innerHTML =
                        `<span style="color: var(--error);">❌ Không thể kết nối đến server. Vui lòng thử lại.</span>`;
                }
                Toast.error('Không thể kết nối đến server');
            }
        } finally {
            this.isStreaming = false;
            this.sendBtn.disabled = !this.messageInput.value.trim();
            this.currentStreamController = null;
        }
    },

    /**
     * Update a conversation title in the sidebar without full reload.
     */
    updateConversationTitle(convId, newTitle) {
        const item = document.querySelector(`.conversation-item[data-id="${convId}"]`);
        if (item) {
            const titleEl = item.querySelector('.conv-title');
            if (titleEl) titleEl.textContent = newTitle;
        }
    },

    /**
     * Render source citation tags.
     */
    renderSources(sources) {
        if (!sources || !sources.length) return '';
        return `
            <div class="message-sources">
                ${sources.map(s => `
                    <span class="source-tag" title="${this.escapeHtml(s.content_preview || '')}">
                        📖 ${this.escapeHtml(s.article || 'N/A')}
                    </span>
                `).join('')}
            </div>
        `;
    },

    /**
     * Render markdown using marked.js (with fallback).
     */
    renderMarkdown(text) {
        if (!text) return '';

        // Use marked.js if available
        if (typeof marked !== 'undefined') {
            try {
                return marked.parse(text);
            } catch (e) {
                console.warn('marked.js error, using fallback:', e);
            }
        }

        // Fallback: simple markdown
        let html = this.escapeHtml(text);
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
        html = html.replace(/^### (.*$)/gm, '<h3>$1</h3>');
        html = html.replace(/^## (.*$)/gm, '<h2>$1</h2>');
        html = html.replace(/^# (.*$)/gm, '<h1>$1</h1>');
        html = html.replace(/\n/g, '<br>');
        return html;
    },

    /**
     * Escape HTML special characters.
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    /**
     * Scroll chat to bottom.
     */
    scrollToBottom() {
        this.messagesArea.scrollTop = this.messagesArea.scrollHeight;
    },
};
