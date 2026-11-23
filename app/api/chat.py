from fastapi import APIRouter, Depends

from app.api.deps import get_services
from app.chat import ask
from app.schemas import ChatRequest, ChatResponse
from app.services import Services

router = APIRouter(tags=["chat"])


@router.post("/main/chat", response_model=ChatResponse)
async def main_chat(body: ChatRequest, services: Services = Depends(get_services)) -> dict:
    """Answer a question from the SOP documents, with checked citations.

    `status` is a domain outcome (answered / partial / no_answer / out_of_scope / unsafe) and is
    always returned with HTTP 200. A failing dependency (LLM, embeddings, Qdrant) returns 503.
    """
    return await ask(services, body.question, top_k=body.top_k)
