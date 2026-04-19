import os
import re
from typing import List

import numpy as np
from langchain.docstore.document import Document
from langchain.text_splitter import TextSplitter


class HybridSemanticTextSplitter(TextSplitter):
    """Hybrid splitter: structure-first, semantic breakpoints second, length fallback last."""

    _encoder_cache = {}

    def __init__(
        self,
        fallback_splitter,
        model_path: str,
        similarity_threshold: float = 0.74,
        min_chunk_size: int = 220,
        max_chunk_size: int = 520,
        min_paragraph_chars: int = 80,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.fallback_splitter = fallback_splitter
        self.model_path = model_path
        self.similarity_threshold = similarity_threshold
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.min_paragraph_chars = min_paragraph_chars

    def split_documents(self, documents: List[Document]) -> List[Document]:
        results = []
        for doc in documents:
            chunks = self.split_text(doc.page_content)
            for chunk in chunks:
                metadata = dict(doc.metadata)
                results.append(Document(page_content=chunk, metadata=metadata))
        return results

    def split_text(self, text: str) -> List[str]:
        if not text or not text.strip():
            return []

        paragraphs = self._structure_split(text)
        output_chunks = []
        for paragraph in paragraphs:
            if len(paragraph) <= self.max_chunk_size:
                output_chunks.append(paragraph)
                continue

            semantic_chunks = self._semantic_split(paragraph)
            for item in semantic_chunks:
                if len(item) <= self.max_chunk_size:
                    output_chunks.append(item)
                else:
                    output_chunks.extend(self.fallback_splitter.split_text(item))

        normalized = [self._normalize_whitespace(chunk) for chunk in output_chunks if chunk and chunk.strip()]
        return self._apply_overlap(normalized)

    def _structure_split(self, text: str) -> List[str]:
        parts = [p.strip() for p in re.split(r"\n\s*\n+", text) if p and p.strip()]
        if not parts:
            return [text.strip()]

        merged = []
        buffer = ""
        for part in parts:
            if not buffer:
                buffer = part
                continue

            if len(buffer) < self.min_paragraph_chars:
                buffer = f"{buffer}\n{part}".strip()
            else:
                merged.append(buffer)
                buffer = part

        if buffer:
            merged.append(buffer)
        return merged

    def _semantic_split(self, text: str) -> List[str]:
        sentences = self._sentence_split(text)
        if len(sentences) <= 1:
            return [text]

        embeddings = self._encode(sentences)
        if embeddings is None:
            return self.fallback_splitter.split_text(text)

        chunks = []
        current = [sentences[0]]
        current_len = len(sentences[0])

        for i in range(1, len(sentences)):
            sim = self._cosine_similarity(embeddings[i - 1], embeddings[i])
            sentence = sentences[i]

            should_break = (
                sim < self.similarity_threshold
                and current_len >= self.min_chunk_size
            ) or (current_len + len(sentence) > self.max_chunk_size)

            if should_break:
                chunks.append("".join(current).strip())
                current = [sentence]
                current_len = len(sentence)
            else:
                current.append(sentence)
                current_len += len(sentence)

        if current:
            chunks.append("".join(current).strip())

        return chunks

    @staticmethod
    def _sentence_split(text: str) -> List[str]:
        # Keep punctuation in each sentence for readability and retrieval context.
        sentences = re.findall(r"[^。！？!?；;\n]+[。！？!?；;\n]?", text)
        cleaned = [s.strip() for s in sentences if s and s.strip()]
        return cleaned if cleaned else [text]

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _apply_overlap(self, chunks: List[str]) -> List[str]:
        if not chunks:
            return []

        overlap = max(0, self._chunk_overlap)
        if overlap == 0:
            return chunks

        output = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = output[-1]
            head = prev[-overlap:] if len(prev) > overlap else prev
            merged = f"{head}{chunks[i]}" if head else chunks[i]
            output.append(merged)
        return output

    def _encode(self, sentences: List[str]):
        try:
            encoder = self._get_encoder()
            if encoder is None:
                return None
            vectors = encoder.encode(sentences, normalize_embeddings=True, show_progress_bar=False)
            return vectors
        except Exception:
            return None

    def _get_encoder(self):
        cache_key = self.model_path
        if cache_key in self._encoder_cache:
            return self._encoder_cache[cache_key]

        if not self.model_path:
            self._encoder_cache[cache_key] = None
            return None

        resolved_path = self.model_path
        if not os.path.exists(resolved_path):
            self._encoder_cache[cache_key] = None
            return None

        try:
            from sentence_transformers import SentenceTransformer

            encoder = SentenceTransformer(resolved_path)
            self._encoder_cache[cache_key] = encoder
            return encoder
        except Exception:
            self._encoder_cache[cache_key] = None
            return None

    @staticmethod
    def _cosine_similarity(v1, v2) -> float:
        v1 = np.asarray(v1)
        v2 = np.asarray(v2)
        denom = (np.linalg.norm(v1) * np.linalg.norm(v2))
        if denom == 0:
            return 1.0
        return float(np.dot(v1, v2) / denom)
