import re


class RetrievalTokenizer:
    """为中文 BM25 和词法降级提供一致、可重复的轻量分词。"""

    token_pattern = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)

    @classmethod
    def tokenize(cls, text: str) -> list[str]:
        # 英文和数字保留完整词元；连续中文使用双字片段，避免引入大型分词模型。
        normalized_text = text.casefold().replace(",", "")
        features: list[str] = []
        for token in cls.token_pattern.findall(normalized_text):
            if cls._is_chinese(token[0]):
                if len(token) == 1:
                    features.append(token)
                else:
                    features.extend(
                        token[index : index + 2]
                        for index in range(len(token) - 1)
                    )
            else:
                features.append(token)
        return features

    @staticmethod
    def _is_chinese(character: str) -> bool:
        return "\u4e00" <= character <= "\u9fff"
