document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('chat-form');
    const input = document.getElementById('user-input');
    const chatWindow = document.getElementById('chat-window');
    const chatEndpoint = '/chat';

    function getOrCreateSessionId() {
        let sessionId = sessionStorage.getItem('chatSessionId');
        if (!sessionId) {
            sessionId = crypto.randomUUID();
            sessionStorage.setItem('chatSessionId', sessionId);
        }
        return sessionId;
    }

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
                model: "llama-3.3-70b"
            };

            const res = await fetch(chatEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });

            if (!res.ok) {
                throw new Error(`Error del servidor: ${res.status}`);
            }

            const data = await res.json();
            removeTypingIndicator();
            addMessage(data.answer, 'ai');

        } catch (error) {
            removeTypingIndicator();
            addMessage('Lo siento, ha ocurrido un error. Por favor, intenta de nuevo.', 'ai');
            console.error('Error en la petición fetch:', error);
        }
    });

    function addMessage(content, role) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        bubble.textContent = content;
        messageDiv.appendChild(bubble);
        chatWindow.appendChild(messageDiv);
        scrollToBottom();
    }

    function showTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.className = 'message ai typing';
        typingDiv.innerHTML = `
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

    setTimeout(() => {
        addMessage('¡Hola! Soy tu asistente virtual. ¿En qué puedo ayudarte hoy?', 'ai');
    }, 500);
});