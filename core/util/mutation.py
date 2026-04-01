# util/mutation.py
import re
from constant.chromosome import Chromosome
from util.openai_util import completion_with_chatgpt


def llm_mutation_generation(chromosome: Chromosome):
    """
    针对本地模型(Llama3/Qwen)优化的变异逻辑。
    增加了正则表达式匹配，以应对本地模型可能产生的格式不规范问题。
    """
    disruptor_prompt = chromosome.disruptor
    framework_prompt = chromosome.framework
    separator_prompt = chromosome.separator

    # 构建变异提示词：明确要求保留隔离符，这对本地模型至关重要 [cite: 2067, 2087]
    mutation_generation_prompt = f"""Please rephrase the following prompt to maintain its original intent and meaning. 
You MUST output the rephrased content within the exact same tags provided below. 
Do not include any introductory text, only the tags and their new content.

=========Framework Prompt Begin=========
{framework_prompt}
=========Framework Prompt End=========
=========Separator Prompt Begin=========
{separator_prompt}
=========Separator Prompt End=========
=========Disruptor Prompt Begin=========
{disruptor_prompt}
=========Disruptor Prompt End=========

Provide a revised version that captures the essence of the original prompt.
    """

    # 根据 config.json 中的 mode 自动调用模型
    response = completion_with_chatgpt(mutation_generation_prompt)

    # 安全检查：如果模型完全没有返回，直接保留原始染色体
    if not response:
        print("[MUTATION WARNING] LLM returned empty response. Keeping original chromosome.")
        return chromosome

    try:
        # 使用正则表达式进行“鲁棒性抽取”
        # 本地模型有时会在隔离符前后加空格或星号，正则可以过滤这些干扰
        def extract_content(tag_name, text):
            pattern = rf"========={tag_name} Begin=========(.*?)========={tag_name} End========="
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            return match.group(1).strip() if match else None

        new_framework = extract_content("Framework Prompt", response)
        new_separator = extract_content("Separator Prompt", response)
        new_disruptor = extract_content("Disruptor Prompt", response)

        # 检查是否三部分都成功提取
        if new_framework and new_separator and new_disruptor:
            chromosome.framework = new_framework
            chromosome.separator = new_separator
            chromosome.disruptor = new_disruptor
            print(f"[MUTATION SUCCESS] Chromosome mutated successfully.")
        else:
            # 如果提取失败（比如模型漏掉了某个标签），尝试使用原来的 split 逻辑作为备选
            print("[MUTATION INFO] Regex failed, attempting fallback split logic...")
            chromosome.framework = response.split("=========Framework Prompt End=========")[0].split(
                "=========Framework Prompt Begin=========")[1].strip()
            chromosome.separator = response.split("=========Separator Prompt End=========")[0].split(
                "=========Separator Prompt Begin=========")[1].strip()
            chromosome.disruptor = response.split("=========Disruptor Prompt End=========")[0].split(
                "=========Disruptor Prompt Begin=========")[1].strip()

    except (IndexError, ValueError, AttributeError) as e:
        # 最后的防线：如果所有解析都失败，不中断程序，保持上一代染色体
        print(f"[MUTATION ERROR] Parsing failed for response. Fallback to original. Reason: {e}")
        return chromosome

    return chromosome