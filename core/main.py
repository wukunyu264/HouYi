import json
import os
import sys
import loguru
import openai
from datetime import datetime

# --- 核心路径修复 ---
current_file = os.path.abspath(__file__)
core_dir = os.path.dirname(current_file)
root_dir = os.path.dirname(core_dir)

for p in [root_dir, core_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from constant.chromosome import Chromosome
from iterative_prompt_optimization import IterativePromptOptimizer

# ====== 1. 导入所有的攻击意图 (Intentions) ======
from intention.base_intention import Intention
from intention.prompt_leakage import PromptLeakage
from intention.spam_generation import SpamGeneration
from intention.content_manipulation import ContentManipulation
from intention.information_gathering import InformationGathering
from intention.write_code import WriteCode
from intention.stealthy_leak import StealthyLeakIntention

# ====== 2. 导入所有的靶机 (Harnesses) ======
from harness.base_harness import Harness
from harness.csv_agent_harness import CSVAgentHarness
from harness.demo_translator_harness import TranslatorHarness

logger = loguru.logger

# =====================================================================
# 🌟 核心映射字典：将前端传来的字符串对应到具体的 Python 类
# =====================================================================
INTENTION_MAP = {
    "PromptLeakage": PromptLeakage,
    "SpamGeneration": SpamGeneration,
    "ContentManipulation": ContentManipulation,
    "InformationGathering": InformationGathering,
    "WriteCode": WriteCode,
    "StealthyLeak": StealthyLeakIntention
}

TARGET_MAP = {
    "csv_agent": CSVAgentHarness,
    "mock": TranslatorHarness  # 模拟靶机：翻译器
}

# 读取配置与初始化大模型
config_file_path = os.path.join(core_dir, "config.json")
try:
    with open(config_file_path, 'r', encoding="utf-8") as f:
        config = json.load(f)
except FileNotFoundError:
    logger.error(f"找不到配置文件: {config_file_path}")
    sys.exit(1)

mode = config.get("mode", "ollama")
if mode == "openai":
    os.environ["OPENAI_API_KEY"] = config.get("openai_key")
    os.environ["OPENAI_BASE_URL"] = config.get("openai_base_url")
    openai.api_key = os.environ["OPENAI_API_KEY"]
    openai.api_base = os.environ["OPENAI_BASE_URL"]
else:
    os.environ["OPENAI_API_KEY"] = config.get("openai_key", "sk-xxx")
    os.environ["OPENAI_BASE_URL"] = config.get("ollama_base_url")
    openai.api_key = os.environ["OPENAI_API_KEY"]
    openai.api_base = os.environ["OPENAI_BASE_URL"]


def inject(
        intention: Intention,
        application_harness: Harness,
        iterations: int = 5,
        population: int = 3,
        progress_callback=None
) -> Chromosome:
    """通用的注入执行函数，支持传入参数和前端回调"""
    optimizer = IterativePromptOptimizer(
        intention=intention,
        application_harness=application_harness,
        iteration=iterations,
        crossover=0.2,
        mutation=0.5,
        population=population,
        progress_callback=progress_callback  # 将进度回调传给优化器
    )
    optimizer.optimize()
    return optimizer.best_chromosome


def cli_main():
    """这是为了让你在终端直接跑 python main.py 留下的本地测试入口"""
    logger.info(f"--- 开始 HouYi 攻击 本地CLI测试 (模式: {mode}) ---")

    # 在终端测试时，你可以手动修改这俩字符串
    test_intention = "SpamGeneration"
    test_target = "mock"

    # 从映射字典中动态实例化
    intention_obj = INTENTION_MAP[test_intention]()
    harness_obj = TARGET_MAP[test_target]()

    chromosome = inject(intention_obj, harness_obj, iterations=5, population=3)

    if chromosome is None:
        logger.error("注入失败，请检查日志")
        return

    payload = f"{chromosome.framework}{chromosome.separator}{chromosome.disruptor}"
    logger.info(f"✨ 攻击完成！最终得分: {chromosome.fitness_score}")
    logger.info(f"最佳 Payload:\n{payload}")


if __name__ == "__main__":
    cli_main()