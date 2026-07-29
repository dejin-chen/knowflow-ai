import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class FrontendSettings:
    """前端只保存连接后端所需的配置，不保存任何模型密钥。"""

    api_base_url: str = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api")


settings = FrontendSettings()
