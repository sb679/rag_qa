# -*- coding:utf-8 -*-
"""Compare rule vs hybrid chunking on a local corpus.

Usage example:
    python evaluate_chunking_modes.py --data-dir .\data\mining_data

The script reports chunk statistics and a lightweight semantic-coherence proxy.
"""

import argparse
import os
import statistics
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, current_dir)

from core.document_processor import load_documents_from_directory  # noqa: E402
from edu_text_spliter import ChineseRecursiveTextSplitter, HybridSemanticTextSplitter  # noqa: E402
from base import Config  # noqa: E402


@dataclass
class ChunkStats:
    mode: str
    chunk_count: int
    avg_chars: float
    median_chars: float
    p90_chars: float
    max_chars: int
    min_chars: int
    under_120_ratio: float
    coherence: Optional[float]


def _build_rule_chunks(documents, parent_chunk_size: int, child_chunk_size: int, chunk_overlap: int):
    parent_splitter = ChineseRecursiveTextSplitter(chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap)
    child_splitter = ChineseRecursiveTextSplitter(chunk_size=child_chunk_size, chunk_overlap=chunk_overlap)
    chunks = []
    for doc in documents:
        parent_docs = parent_splitter.split_documents([doc])
        for parent_doc in parent_docs:
            chunks.extend(child_splitter.split_documents([parent_doc]))
    return chunks


def _build_hybrid_chunks(documents, parent_chunk_size: int, child_chunk_size: int, chunk_overlap: int, conf: Config):
    parent_splitter = ChineseRecursiveTextSplitter(chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap)
    child_splitter = HybridSemanticTextSplitter(
        fallback_splitter=ChineseRecursiveTextSplitter(chunk_size=child_chunk_size, chunk_overlap=chunk_overlap),
        model_path=conf.SEMANTIC_MODEL_PATH,
        similarity_threshold=conf.SEMANTIC_SIM_THRESHOLD,
        min_chunk_size=conf.SEMANTIC_MIN_CHUNK_SIZE,
        max_chunk_size=conf.SEMANTIC_MAX_CHUNK_SIZE,
        min_paragraph_chars=conf.STRUCT_MIN_PARAGRAPH_CHARS,
        chunk_size=child_chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = []
    for doc in documents:
        parent_docs = parent_splitter.split_documents([doc])
        for parent_doc in parent_docs:
            chunks.extend(child_splitter.split_documents([parent_doc]))
    return chunks


def _length_stats(chunks) -> Dict[str, float]:
    lengths = [len(chunk.page_content) for chunk in chunks]
    if not lengths:
        return {
            "chunk_count": 0,
            "avg_chars": 0.0,
            "median_chars": 0.0,
            "p90_chars": 0.0,
            "max_chars": 0,
            "min_chars": 0,
            "under_120_ratio": 0.0,
        }

    sorted_lengths = sorted(lengths)
    p90_index = min(len(sorted_lengths) - 1, int(len(sorted_lengths) * 0.9))
    return {
        "chunk_count": len(lengths),
        "avg_chars": round(sum(lengths) / len(lengths), 2),
        "median_chars": round(statistics.median(lengths), 2),
        "p90_chars": round(sorted_lengths[p90_index], 2),
        "max_chars": max(lengths),
        "min_chars": min(lengths),
        "under_120_ratio": round(sum(1 for size in lengths if size < 120) / len(lengths), 4),
    }


def _sentence_embeddings(model, texts: List[str]):
    if model is None or not texts:
        return None
    try:
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    except Exception:
        return None


def _coherence_score(chunks, model_path: str) -> Optional[float]:
    if not chunks:
        return None
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        return None

    if not model_path or not os.path.exists(model_path):
        return None

    try:
        model = SentenceTransformer(model_path)
    except Exception:
        return None

    values = []
    for index in range(1, len(chunks)):
        left = chunks[index - 1].page_content.strip()
        right = chunks[index].page_content.strip()
        if not left or not right:
            continue
        vectors = _sentence_embeddings(model, [left, right])
        if vectors is None:
            continue
        sim = float(np.dot(vectors[0], vectors[1]))
        values.append(sim)

    if not values:
        return None
    return round(sum(values) / len(values), 4)


def evaluate_mode(mode: str, documents, conf: Config, parent_chunk_size: int, child_chunk_size: int, chunk_overlap: int) -> ChunkStats:
    if mode == "rule":
        chunks = _build_rule_chunks(documents, parent_chunk_size, child_chunk_size, chunk_overlap)
    elif mode == "hybrid":
        chunks = _build_hybrid_chunks(documents, parent_chunk_size, child_chunk_size, chunk_overlap, conf)
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    stats = _length_stats(chunks)
    coherence = _coherence_score(chunks[:50], conf.SEMANTIC_MODEL_PATH)
    return ChunkStats(mode=mode, coherence=coherence, **stats)


def print_stats(stats: ChunkStats):
    print(f"\n=== {stats.mode.upper()} ===")
    print(f"chunk_count: {stats.chunk_count}")
    print(f"avg_chars: {stats.avg_chars}")
    print(f"median_chars: {stats.median_chars}")
    print(f"p90_chars: {stats.p90_chars}")
    print(f"min_chars: {stats.min_chars}")
    print(f"max_chars: {stats.max_chars}")
    print(f"under_120_ratio: {stats.under_120_ratio}")
    print(f"semantic_coherence_proxy: {stats.coherence if stats.coherence is not None else 'N/A'}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate rule vs hybrid chunking modes")
    parser.add_argument("--data-dir", required=True, help="Corpus directory, e.g. rag_qa/data/mining_data")
    parser.add_argument("--parent-chunk-size", type=int, default=None)
    parser.add_argument("--child-chunk-size", type=int, default=None)
    parser.add_argument("--chunk-overlap", type=int, default=None)
    args = parser.parse_args()

    conf = Config()
    parent_chunk_size = args.parent_chunk_size or conf.PARENT_CHUNK_SIZE
    child_chunk_size = args.child_chunk_size or conf.CHILD_CHUNK_SIZE
    chunk_overlap = args.chunk_overlap or conf.CHUNK_OVERLAP

    documents = load_documents_from_directory(args.data_dir)
    print(f"Loaded documents: {len(documents)}")

    rule_stats = evaluate_mode("rule", documents, conf, parent_chunk_size, child_chunk_size, chunk_overlap)
    hybrid_stats = evaluate_mode("hybrid", documents, conf, parent_chunk_size, child_chunk_size, chunk_overlap)

    print_stats(rule_stats)
    print_stats(hybrid_stats)

    if rule_stats.chunk_count and hybrid_stats.chunk_count:
        diff = {
            "chunk_count_delta": hybrid_stats.chunk_count - rule_stats.chunk_count,
            "avg_chars_delta": round(hybrid_stats.avg_chars - rule_stats.avg_chars, 2),
            "under_120_ratio_delta": round(hybrid_stats.under_120_ratio - rule_stats.under_120_ratio, 4),
        }
        if rule_stats.coherence is not None and hybrid_stats.coherence is not None:
            diff["coherence_delta"] = round(hybrid_stats.coherence - rule_stats.coherence, 4)
        print("\n=== DELTA (hybrid - rule) ===")
        for key, value in diff.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
