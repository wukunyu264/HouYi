import json
import os
import pandas as pd
from kb_manager.faiss_manager import CSVKBManager


def process_poison_to_csv(dataset_name, poison_rag_path):
    """
    读取 PoisonedRAG 的 adv_targeted_results JSON，转换为 HouYi 的 CSV 并入库
    """
    # 1. 定位源 JSON 文件
    json_path = os.path.join(poison_rag_path, "results", "adv_targeted_results", f"{dataset_name}.json")
    if not os.path.exists(json_path):
        print(f"Error: {json_path} 不存在，请先运行 gen_adv.py")
        return False

    with open(json_path, 'r', encoding='utf-8') as f:
        adv_data = json.load(f)

    # 2. 提取 adv_texts 转换为 DataFrame
    rows = []
    for q_id, content in adv_data.items():
        # content 包含 question, incorrect answer, adv_texts 等
        for text in content.get("adv_texts", []):
            rows.append({
                "content": text,
                "source_query_id": q_id,
                "target_incorrect": content.get("incorrect answer")
            })

    df = pd.DataFrame(rows)

    # 3. 保存到 HouYi 的 uploads 目录
    upload_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
    os.makedirs(upload_dir, exist_ok=True)
    csv_filename = f"poisoned_{dataset_name}.csv"
    csv_path = os.path.join(upload_dir, csv_filename)
    df.to_csv(csv_path, index=False)

    # 4. 调用 HouYi 的 faiss_manager 强制执行 ingest.py
    # 我们需要模拟一个能被 faiss_manager 识别的对象
    class MockFile:
        def save(self, path):
            df.to_csv(path, index=False)

    kb_manager = CSVKBManager()
    success = kb_manager.upload_and_ingest(MockFile(), f"poisoned_{dataset_name}")
    return success