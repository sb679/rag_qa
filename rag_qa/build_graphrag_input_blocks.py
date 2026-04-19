# -*- coding:utf-8 -*-
"""Export GraphRAG entity-extraction input blocks as JSONL."""

import argparse
import json
import os
import sys
from typing import List

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, current_dir)

from base import Config  # noqa: E402
from core.document_processor import process_graph_documents  # noqa: E402


def _collect_sources(root_dir: str, valid_sources: List[str]):
    sources = []
    for source in valid_sources:
        with_suffix = os.path.join(root_dir, f"{source}_data")
        without_suffix = os.path.join(root_dir, source)
        if os.path.exists(with_suffix):
            sources.append((source, with_suffix))
        elif os.path.exists(without_suffix):
            sources.append((source, without_suffix))
    return sources


def main():
    parser = argparse.ArgumentParser(description="Build GraphRAG input blocks from local documents")
    parser.add_argument("--data-root", required=True, help="Root directory containing source folders")
    parser.add_argument("--output", required=True, help="Output JSONL path")
    args = parser.parse_args()

    conf = Config()
    sources = _collect_sources(args.data_root, conf.VALID_SOURCES)
    if not sources:
        raise SystemExit("No valid source directories found")

    all_chunks = []
    for source_name, source_dir in sources:
        chunks = process_graph_documents(
            source_dir,
            parent_chunk_size=conf.GRAPH_PARENT_CHUNK_SIZE,
            child_chunk_size=conf.GRAPH_CHILD_CHUNK_SIZE,
            chunk_overlap=conf.GRAPH_CHUNK_OVERLAP,
        )
        for chunk in chunks:
            payload = {
                "id": chunk.metadata.get("graph_id") or chunk.metadata.get("id"),
                "text": chunk.page_content,
                "source": source_name,
                "file_name": chunk.metadata.get("file_name"),
                "file_path": chunk.metadata.get("file_path"),
                "parent_id": chunk.metadata.get("graph_parent_id") or chunk.metadata.get("parent_id"),
                "chunk_role": chunk.metadata.get("chunk_role", "graph"),
                "metadata": chunk.metadata,
            }
            all_chunks.append(payload)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        for item in all_chunks:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Exported {len(all_chunks)} graph chunks to {args.output}")


if __name__ == "__main__":
    main()
