from typing import Any

import requests


class ApiClientError(Exception):
    """后端返回错误或网络连接失败时抛出的前端统一异常。"""


class BackendApiClient:
    """Streamlit 与 FastAPI 之间的唯一通信入口。"""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def list_knowledge_bases(self) -> list[dict[str, Any]]:
        return self._request("GET", "/knowledge-bases")

    def create_knowledge_base(
        self,
        name: str,
        description: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/knowledge-bases",
            json={"name": name, "description": description or None},
        )

    def delete_knowledge_base(self, knowledge_base_id: int) -> None:
        self._request("DELETE", f"/knowledge-bases/{knowledge_base_id}")

    def list_documents(self, knowledge_base_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/knowledge-bases/{knowledge_base_id}/documents")

    def upload_document(self, knowledge_base_id: int, uploaded_file) -> dict[str, Any]:
        files = {
            "file": (
                uploaded_file.name,
                uploaded_file.getvalue(),
                uploaded_file.type or "application/octet-stream",
            )
        }
        return self._request(
            "POST",
            f"/knowledge-bases/{knowledge_base_id}/documents",
            files=files,
        )

    def process_document_chunks(self, document_id: int) -> dict[str, Any]:
        return self._request("POST", f"/documents/{document_id}/chunks")

    def index_document(self, document_id: int) -> dict[str, Any]:
        return self._request("POST", f"/documents/{document_id}/index")

    def generate_document_summary(self, document_id: int) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/documents/{document_id}/summary",
            timeout=120,
        )

    def generate_document_faqs(self, document_id: int) -> list[dict[str, Any]]:
        return self._request(
            "POST",
            f"/documents/{document_id}/faqs",
            timeout=120,
        )

    def chat(
        self,
        knowledge_base_id: int,
        question: str,
        conversation_id: int | None,
        top_k: int = 3,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/knowledge-bases/{knowledge_base_id}/chat",
            json={
                "question": question,
                "conversation_id": conversation_id,
                "top_k": top_k,
            },
            timeout=120,
        )

    def list_conversations(self, knowledge_base_id: int) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            f"/knowledge-bases/{knowledge_base_id}/conversations",
        )

    def list_conversation_messages(self, conversation_id: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/conversations/{conversation_id}/messages")

    def submit_answer_feedback(
        self,
        assistant_message_id: int,
        feedback_type: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/messages/{assistant_message_id}/feedback",
            json={"feedback_type": feedback_type},
        )

    def _request(
        self,
        method: str,
        path: str,
        timeout: int = 20,
        **kwargs: Any,
    ) -> Any:
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                timeout=timeout,
                **kwargs,
            )
        except requests.RequestException as error:
            raise ApiClientError("后端服务不可用，请确认 FastAPI 已启动。") from error

        if not response.ok:
            detail = self._get_error_detail(response)
            raise ApiClientError(detail)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    @staticmethod
    def _get_error_detail(response: requests.Response) -> str:
        try:
            payload = response.json()
            return str(payload.get("detail", "后端请求失败"))
        except ValueError:
            return "后端请求失败"
