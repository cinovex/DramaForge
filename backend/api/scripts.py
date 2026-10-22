from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from services import gpt_service

router = APIRouter(prefix="/api/scripts", tags=["scripts"])


class GenScriptRequest(BaseModel):
    theme: str
    style: str = ""
    episodes: int = 3
    seconds_per_ep: int | None = None


@router.post("/generate")
async def generate(body: GenScriptRequest, db: Session = Depends(get_db)):
    """AI 生成完整剧本文本（供用户确认后再存项目）"""
    try:
        text = await gpt_service.generate_script(
            db,
            theme=body.theme,
            style=body.style,
            episodes=body.episodes,
            seconds_per_ep=body.seconds_per_ep,
        )
        return {"script_text": text}
    except gpt_service.GPTError as e:
        raise HTTPException(e.status_code, e.message)
