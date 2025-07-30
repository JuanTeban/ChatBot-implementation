import logging
import uuid
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.models.pydantic_models import QueryInput, QueryResponse
from app.agent.langgraph_agent import get_agent
from langchain_core.messages import HumanMessage, AIMessage

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/chat-ui", response_class=HTMLResponse)
def chat_ui(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request, "messages": []})

@router.post("/chat", response_model=QueryResponse)
async def chat(request: Request, query_input: QueryInput):
    session_id = query_input.session_id or str(uuid.uuid4())
    logging.info(f"Session ID: {session_id}, User Query: {query_input.question}")

    db_conn = getattr(request.app.state, 'db_connection', None)
    enriched_schema = getattr(request.app.state, 'enriched_schema', "")
    sql_keywords = getattr(request.app.state, 'sql_keywords', [])

    if db_conn is None:
        raise HTTPException(status_code=503, detail="La conexión a la base de datos de Excel no está disponible.")

    # --- LÓGICA MODIFICADA ---
    # Pasamos la conexión a través de 'configurable'
    config = {
        "configurable": {
            "thread_id": session_id,
            "db_conn": db_conn,
            "enriched_schema": enriched_schema,
            "sql_keywords": sql_keywords 
        }
    }
    
    input_message = HumanMessage(content=query_input.question)
    initial_state = {"messages": [input_message]}
    # --- FIN DE LA MODIFICACIÓN ---

    try:
        agent = get_agent()
        final_state = await agent.ainvoke(initial_state, config=config)
        
        last_message = next((m for m in reversed(final_state["messages"]) if isinstance(m, AIMessage)), None)
        answer = last_message.content if last_message else "Lo siento, no pude generar una respuesta en este momento."

        logging.info(f"Session ID: {session_id}, AI Response: {answer}")
        return QueryResponse(answer=answer, session_id=session_id, model=query_input.model)

    except Exception as e:
        logging.error(f"Error in chat: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")