import sys
import os
import asyncio
import json
import threading
import subprocess
import contextlib
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel
import requests
# 禁用 SSL 警告
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 强制全局不校验 SSL
os.environ['CURL_CA_BUNDLE'] = ''

# --- 路径定位 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
POISON_RAG_DIR = os.path.abspath(os.path.join(root_dir, "..", "PoisonedRAG"))

# --- 结果保存目录 ---
# HouYi 结果保存目录
HOUYI_RESULTS_DIR = os.path.join(current_dir, "results_houyi")
os.makedirs(HOUYI_RESULTS_DIR, exist_ok=True)

# Poison 结果保存目录
POISON_HISTORY_DIR = os.path.join(current_dir, "results_poison")
os.makedirs(POISON_HISTORY_DIR, exist_ok=True)

for path in [root_dir, current_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

from intention.prompt_leakage import PromptLeakage
from harness.csv_agent_harness import CSVAgentHarness
from main import INTENTION_MAP, TARGET_MAP, inject
from json_to_csv_ingest import process_poison_to_csv

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

event_queue = asyncio.Queue()
poison_log_queue = asyncio.Queue()


# ==========================================
# 模块 A: HouYi 指令层攻击接口 (带详细过程拦截)
# ==========================================
@app.get("/api/attack/stream")
async def stream_attack(
        intention_name: str = "PromptLeakage",
        iterations: int = 5,
        population: int = 3,
        target: str = "csv_agent",
        model_name: str = "llama3:8b",
        dataset: str = "nq"
):
    # 注入全局环境变量
    os.environ["HOUYI_MODEL"] = model_name
    os.environ["HOUYI_DATASET"] = dataset

    while not event_queue.empty():
        await event_queue.get()

    loop = asyncio.get_running_loop()

    # 初始化报告数据结构
    run_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": model_name,
        "dataset": dataset,
        "target": target,
        "intention": intention_name,
        "iterations_log": [],
        "raw_interaction": []  # 记录所有的问答对
    }

    # 拦截 Loguru 日志：解决“信息不对称”
    def sse_log_sink(message):
        msg_text = message.record["message"]
        if any(k in msg_text for k in ["正在执行注入攻击", "Agent 最终响应", "打分完成", "判定"]):
            data = {"type": "info", "content": msg_text}
            run_data["raw_interaction"].append(msg_text)
            asyncio.run_coroutine_threadsafe(event_queue.put(data), loop)

    sink_id = logger.add(sse_log_sink, level="INFO", format="{message}")

    def progress_callback(iteration, best_score, best_payload, llm_response):
        step_data = {
            "iteration": iteration,
            "score": best_score,
            "payload": best_payload,
            "response": str(llm_response)
        }
        run_data["iterations_log"].append(step_data)
        asyncio.run_coroutine_threadsafe(event_queue.put({"type": "progress", **step_data}), loop)

    def run_houyi():
        try:
            intention_obj = INTENTION_MAP.get(intention_name)()
            harness_obj = TARGET_MAP.get(target)()

            inject(
                intention=intention_obj, application_harness=harness_obj,
                iterations=iterations, population=population,
                progress_callback=progress_callback, dataset=dataset
            )

            file_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"houyi_{file_time}_{dataset}.json"
            filepath = os.path.join(HOUYI_RESULTS_DIR, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(run_data, f, ensure_ascii=False, indent=2)

            asyncio.run_coroutine_threadsafe(event_queue.put({"type": "done", "filename": filename}), loop)
        except Exception as e:
            asyncio.run_coroutine_threadsafe(event_queue.put({"type": "error", "message": str(e)}), loop)
        finally:
            logger.remove(sink_id)

    threading.Thread(target=run_houyi).start()

    async def event_generator():
        while True:
            data = await event_queue.get()
            yield f"data: {json.dumps(data)}\n\n"
            if data.get("type") in ["done", "error"]: break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/houyi/history")
async def get_houyi_history():
    files_list = []
    if os.path.exists(HOUYI_RESULTS_DIR):
        for f in os.listdir(HOUYI_RESULTS_DIR):
            if f.endswith('.json'):
                try:
                    with open(os.path.join(HOUYI_RESULTS_DIR, f), 'r', encoding='utf-8') as file:
                        d = json.load(file)
                        files_list.append({
                            "filename": f, "timestamp": d.get("timestamp"),
                            "model": d.get("model"), "dataset": d.get("dataset"),
                            "intention": d.get("intention")
                        })
                except:
                    pass
    files_list.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"status": "success", "data": files_list}


