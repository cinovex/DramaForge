"""通用 GPT 文本调用（用 script 环节的配置，可插拔）"""
import asyncio
import httpx
from sqlalchemy.orm import Session
from services.settings_service import get_stage_config


class GPTError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def chat_completion(
    db: Session,
    system_prompt: str,
    user_prompt: str,
    stage: str = "script",
    model: str | None = None,
    temperature: float = 0.4,
    json_mode: bool = False,
    max_tokens: int = 4096,
) -> str:
    """调用 script 环节配置的模型，返回文本内容"""
    cfg = get_stage_config(db, stage)
    if not cfg or not cfg.get("api_key"):
        raise GPTError("未配置剧本分析环节的 API Key，请到设置中心填写", 400)

    base_url = cfg["base_url"].rstrip("/")
    model = model or cfg.get("model", "gpt-4o")
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    # New GPT reasoning models reject the legacy max_tokens parameter and do
    # not accept a custom temperature. Keep older-model behavior unchanged.
    if model.startswith(("gpt-5", "gpt-6")):
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["temperature"] = temperature
        payload["max_tokens"] = max_tokens
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    request_timeout = 1800 if max_tokens >= 128000 else 180
    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            token_field = "max_completion_tokens" if model.startswith(("gpt-5", "gpt-6")) else "max_tokens"
            first_limit = payload[token_field]
            retry_limit = max(first_limit, min(max(first_limit * 2, first_limit + 4096), 32768))
            for attempt in range(2):
                async with asyncio.timeout(request_timeout):
                    resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
                if resp.status_code == 401:
                    raise GPTError("API Key 无效（401）", 401)
                if resp.status_code == 402:
                    raise GPTError("余额不足（402）", 402)
                if resp.status_code == 404:
                    raise GPTError(f"模型 {model} 不存在（404）", 404)
                if resp.is_error:
                    detail = ""
                    try:
                        body = resp.json()
                        detail = (body.get("error") or {}).get("message", "") if isinstance(body, dict) else ""
                    except Exception:
                        detail = resp.text[:500]
                    raise GPTError(f"模型接口请求失败（HTTP {resp.status_code}）" + (f"：{detail}" if detail else ""), resp.status_code)
                data = resp.json()
                choices=data.get("choices") or []
                if not choices or not isinstance(choices[0],dict):
                    raise GPTError("模型接口未返回 choices 结果，请检查接口兼容性",502)
                choice = choices[0]
                message=choice.get("message") or {}
                content=message.get("content")
                if isinstance(content,list):
                    content="\n".join(part.get("text","") for part in content if isinstance(part,dict))
                # Reasoning tokens may use most of the first completion budget and
                # leave no visible JSON. Retry that incomplete response once with
                # a larger output budget; never pass a partial result downstream.
                if choice.get("finish_reason") == "length":
                    if attempt == 0 and retry_limit > first_limit:
                        payload[token_field] = retry_limit
                        continue
                    raise GPTError(
                        f"模型输出连续达到长度上限（已尝试最多 {payload[token_field]} tokens）；请缩短剧本/分析批次，或检查接口的输出上限配置",
                        502,
                    )
                if not isinstance(content,str) or not content.strip():
                    reason=message.get("refusal") or f"模型返回空内容（结束原因：{choice.get('finish_reason','未知')}）"
                    raise GPTError(reason,502)
                return content
    except GPTError:
        raise
    except httpx.ConnectError:
        raise GPTError(f"无法连接到 {base_url}（检查 base_url 或网络）", 502)
    except (httpx.TimeoutException, TimeoutError):
        raise GPTError(f"请求超时（{request_timeout}s），请检查模型响应或网络后重试", 504)
    except Exception as e:
        raise GPTError(f"GPT 调用异常: {type(e).__name__}: {e}", 502)


async def generate_script(
    db: Session, theme: str, style: str = "", episodes: int = 3, seconds_per_ep: int | None = None
) -> str:
    """根据主题生成完整短剧剧本"""
    system = "你是专业短剧编剧，擅长撰写竖屏短剧剧本（含场景、台词、动作、音效提示）。"
    user = (
        f"请为主题「{theme}」撰写一部短剧剧本。\n"
        f"要求：共 {episodes} 集；"
        + (f"每集约 {seconds_per_ep} 秒；" if seconds_per_ep else "每集时长根据剧情内容和节奏自然安排，短剧单集通常约1–3分钟，不要为了凑时长灌水或删减必要剧情；")
        + "每个镜头可拍4–12秒，请规划足够数量的镜头与对白，不要把长对白挤进单个短镜头。\n"
        f"{'风格：' + style if style else ''}\n"
        "格式：先给剧名和一句话梗概，再按集分场，每场标注场景、角色、台词、动作、音效。"
        "直接输出剧本文本，不要解释。"
    )
    return await chat_completion(db, system, user, json_mode=False, max_tokens=4096)
