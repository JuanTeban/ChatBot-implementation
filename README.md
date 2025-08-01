
<div align="center">
  <img
  src="https://github.com/user-attachments/assets/751fbe75-4008-4ae4-8dd2-9bec02709d49"
  alt="Tabalux"
  width="150"
  height="auto"
/>

  <h1 style="margin-top: 10px;">Tabalux</h1>
</div>

<div align="center">
  <p><strong>Conversa con tus datos usando lenguaje natural.</strong></p>
</div>


---

**Tabalux** es un agente de software que utiliza un framework de **Generación Aumentada por Recuperación (RAG)** para traducir preguntas en lenguaje natural a consultas SQL precisas y ejecutables. Su arquitectura está diseñada para ser robusta, precisa y capaz de aprender de sus propios errores.

## 🧠 Flujo del Agente

Aquí se muestra el flujo de cómo una pregunta del usuario se transforma en una respuesta, pasando por la recuperación de contexto, la generación de SQL y la autocorrección.
<div align="center">
  <img
    src="https://github.com/user-attachments/assets/51635084-5385-410b-a16e-e768de2e75fe"
    alt="Diagrama Tabalux"
    width="900"
    height="1140"
  />
</div>

<div align="center">
  
</div>

---

## 🚀 Características Principales

* **Fundación de Datos de Alto Rendimiento**: Utiliza **Polars** y **DuckDB** para una ingesta y consulta de datos ultra rápida.
* **Contexto Enriquecido**: No solo usa el esquema de la base de datos, sino que enriquece el contexto con metadatos, descripciones y datos de ejemplo para mejorar la precisión.
* **Agente Autocorrectivo**: Construido con **LangGraph**, el agente puede validar sus propias consultas SQL, analizar los errores y corregirlos en un bucle de retroalimentación.
* **Backend Moderno**: Servido a través de una API rápida y eficiente construida con **FastAPI**.

---

## 🔧 Instalación y Configuración

Sigue estos pasos para poner en marcha Tabalux en tu entorno local.

### 1. Clonar el Repositorio

```bash
git clone https://github.com/JuanTeban/ChatBot-implementation.git
cd ChatBot-implementation
```

### 2. Crear y Activar un Entorno Virtual

Es una buena práctica aislar las dependencias del proyecto.

**En macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**En Windows:**
```bash
python -m venv venv
.\venv\Scripts\activate
```

### 3. Instalar Dependencias

El archivo `requirements.txt` contiene todas las librerías de Python necesarias.

```bash
pip install -r requirements.txt
```

### 4. Configurar las Variables de Entorno

Para que Tabalux funcione, necesita acceso a ciertas APIs. Crea un archivo llamado `.env` en la raíz del proyecto y añade tus claves. Puedes usar el archivo `.env.example` como plantilla:

```
# .env

# LLM para razonamiento (ej. OpenAI, Anthropic, Google)
OPENAI_API_KEY="sk-..."

# Llave para Tavily (para futuras integraciones de búsqueda web)
TAVILY_API_KEY="tvly-..."
```

---

▶️ **Uso**

Una vez que hayas configurado tus variables de entorno, puedes iniciar el servidor de FastAPI con el siguiente comando:

```bash
uvicorn app.main:app --reload
```

- `app.main`: archivo `main.py` dentro de la carpeta `app`.  
- `app`: nombre de la instancia de FastAPI dentro de ese archivo.  
- `--reload`: reinicia el servidor automáticamente cada vez que haces cambios en el código.

Ahora podrás acceder a la API y su documentación interactiva en `http://127.0.0.1:8000/docs`.

---

⚙️ **Tecnologías Utilizadas**

| Categoría       | Tecnología                             | Rol Principal                                                       |
|-----------------|----------------------------------------|---------------------------------------------------------------------|
| **Backend**     | FastAPI                                | Para servir el agente a través de una API web de alto rendimiento.  |
| **Datos**       | Polars, DuckDB                         | Para la ingesta, almacenamiento y consulta eficiente de los datos.  |
| **Orquestación AI** | LangChain, LangGraph              | Para construir el flujo del agente, manejar los prompts y la lógica de autocorrección. |
| **Embeddings**  | Sentence Transformers                  | Para convertir el contexto de los datos en vectores numéricos.      |
| **Búsqueda Vectorial** | ChromaDB / FAISS               | Para almacenar y buscar los vectores de contexto de forma semántica.|

---
