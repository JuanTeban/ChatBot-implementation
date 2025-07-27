import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from app.models.pydantic_models import QueryInput, QueryResponse, ModelName
from app.utils.db_utils import insert_chat_history, get_chat_history
from app.utils.utils import get_or_create_session_id, history_to_lc_messages, append_message
from app.utils.langchain_utils import contextualise_chain
from app.agent.langgraph_agent import agent
from langchain_core.messages import HumanMessage, AIMessage

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/chat-ui", response_class=HTMLResponse)
def chat_ui(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request, "messages": []})

@router.post("/chat", response_model=QueryResponse)
async def chat(query_input: QueryInput):
    session_id = get_or_create_session_id(query_input.session_id)
    logging.info(f"Session ID: {session_id}, User Query: {query_input.question}, Model: {query_input.model.value}")

    try:
        chat_history = get_chat_history(session_id)
        messages = history_to_lc_messages(chat_history)

        print("\n\n--- DEBUG: HISTORIAL DE CHAT DE LA SESIÓN---")
        print(f"Historial para Session ID: {session_id}")

        if not messages:
            print("El historial de chat está VACÍO.")
        else:
            for i, msg in enumerate(messages):
                # Imprimimos el tipo de mensaje (Human/AI) y su contenido
                print(f"  Mensaje {i+1} ({type(msg).__name__}): {msg.content}")
        print("--------------------------------------------------\n")
        # --- FIN DEBUG ---
        
        standalone_q = await contextualise_chain.ainvoke({
            "chat_history": messages,
            "input": query_input.question,
        })

        # --- INICIO DEBUG---
        print("\n\n--- DEBUG: ENTRADA AL AGENTE---")
        print(f"Pregunta Original: '{query_input.question}'")
        print(f"Pregunta Procesada (Standalone): '{standalone_q}'")
        print("------------------------------------------\n")
        # --- FIN DEBUG ---

        messages = append_message(messages, HumanMessage(content=standalone_q))
        
        result = await agent.ainvoke({"messages": messages})

        last_message = next((m for m in reversed(result["messages"]) if isinstance(m, AIMessage)), None)
        
        answer = last_message.content if last_message else "I apologize, but I couldn't generate a response at this time."

        insert_chat_history(session_id, query_input.question, answer, query_input.model.value)
        logging.info(f"Session ID: {session_id}, AI Response: {answer}")

        return QueryResponse(answer=answer, session_id=session_id, model=query_input.model)

    except Exception as e:
        logging.error(f"Error in chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

