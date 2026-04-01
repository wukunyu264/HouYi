import os
import subprocess
import loguru

logger = loguru.logger


class CSVKBManager:
    def __init__(self, template_path=None):
        # 自动定位到根目录下的 core/langchain-templates/csv-agent
        if template_path is None:
            # 假设该文件在 HouYi_Web/kb_manager/ 下
            current_dir = os.path.dirname(os.path.abspath(__file__))
            root_dir = os.path.dirname(current_dir)
            self.template_path = os.path.join(root_dir, "core", "langchain-templates", "csv-agent")
        else:
            self.template_path = template_path

        self.upload_dir = os.path.join(os.path.dirname(self.template_path), "..", "..", "uploads")
        os.makedirs(self.upload_dir, exist_ok=True)

    def upload_and_ingest(self, file_obj, kb_name):
        file_path = os.path.join(self.upload_dir, f"{kb_name}.csv")
        file_obj.save(file_path)

        logger.info(f"执行向量化，模板路径: {self.template_path}")
        try:
            # 确保 ingest.py 在 core/langchain-templates/csv-agent 下
            result = subprocess.run(
                ["python", "ingest.py"],
                cwd=self.template_path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                logger.info("向量化处理完成")
                return True
            else:
                logger.error(f"Ingest 失败: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"执行异常: {e}")
            return False