@app.get("/api/houyi/results")
async def get_houyi_results(filename: str):
    path = os.path.join(HOUYI_RESULTS_DIR, filename)
    if not os.path.exists(path): return JSONResponse(status_code=404, content={"message": "Not Found"})
    with open(path, "r", encoding="utf-8") as f:
        return {"status": "success", "data": json.load(f)}


# ==========================================
# 模块 B: PoisonedRAG 任务接口
# ==========================================
@app.post("/api/poison/start")
async def start_poison_attack(config: dict):
    dataset = config.get("dataset", "nq")
    model_name = config.get("model_name", "gpt4")
    mode = config.get("mode", "mock")
    python_path = sys.executable

    config_file_path = os.path.join(current_dir, "config.json")
    try:
        with open(config_file_path, 'r', encoding="utf-8") as f:
            sys_config = json.load(f)
    except Exception as e:
        logger.error(f"加载系统配置失败: {e}")
        sys_config = {}

    env = os.environ.copy()
    env["OPENAI_API_KEY"] = sys_config.get("openai_key", "")
    env["OPENAI_BASE_URL"] = sys_config.get("openai_base_url", "https://api.openai.com/v1")

    if mode == "mock":
        cmd = [python_path, "main.py", "--eval_dataset", dataset, "--model_name", model_name, "--name",
               f"{dataset}_web_run"]
    else:
        cmd = [python_path, "gen_adv.py", "--eval_dataset", dataset, "--model_name", model_name]

    loop = asyncio.get_running_loop()

    def run_and_capture():
        try:
            process = subprocess.Popen(
                cmd,
                cwd=POISON_RAG_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )

            for line in iter(process.stdout.readline, ""):
                if line:
                    asyncio.run_coroutine_threadsafe(poison_log_queue.put({"type": "log", "content": line.strip()}),
                                                     loop)

            process.stdout.close()
            return_code = process.wait()

            if return_code != 0:
                asyncio.run_coroutine_threadsafe(poison_log_queue.put({"type": "error",
                                                                       "content": f">>> [ERROR] 内核执行失败 (Exit Code: {return_code})，请检查 API Key 和网络连接。"}),
                                                 loop)
                return

            if mode == "mock":
                res_path = os.path.join(POISON_RAG_DIR, "results", "query_results", "main", f"{dataset}_web_run.json")
                if os.path.exists(res_path):
                    with open(res_path, 'r', encoding='utf-8') as f:
                        raw_data = json.load(f)

                    snapshot = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "model": model_name,
                        "dataset": dataset,
                        "data": raw_data
                    }

                    file_time = datetime.now().strftime("%Y%m%d_%H%M%S")
                    history_filename = f"poison_{file_time}_{dataset}.json"
                    with open(os.path.join(POISON_HISTORY_DIR, history_filename), 'w', encoding='utf-8') as f:
                        json.dump(snapshot, f, ensure_ascii=False, indent=2)

            if mode == "real":
                process_poison_to_csv(dataset, POISON_RAG_DIR)
                asyncio.run_coroutine_threadsafe(
                    poison_log_queue.put({"type": "log", "content": ">>> [SYSTEM] 数据集已更新并注入向量库..."}), loop)

            asyncio.run_coroutine_threadsafe(poison_log_queue.put({"type": "done"}), loop)

        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                poison_log_queue.put({"type": "error", "content": f">>> [CRITICAL] 运行时异常: {str(e)}"}), loop)

    threading.Thread(target=run_and_capture).start()
    return {"status": "success", "message": "投毒内核启动..."}


