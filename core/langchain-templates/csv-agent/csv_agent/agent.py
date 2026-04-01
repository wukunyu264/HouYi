import os
import json
import loguru
import pandas as pd
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent
from langchain_openai import ChatOpenAI

logger = loguru.logger

import requests
# 禁用 SSL 警告
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 强制全局不校验 SSL
os.environ['CURL_CA_BUNDLE'] = ''

# 1. 路径精确定位
current_file_path = os.path.abspath(__file__)
# 向上找 4 层定位到 houyi/core 目录
core_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file_path))))
config_path = os.path.join(core_dir, "config.json")

# 准确定位到 HouYi/uploads 目录
uploads_dir = os.path.abspath(os.path.join(os.path.dirname(core_dir), "uploads"))
# 数据集存放基础目录
data_dir = os.path.dirname(os.path.dirname(current_file_path))


def get_agent_executor():
    """
    核心工厂函数：根据当前环境变量动态创建适配的 Agent 实例。
    优化点：增加强力的格式纠正指令，解决大模型应对注入攻击时的水土不服。
    """
    # 2. 读取基础配置
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Agent 加载配置失败: {e}")
        config = {}

    # 3. 智能模型路由
    selected_model = os.environ.get("HOUYI_MODEL", config.get("ollama_model", "llama3:8b"))

    if "gpt" in selected_model.lower():
        api_key = config.get("openai_key")
        api_base = config.get("openai_base_url")
        logger.info(f">>> [Agent] 激活远程靶机引擎: {selected_model}")
    else:
        api_key = "ollama"
        api_base = config.get("ollama_base_url", "http://localhost:11434/v1")
        logger.info(f">>> [Agent] 激活本地驱动引擎: {selected_model}")

    # 4. 强制使用 temperature=0 追求确定性
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=api_base,
        model=selected_model,
        temperature=0
    )

    # 5. 动态加载数据集路径优化
    dataset_name = os.environ.get("HOUYI_DATASET", "nq")

    possible_paths = [
        os.path.join(uploads_dir, f"poisoned_{dataset_name}.csv"),
        os.path.join(uploads_dir, f"{dataset_name}.csv"),
        os.path.join(data_dir, f"{dataset_name}.csv")
    ]

    csv_path = None
    for path in possible_paths:
        if os.path.exists(path):
            csv_path = path
            break

    if not csv_path:
        logger.warning(f"无法在 uploads 或 data 目录找到 {dataset_name} 相关文件，回退至默认 titanic.csv")
        csv_path = os.path.join(data_dir, "titanic.csv")

    try:
        df = pd.read_csv(csv_path)
        logger.info(f">>> [Agent] 成功挂载数据集上下文: {os.path.abspath(csv_path)}")
    except Exception as e:
        logger.error(f"读取 CSV 失败: {e}")
        df = pd.DataFrame()

    # 6. 创建具备审计能力的 Agent
    try:
        # 🚀 核心修改：将 handle_parsing_errors 改为具体的纠正提示词
        error_handling_prompt = (
            "Check your output and make sure it strictly follows the Thought/Action/Action Input format. "
            "If you have finished or want to talk to the user directly, you MUST use the format: "
            "Final Answer: [your response here]"
        )

        executor = create_pandas_dataframe_agent(
            llm=llm,
            df=df,
            verbose=True,
            agent_type="zero-shot-react-description",
            allow_dangerous_code=True,
            include_df_in_prompt=True,
            max_iterations=10,
            return_intermediate_steps=True,
            handle_parsing_errors=error_handling_prompt  # 🚀 传入强力纠正指令
        )
        return executor
    except Exception as e:
        logger.error(f"创建 Agent 失败: {e}")
        return None


# 为了兼容旧版代码
agent_executor = get_agent_executor()