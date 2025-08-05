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
            
            addMessage(data.answer, 'ai', data.chart);

        } catch (error) {
            removeTypingIndicator();
            addMessage(`Lo siento, ha ocurrido un error: ${error.message}`, 'ai');
            console.error('Error en la petición fetch:', error);
        }
    });

    function addMessage(content, role, chartData = null) {
        const messageRow = document.createElement('div');
        messageRow.className = `message ${role}`;
    
        const avatar = document.createElement('div');
        avatar.className = 'avatar';
        if (role === 'ai') {
            const avatarImg = document.createElement('img');
            avatarImg.src = '/static/img/logo.png';
            avatarImg.alt = 'AI Avatar';
            avatar.appendChild(avatarImg);
        } else {
            const sessionId = getOrCreateSessionId();
            const initial = sessionId.split('-')[1] ? sessionId.split('-')[1].charAt(0).toUpperCase() : 'U';
            avatar.textContent = initial;
        }
        messageRow.appendChild(avatar);
    
        const contentContainer = document.createElement('div');
        contentContainer.className = 'content-container';

        const hasText = content && content.trim();
        const hasChart = chartData && role === 'ai';

        if (!hasText && !hasChart) {
            return;
        }

        if (hasText) {
            const bubble = document.createElement('div');
            bubble.className = 'bubble';
            if (role === 'ai') {
                bubble.innerHTML = marked.parse(content);
            } else {
                bubble.textContent = content;
            }
            contentContainer.appendChild(bubble);
        }

        if (hasChart) {
            const chartElement = createChartElement(chartData);
            contentContainer.appendChild(chartElement);
        }
        
        messageRow.appendChild(contentContainer);
        chatWindow.appendChild(messageRow);
        scrollToBottom();
    }

    function createChartElement(chart) {
        const chartWrapper = document.createElement('div');
        chartWrapper.className = 'chart-wrapper';
      
        /* ---------- encabezado ---------- */
        const header = document.createElement('div');
        header.className = 'chart-header-ui';
      
        const title = document.createElement('h3');
        title.className = 'chart-title';
        title.textContent = chart.title || 'Gráfico de Datos';
      
        const downloadBtn = document.createElement('button');
        downloadBtn.className = 'download-btn';
        downloadBtn.innerHTML =
          `<svg fill="currentColor" width="14" height="14" viewBox="0 0 24 24">
             <path d="M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z"/>
           </svg> CSV`;
        downloadBtn.onclick = () => downloadChartData(chart.download_id, downloadBtn);
      
        header.append(title, downloadBtn);
      
        /* ---------- contenedor del gráfico ---------- */
        const plotDiv = document.createElement('div');
        plotDiv.className = 'chart-plot';
        plotDiv.id = `chart-${chart.download_id}`;
        plotDiv.style.minHeight = '350px';
      
        /* agrega ambos nodos al wrapper (ya existe header) */
        chartWrapper.append(header, plotDiv);
      
        /* ---------- render después del primer repintado ---------- */
        requestAnimationFrame(() => {
          const spec = chart.spec || {};
          let traces  = spec.data || spec.traces || [];
          if (!Array.isArray(traces)) traces = [traces];   // normaliza
      
          const layout = { autosize: true, ...(spec.layout || {}), title: chart.title };
      
          if (traces.length && window.Plotly) {
            Plotly.newPlot(plotDiv, traces, layout, { responsive: true })
                  .catch(err => {
                    console.error('Plotly error:', err);
                    plotDiv.textContent = 'Error al dibujar el gráfico.';
                  });
          } else {
            plotDiv.textContent = 'No se encontraron datos para el gráfico.';
          }
        });
      
        return chartWrapper;
      }
      
      

    async function downloadChartData(downloadId, button) {
        button.disabled = true;
        button.textContent = 'Descargando...';
        try {
            const response = await fetch(`/download-chart/${downloadId}`);
            if (!response.ok) throw new Error('Error en la descarga');
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = `chart_data_${downloadId.substring(0, 8)}.csv`;
            if (contentDisposition) {
                const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
                if (filenameMatch && filenameMatch.length > 1) {
                    filename = filenameMatch[1];
                }
            }
            a.download = filename;
            
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (error) {
            console.error('Error al descargar:', error);
            alert('No se pudo descargar el archivo.');
        } finally {
            button.disabled = false;
            button.innerHTML = `<svg fill="currentColor" width="14" height="14" viewBox="0 0 24 24"><path d="M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z" /></svg> CSV`;
        }
    }
    
    function showTypingIndicator() {
        if (document.getElementById('typing-indicator')) return;
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.className = 'message ai typing';
        
        typingDiv.innerHTML = `
            <div class="avatar">
                <img src="/static/img/logo.png" alt="AI Avatar">
            </div>
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
            addMessage('¡Hola! Soy tu asistente virtual. ¿En qué puedo ayudarte hoy? Ahora también puedo generar gráficos si me lo solicitas.', 'ai');
        }, 500);
    }

    initializeChat();
});