import os
import json
from langchain_community.document_loaders import CSVLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

current_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(current_dir, "..", "..", "config.json")

# 1. 读取 config.json 配置
try:
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
except Exception as e:
    print(f"加载 config.json 失败，请检查文件: {e}")
    exit(1)

api_key = config.get("openai_key")
api_base = config.get("openai_base_url", "https://api.openai.com/v1").rstrip("/")

# 2. 读取 CSV 数据
csv_path = os.path.join(current_dir, "titanic.csv")
if not os.path.exists(csv_path):
    print(f"错误：找不到文件 {csv_path}")
    exit(1)

print(f"找到真实的 CSV 文件: {csv_path}，准备加载数据...")
loader = CSVLoader(csv_path)
docs = loader.load()
print(f"共加载了 {len(docs)} 条数据。")

# 3. 向量化 (核心修改：使用现代写法替代废弃的 VectorstoreIndexCreator)
print("正在调用 Embedding 接口进行向量化建库 (这可能需要十几秒钟)...")
# 显式传入你的 ChatAnywhere API 地址和 Key
embeddings = OpenAIEmbeddings(
    openai_api_key=api_key,
    openai_api_base=api_base
)
# 直接将文档和 Embedding 模型喂给 FAISS
vectorstore = FAISS.from_documents(docs, embeddings)

# 4. 保存到本地
save_path = os.path.join(current_dir, "titanic_data")
vectorstore.save_local(save_path)

print(f"🎉 数据注入成功！FAISS 向量库已保存至: {save_path}")
print("现在你可以返回 core 目录，运行 python main.py 启动攻击测试了！")