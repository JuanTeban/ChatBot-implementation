document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('chat-form');
    const input = document.getElementById('user-input');
    const chatWindow = document.getElementById('chat-window');
    const sourceSelector = document.getElementById('source-selector'); // Nuevo
    const profileIcon = document.getElementById('profile-icon');
    const profileDropdown = document.getElementById('profile-dropdown');
    
    const CHAT_ENDPOINT = '/chat';
    const SOURCES_ENDPOINT = '/list-sources'; // Nuevo
    const MODEL_NAME = "llama-3.3-70b";

    let selectedSourceId = null; // Nuevo: para guardar la selección

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
        document.getElementById('session-info').innerHTML = `<strong>Session ID:</strong> ${sessionId}`;
        document.getElementById('model-info').innerHTML = `<strong>Model:</strong> ${MODEL_NAME}`;
    }

    // --- NUEVA FUNCIÓN PARA CARGAR Y MOSTRAR LAS FUENTES ---
    async function loadSources() {
        try {
            const res = await fetch(SOURCES_ENDPOINT);
            if (!res.ok) throw new Error('No se pudieron cargar las fuentes de datos.');
            
            const sources = await res.json();
            
            sourceSelector.innerHTML = '<span class="source-selector-title">Consultar en:</span>';

            // Botón por defecto "Autodetectar"
            const autoButton = createSourcePill('Autodetectar', null, true);
            sourceSelector.appendChild(autoButton);

            // Botones para Excel
            sources.excel.forEach(source => {
                const pill = createSourcePill(source.filename, source.id || source.file_id);
                sourceSelector.appendChild(pill);
            });

            // Botones para RAG
            sources.rag.forEach(source => {
                const pill = createSourcePill(source.filename, source.id || source.file_id);
                sourceSelector.appendChild(pill);
            });

        } catch (error) {
            console.error("Error al cargar fuentes:", error);
            sourceSelector.innerHTML = '<span class="source-selector-title">Error al cargar fuentes.</span>';
        }
    }

    // --- NUEVA FUNCIÓN PARA CREAR CADA BOTÓN ---
    function createSourcePill(text, sourceId, isActive = false) {
        const pill = document.createElement('div');
        pill.className = 'source-pill';
        pill.textContent = text;
        pill.dataset.sourceId = sourceId;

        if (isActive) {
            pill.classList.add('active');
            selectedSourceId = sourceId;
        }

        pill.addEventListener('click', () => {
            // Deseleccionar el anterior
            const currentActive = document.querySelector('.source-pill.active');
            if (currentActive) currentActive.classList.remove('active');

            // Seleccionar el nuevo
            pill.classList.add('active');
            selectedSourceId = pill.dataset.sourceId === 'null' ? null : pill.dataset.sourceId;
            console.log("Fuente seleccionada:", selectedSourceId);
        });

        return pill;
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
                model: MODEL_NAME,
                source_id: selectedSourceId // Enviar la fuente seleccionada
            };

            const res = await fetch(CHAT_ENDPOINT, {
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
    
    // --- (El resto de las funciones como addMessage, showTypingIndicator, etc., se mantienen igual) ---

    function addMessage(content, role) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        const avatar = document.createElement('div');
        avatar.className = 'avatar';
        avatar.textContent = role === 'ai' ? 'AI' : 'U';
        messageDiv.appendChild(avatar);
        const bubble = document.createElement('div');
        bubble.className = 'bubble';
        bubble.innerHTML = role === 'ai' ? marked.parse(content) : content;
        messageDiv.appendChild(bubble);
        chatWindow.appendChild(messageDiv);
        scrollToBottom();
    }

    function showTypingIndicator() {
        if (document.getElementById('typing-indicator')) return;
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.className = 'message ai typing';
        typingDiv.innerHTML = `<div class="avatar">AI</div><div class="bubble"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>`;
        chatWindow.appendChild(typingDiv);
        scrollToBottom();
    }

    function removeTypingIndicator() {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) typingIndicator.remove();
    }

    function scrollToBottom() {
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    function initializeChat() {
        updateProfileInfo();
        loadSources(); // Cargar las fuentes al iniciar
        setTimeout(() => {
            addMessage('¡Hola! Soy tu asistente virtual. Elige una fuente de datos o haz una pregunta para que la detecte automáticamente.', 'ai');
        }, 500);
    }

    initializeChat();
    // Manejo del dropdown del perfil (código existente)
    profileIcon.addEventListener('click', () => { profileDropdown.style.display = profileDropdown.style.display === 'block' ? 'none' : 'block'; });
    document.addEventListener('click', (e) => { if (!profileIcon.contains(e.target) && !profileDropdown.contains(e.target)) profileDropdown.style.display = 'none'; });
});