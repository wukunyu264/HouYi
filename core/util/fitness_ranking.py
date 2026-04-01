import loguru
from constant.chromosome import Chromosome
from util.unified_evaluator import evaluator  # 引入我们的大脑

logger = loguru.logger


def llm_fitness_ranking(chromosome: Chromosome) -> int:
    """
    将旧的冗长逻辑替换为调用 unified_evaluator，
    既保持了遗传算法所需的 1-10 分梯度，又能输出统一指标日志！
    """
    record = {
        "attack_method": "HOUYI",
        "question": chromosome.question_prompt,
        "target_goal": chromosome.question_prompt,  # HouYi 的目标通常在问题中描述
        "llm_response": chromosome.llm_response,
        "injected_adv_docs": [],  # 指令劫持通常没有注入外部向量库，传空
        "top_k": 0,
        "adv_per_query": 0
    }

    # 调用统一大脑
    eval_result = evaluator.evaluate(record)

    final_score = eval_result["Raw_Score"]
    asr_status = eval_result["ASR"]

    # 打印极简清爽战报
    logger.info(f"--- 靶机评估 ---")
    logger.info(f"Payload: {record['question']}")
    logger.info(f"Response[:100]: {str(record['llm_response'])[:100]}...")
    logger.info(f"打分: {final_score}/10 (统一定义 ASR={'成功' if asr_status == 1 else '失败'})")
    logger.info(f"----------------")

    return final_score