@app.get("/api/poison/stream")
async def stream_poison_logs():
    async def log_generator():
        while True:
            data = await poison_log_queue.get()
            yield f"data: {json.dumps(data)}\n\n"
            if data.get("type") in ["done", "error"]: break

    return StreamingResponse(log_generator(), media_type="text/event-stream")


@app.get("/api/poison/history")
async def get_poison_history():
    files_list = []
    if os.path.exists(POISON_HISTORY_DIR):
        for f in os.listdir(POISON_HISTORY_DIR):
            if f.endswith('.json'):
                try:
                    with open(os.path.join(POISON_HISTORY_DIR, f), 'r', encoding='utf-8') as file:
                        d = json.load(file)
                        files_list.append({
                            "filename": f,
                            "timestamp": d.get("timestamp"),
                            "model": d.get("model"),
                            "dataset": d.get("dataset")
                        })
                except:
                    pass
    files_list.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"status": "success", "data": files_list}


# ==========================================
# 模块 C: 实战交互与验证 (Chat)
# ==========================================
class ChatRequest(BaseModel):
    user_input: str
    dataset: str
    model_name: str
    target: str = "csv_agent"


@app.post("/api/chat")
async def chat_with_rag(request: ChatRequest):
    os.environ["HOUYI_MODEL"] = request.model_name
    os.environ["HOUYI_DATASET"] = request.dataset

    try:
        harness_obj = TARGET_MAP.get(request.target)()
        llm_response = harness_obj.generate(request.user_input)
        return {"status": "success", "response": str(llm_response)}
    except Exception as e:
        logger.error(f"Chat API 异常: {str(e)}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.get("/api/poison/history/results")
async def get_poison_history_results(filename: str):
    path = os.path.join(POISON_HISTORY_DIR, filename)
    if not os.path.exists(path): return JSONResponse(status_code=404, content={"message": "Not Found"})
    with open(path, "r", encoding="utf-8") as f:
        return {"status": "success", "data": json.load(f)}


@app.get("/api/poison/results")
async def get_poison_results(dataset: str = "nq"):
    res_path = os.path.join(POISON_RAG_DIR, "results", "query_results", "main", f"{dataset}_web_run.json")
    if not os.path.exists(res_path): return JSONResponse(status_code=404, content={"message": "结果文件未找到"})
    with open(res_path, "r", encoding="utf-8") as f:
        return {"status": "success", "data": json.load(f)}


# =====================================================================
# 模块 D: DRA 大模型越狱攻击系统 (新增)
# =====================================================================

DRA_PATH = os.path.abspath(os.path.join(root_dir, "..", "DRA", "src", "attack"))
if DRA_PATH not in sys.path:
    sys.path.insert(0, DRA_PATH)


# 🚀 终极防坑补丁：强力清扫所有错误生成的 0字节 JSON 文件
def fix_empty_json_files(*directories):
    for d in directories:
        cache_dir = os.path.join(d, "cache")
        if os.path.exists(cache_dir):
            for fname in os.listdir(cache_dir):
                if fname.endswith('.json'):
                    fpath = os.path.join(cache_dir, fname)
                    # 只要是0字节文件，统统写入安全的空字典
                    if os.path.getsize(fpath) == 0:
                        with open(fpath, 'w', encoding='utf-8') as f:
                            f.write("{}")


# 扫描并修复 HouYi 目录和 DRA 目录下的异常缓存
fix_empty_json_files(current_dir, DRA_PATH)

try:
    from attack import generation, chat_with_ollama, jailbreak_check, process_reasoning_response
except ImportError as e:
    logger.error(f"⚠️ [DRA模块加载警告] 导入 DRA 模块失败，请检查路径: {e}")


class DraRequest(BaseModel):
    query: str
    model: str = "ollama-deepseek-r1:latest"


class DraChatRequest(BaseModel):
    prompt: str
    model: str = "ollama-deepseek-r1:latest"


# 🚀 上下文管理器：瞬间空间瞬移，确保 DRA 原本的相对路径不出错
@contextlib.contextmanager
def run_in_dra_env():
    old_cwd = os.getcwd()
    os.chdir(DRA_PATH)  # 瞬间切到 DRA 目录
    try:
        yield
    finally:
        os.chdir(old_cwd)  # 执行完立刻切回 HouYi 目录


@app.get("/api/dra/behaviors")
async def get_dra_behaviors():
    file_path = os.path.abspath(os.path.join(root_dir, "..", "DRA", "data", "behaviors.json"))
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            behaviors = json.load(f)
        return {"code": 200, "data": behaviors}
    except Exception as e:
        return {"code": 500, "msg": str(e)}


@app.post("/api/dra/debug")
async def dra_debug(req: DraRequest):
    try:
        attack_kwargs = {"toxic_trunc": 0.5, "benign_trunc": 0.5}
        with run_in_dra_env():  # 🚀 挂载空间瞬移！彻底解决相对路径报错
            prompt = generation(req.query, model=req.model, verbose=False, **attack_kwargs)
        return {"code": 200, "prompt": prompt}
    except Exception as e:
        return {"code": 500, "msg": str(e)}


@app.post("/api/dra/attack")
async def dra_attack(req: DraRequest):
    try:
        attack_kwargs = {"toxic_trunc": 0.5, "benign_trunc": 0.5}
        with run_in_dra_env():  # 🚀 挂载空间瞬移
            prompt = generation(req.query, req.model, verbose=False, **attack_kwargs)
            local_model_name = req.model.replace('ollama-', '')
            raw_response = chat_with_ollama(prompt, model_name=local_model_name)
            clean_res = process_reasoning_response(raw_response)
            is_jb, _, em = jailbreak_check(req.query, clean_res, 0.7)

        return {
            "code": 200,
            "prompt": prompt,
            "response": clean_res,
            "is_jailbroken": is_jb,
            "em_score": em
        }
    except Exception as e:
        return {"code": 500, "msg": str(e)}


@app.post("/api/dra/chat")
async def dra_chat(req: DraChatRequest):
    try:
        local_model_name = req.model.replace('ollama-', '')
        with run_in_dra_env():  # 🚀 挂载空间瞬移
            raw_response = chat_with_ollama(req.prompt, model_name=local_model_name)
            clean_res = process_reasoning_response(raw_response)
        return {"code": 200, "response": clean_res}
    except Exception as e:
        return {"code": 500, "msg": str(e)}


# =====================================================================
# 新增：DRA 越狱沙箱的流式输出接口 (Server-Sent Events)
# =====================================================================
@app.post("/api/dra/chat_stream")
async def dra_chat_stream(req: DraChatRequest):
    local_model_name = req.model.replace('ollama-', '')

    async def event_generator():
        try:
            url = "http://localhost:11434/api/chat"
            payload = {
                "model": local_model_name,
                "messages": [{"role": "user", "content": req.prompt}],
                "stream": True,  # 开启流式输出
                "options": {
                    "temperature": 0.0,
                    "num_predict": 8192  # 允许最大长度输出
                }
            }
            # 使用 contextlib 中的 run_in_dra_env 挂载相对路径
            with run_in_dra_env():
                with requests.post(url, json=payload, stream=True) as r:
                    for line in r.iter_lines():
                        if line:
                            data = json.loads(line)
                            if "message" in data and "content" in data["message"]:
                                chunk = data["message"]["content"]
                                # 组装成前端需要的 SSE 格式： "data: {JSON}\n\n"
                                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
        except Exception as e:
            # 返回错误信息到流中
            yield f"data: {json.dumps({'text': f'<br/><br/>[Backend Stream Error]: {str(e)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
