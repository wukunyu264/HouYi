import json
import os
import pathlib
from openai import OpenAI

# 1. 读取配置
config_file_path = pathlib.Path(__file__).parent.parent / "config.json"
try:
    with open(config_file_path, "r", encoding="utf-8") as f:
        config = json.load(f)
except Exception:
    config = {}

def get_client_and_model(requested_model: str = None):
    """智能路由：根据模型名称自动切换请求地址"""
    # 优先使用函数传入的模型，其次找环境变量，最后默认 gpt-3.5-turbo
    model = requested_model or os.environ.get("HOUYI_MODEL", "gpt-3.5-turbo")

    # 如果模型名字里包含 llama 或 qwen，自动切换到本地 Ollama
    # 修改为：
    if "llama" in model.lower() or "qwen" in model.lower() or "deepseek" in model.lower() or "r1" in model.lower():
        client = OpenAI(
            api_key="ollama",
            base_url=config.get("ollama_base_url", "http://localhost:11434/v1")
        )
    else:
        # 否则走 OpenAI 或你的 ChatAnywhere 代理
        client = OpenAI(
            api_key=config.get("openai_key", "sk-xxx"),
            base_url=config.get("openai_base_url", "https://api.chatanywhere.tech/v1")
        )
    return client, model

def completion_with_chatgpt(text: str, model: str = None) -> str:
    """ HouYi 核心调用：支持自动路由和本地模型名称转换 """
    client, current_model = get_client_and_model(model)

    try:
        response = client.chat.completions.create(
            model=current_model,
            messages=[{"role": "user", "content": text}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[LLM ERROR] 呼叫大模型 {current_model} 失败: {e}")
        return ""