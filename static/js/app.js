document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('chat-form');
    const input = document.getElementById('user-input');
    const chatWindow = document.getElementById('chat-window');
    const profileIcon = document.getElementById('profile-icon');
    const profileDropdown = document.getElementById('profile-dropdown');
    const chatEndpoint = '/chat';

    const MODEL_NAME = "llama-3.3-70b";

    function getOrCreateSessionId() {
        let sessionId = sessionStorage.getItem('chatSessionId');
        if (!sessionId) {
            sessionId = `user-${crypto.randomUUID().slice(0, 8)}`;
            sessionStorage.setItem('chatSessionId', sessionId);
        }
        return sessionId;
    }

    function updateProfileInfo() {
        const sessionId = getOrCreateSessionId();
        const sessionInfoDiv = document.getElementById('session-info');
        const modelInfoDiv = document.getElementById('model-info');
        
        sessionInfoDiv.innerHTML = `<strong>Session ID:</strong> ${sessionId}`;
        modelInfoDiv.innerHTML = `<strong>Model:</strong> ${MODEL_NAME}`;
    }

    profileIcon.addEventListener('click', () => {
        const isDisplayed = profileDropdown.style.display === 'block';
        profileDropdown.style.display = isDisplayed ? 'none' : 'block';
    });

    document.addEventListener('click', (event) => {
        if (!profileIcon.contains(event.target) && !profileDropdown.contains(event.target)) {
            profileDropdown.style.display = 'none';
        }
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const question = input.value.trim();
        if (!question) return;

        addMessage(question, 'human');
        input.value = '';
        showTypingIndicator();

        try {
            const sessionId = getOrCreateSessionId();
            const requestBody = {
                question: question,
                session_id: sessionId,
                model: MODEL_NAME
            };

            const res = await fetch(chatEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });

            if (!res.ok) {
                const errorData = await res.json();
                throw new Error(errorData.detail || `Error del servidor: ${res.status}`);
            }

            const data = await res.json();
            removeTypingIndicator();
            addMessage(data.answer, 'ai');

        } catch (error) {
            removeTypingIndicator();
            addMessage(`Lo siento, ha ocurrido un error: ${error.message}`, 'ai');
            console.error('Error en la petición fetch:', error);
        }
    });

    function addMessage(content, role) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
    
        // --- CÓDIGO NUEVO PARA CREAR EL AVATAR ---
        const avatar = document.createElement('div');
        avatar.className = 'avatar';
    
        if (role === 'ai') {
            avatar.textContent = 'AI';
        } else {
            const sessionId = getOrCreateSessionId();
            // Usamos la inicial del nombre de usuario 'user-...'
            avatar.textContent = sessionId.charAt(0).toUpperCase();
        }
        messageDiv.appendChild(avatar);
        // --- FIN DEL CÓDIGO NUEVO ---
    
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        
        if (role === 'ai') {
            bubble.innerHTML = marked.parse(content);
        } else {
            bubble.textContent = content;
        }
        
        messageDiv.appendChild(bubble);
        chatWindow.appendChild(messageDiv);
        scrollToBottom();
    }

    function showTypingIndicator() {
        if (document.getElementById('typing-indicator')) return;
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.className = 'message ai typing';
        
        typingDiv.innerHTML = `
            <div class="avatar">AI</div>
            <div class="bubble">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
            </div>
        `;
        chatWindow.appendChild(typingDiv);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    function scrollToBottom() {
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    function initializeChat() {
        updateProfileInfo();
        setTimeout(() => {
            addMessage('¡Hola! Soy tu asistente virtual. ¿En qué puedo ayudarte hoy?', 'ai');
        }, 500);
    }

    initializeChat();
});