import logging
import json
import uuid
import re
import os
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from app.models.pydantic_models import QueryInput, QueryResponse, ChartData, ModelName
from app.agent.langgraph_agent import get_agent
from langchain_core.messages import HumanMessage, AIMessage
from app.config.settings import CHARTS_DIR

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/chat-ui", response_class=HTMLResponse)
def chat_ui(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request, "messages": []})

@router.post("/chat", response_model=QueryResponse)
async def chat(query_input: QueryInput):
    session_id = query_input.session_id or str(uuid.uuid4())
    logging.info(f"Session ID: {session_id}, User Query: {query_input.question}")

    config = {"configurable": {"thread_id": session_id}}
    input_message = HumanMessage(content=query_input.question)

    try:
        agent = get_agent()
        final_state = await agent.ainvoke({"messages": [input_message]}, config=config)
        
        last_message = next((m for m in reversed(final_state["messages"]) if isinstance(m, AIMessage)), None)
        answer = last_message.content if last_message else "Lo siento, no pude generar una respuesta en este momento."

        chart_response_data = None
        if final_state.get("chart_spec"):
            try:
                chart_spec = final_state["chart_spec"]
                download_id = str(uuid.uuid4())
                
                chart_filepath = CHARTS_DIR / f"{download_id}.csv"
                with open(chart_filepath, 'w', encoding='utf-8') as f:
                    f.write(chart_spec.get("data_csv", ""))
                
                chart_response_data = ChartData(
                    spec={"data": chart_spec.get("data", []), "layout": chart_spec.get("layout", {})},
                    title=chart_spec.get("title", "Gráfico"),
                    download_id=download_id
                )
                logging.info(f"Chart generated with download_id: {download_id}")
                
            except Exception as e:
                logging.error(f"Error processing chart data for response: {e}")

        logging.info(f"Session ID: {session_id}, AI Response: {answer}")

        return QueryResponse(
            answer=answer, 
            session_id=session_id, 
            model=query_input.model,
            chart=chart_response_data
        )

    except Exception as e:
        logging.error(f"Error in chat: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

@router.get("/download-chart/{download_id}")
async def download_chart(download_id: str):
    if not re.match(r'^[a-f0-9-]+$', download_id):
        raise HTTPException(status_code=400, detail="Invalid download ID format")

    try:
        chart_filepath = CHARTS_DIR / f"{download_id}.csv"
        
        if not chart_filepath.exists():
            raise HTTPException(status_code=404, detail="Chart data not found or has expired.")
        
        with open(chart_filepath, 'r', encoding='utf-8') as f:
            csv_data = f.read()
        
        os.remove(chart_filepath)
        
        filename = f"chart_data_{download_id[:8]}.csv"
        
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logging.error(f"Error downloading chart: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving chart data.")