"""测试各环节 API 连通性（GET /models 探测）"""
import httpx
from sqlalchemy.orm import Session
from services.settings_service import get_stage_config


async def test_stage(db: Session, stage: str) -> dict:
    """
    返回: {"ok": bool, "message": str, "stage": str}
    """
    cfg = get_stage_config(db, stage)
    if not cfg:
        return {"ok": False, "stage": stage, "message": "该环节未配置"}

    api_key = cfg.get("api_key", "")
    if not api_key:
        return {"ok": False, "stage": stage, "message": "未填写 API Key"}

    base_url = cfg.get("base_url", "").rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}

    # 尝试 GET {base_url}/models 探测
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{base_url}/models", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                model_list = [m.get("id", "") for m in data.get("data", [])]
                # 检查当前配置的 model 是否在列表中
                cur_model = cfg.get("model", "")
                if cur_model and cur_model in model_list:
                    return {"ok": True, "stage": stage,
                            "message": f"连接成功！模型 {cur_model} 可用",
                            "models_available": model_list[:10]}
                elif model_list:
                    return {"ok": False, "stage": stage,
                            "message": f"连接成功，但当前模型 {cur_model} 未在列表中。可选: {', '.join(model_list[:5])}",
                            "models_available": model_list[:10]}
                else:
                    return {"ok": False, "stage": stage,
                            "message": "连接成功（模型列表为空，请确认配置）"}
            elif resp.status_code == 401:
                return {"ok": False, "stage": stage, "message": "API Key 无效（401 Unauthorized）"}
            elif resp.status_code == 403:
                return {"ok": False, "stage": stage, "message": "无权限（403 Forbidden）"}
            else:
                return {"ok": False, "stage": stage,
                        "message": f"模型列表请求失败（HTTP {resp.status_code}）"}
    except httpx.ConnectError:
        return {"ok": False, "stage": stage, "message": f"无法连接到 {base_url}（网络/地址错误）"}
    except httpx.TimeoutException:
        return {"ok": False, "stage": stage, "message": f"连接超时（{base_url} 15s 无响应）"}
    except Exception as e:
        return {"ok": False, "stage": stage, "message": f"请求异常: {type(e).__name__}: {e}"}
