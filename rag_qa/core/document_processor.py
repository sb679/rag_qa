# 这个脚本讲义的代码架构图没有体现，需要进行补充
import os
import importlib
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders.markdown import UnstructuredMarkdownLoader
from langchain.text_splitter import MarkdownTextSplitter
from datetime import datetime
from typing import Optional
import sys
# 获取当前文件所在目录的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
# print(f'current_dir--》{current_dir}')
# 获取core文件所在的目录的绝对路径
rag_qa_path = os.path.dirname(current_dir)
# print(f'rag_qa_path--》{rag_qa_path}')
sys.path.insert(0, rag_qa_path)
# 获取根目录文件所在的绝对位置
project_root = os.path.dirname(rag_qa_path)
sys.path.insert(0, project_root)
from edu_document_loaders import OCRPDFLoader, OCRDOCLoader, OCRPPTLoader, OCRIMGLoader
from edu_text_spliter import ChineseRecursiveTextSplitter, HybridSemanticTextSplitter
from base import logger, Config

conf = Config()


def _resolve_chunking_mode(source: Optional[str]) -> str:
    source_key = (source or '').strip().lower()
    mode_by_source = conf.CHUNKING_MODE_BY_SOURCE or {}
    return mode_by_source.get(source_key, mode_by_source.get('default', conf.CHUNKING_MODE)).strip().lower()


def _build_child_splitter(chunk_size, chunk_overlap, source=None):
    rule_child_splitter = ChineseRecursiveTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunking_mode = _resolve_chunking_mode(source)

    if chunking_mode != 'hybrid':
        logger.info(f"当前分块模式: {chunking_mode or 'rule'} (使用规则子块切分)")
        return rule_child_splitter

    logger.info(
        f"当前分块模式: hybrid (结构+轻语义), source={source or 'default'}, "
        f"threshold={conf.SEMANTIC_SIM_THRESHOLD}, "
        f"min_chunk={conf.SEMANTIC_MIN_CHUNK_SIZE}, max_chunk={conf.SEMANTIC_MAX_CHUNK_SIZE}"
    )
    return HybridSemanticTextSplitter(
        fallback_splitter=rule_child_splitter,
        model_path=conf.SEMANTIC_MODEL_PATH,
        similarity_threshold=conf.SEMANTIC_SIM_THRESHOLD,
        min_chunk_size=conf.SEMANTIC_MIN_CHUNK_SIZE,
        max_chunk_size=conf.SEMANTIC_MAX_CHUNK_SIZE,
        min_paragraph_chars=conf.STRUCT_MIN_PARAGRAPH_CHARS,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def _split_loaded_documents(documents, parent_chunk_size, child_chunk_size, chunk_overlap, source=None, chunk_role="retrieval"):
    parent_splitter = ChineseRecursiveTextSplitter(chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap)
    child_splitter = _build_child_splitter(chunk_size=child_chunk_size, chunk_overlap=chunk_overlap, source=source)
    markdown_parent_splitter = MarkdownTextSplitter(chunk_size=parent_chunk_size, chunk_overlap=chunk_overlap)
    markdown_child_splitter = MarkdownTextSplitter(chunk_size=child_chunk_size, chunk_overlap=chunk_overlap)

    child_chunks = []
    for i, doc in enumerate(documents):
        file_extension = os.path.splitext(doc.metadata.get("file_path", ""))[1].lower()
        is_markdown = (file_extension == '.md')
        parent_splitter_to_use = markdown_parent_splitter if is_markdown else parent_splitter
        child_splitter_to_use = markdown_child_splitter if is_markdown else child_splitter
        logger.info(
            f"处理文档: {doc.metadata['file_path']}, 使用切分器: {'Markdown' if is_markdown else 'ChineseRecursive'}, 处理类型: {chunk_role}"
        )

        parent_docs = parent_splitter_to_use.split_documents([doc])
        for j, parent_doc in enumerate(parent_docs):
            parent_id = f"{chunk_role}_doc_{i}_parent_{j}"
            sub_chunks = child_splitter_to_use.split_documents([parent_doc])
            for k, sub_chunk in enumerate(sub_chunks):
                sub_chunk.metadata["chunk_role"] = chunk_role
                sub_chunk.metadata["chunking_mode"] = _resolve_chunking_mode(source)
                sub_chunk.metadata["parent_id"] = parent_id
                sub_chunk.metadata["parent_content"] = parent_doc.page_content
                sub_chunk.metadata["id"] = f"{parent_id}_child_{k}"
                if chunk_role == "graph":
                    sub_chunk.metadata["graph_parent_id"] = parent_id
                    sub_chunk.metadata["graph_parent_content"] = parent_doc.page_content
                    sub_chunk.metadata["graph_id"] = f"{parent_id}_child_{k}"
                child_chunks.append(sub_chunk)

    return child_chunks
# 定义支持的文件类型及其对应的加载器字典
document_loaders = {
    # 文本文件使用 TextLoader
    ".txt": TextLoader,
    # PDF 文件使用 OCRPDFLoader
    ".pdf": OCRPDFLoader,
    # Word 文件使用 OCRDOCLoader
    ".docx": OCRDOCLoader,
    # PPT 文件使用 OCRPPTLoader
    ".ppt": OCRPPTLoader,
    # PPTX 文件使用 OCRPPTLoader
    ".pptx": OCRPPTLoader,
    # JPG 文件使用 OCRIMGLoader
    ".jpg": OCRIMGLoader,
    # JPEG 文件使用 OCRIMGLoader
    ".jpeg": OCRIMGLoader,
    # PNG 文件使用 OCRIMGLoader
    ".png": OCRIMGLoader,
    # WEBP 文件使用 OCRIMGLoader
    ".webp": OCRIMGLoader,
    # BMP 文件使用 OCRIMGLoader
    ".bmp": OCRIMGLoader,
    # GIF 文件使用 OCRIMGLoader
    ".gif": OCRIMGLoader,
    # Markdown 文件使用 UnstructuredMarkdownLoader
    ".md": UnstructuredMarkdownLoader
}

# Dedoc 兜底支持的额外格式（主加载器不覆盖时使用）
DEDOC_FALLBACK_EXTENSIONS = {
    ".doc", ".rtf", ".odt", ".html", ".htm", ".xlsx", ".xls", ".csv", ".epub"
}

SUPPORTED_EXTENSIONS = set(document_loaders.keys()) | DEDOC_FALLBACK_EXTENSIONS


def _load_with_primary_loader(file_path: str, file_extension: str):
    loader_class = document_loaders[file_extension]
    if file_extension == ".txt":
        loader = loader_class(file_path, encoding="utf-8")
    elif file_extension == ".pdf":
        loader = loader_class(file_path, use_cache=True)
    else:
        loader = loader_class(file_path)
    return loader.load()


def _dedoc_extract_text(file_path: str) -> str:
    """优先尝试 dedoc；若不可用则返回空字符串。"""
    try:
        dedoc_module = importlib.import_module("dedoc")
    except Exception:
        return ""

    # 采用宽容探测方式，尽量适配 dedoc 的不同版本 API。
    candidates = [
        (dedoc_module, "parse_file"),
        (dedoc_module, "read"),
        (dedoc_module, "extract_text"),
    ]
    try:
        manager_module = importlib.import_module("dedoc.manager.dedoc_manager")
        manager_class = getattr(manager_module, "DedocManager", None)
        if manager_class is not None:
            manager = manager_class()
            candidates.extend([
                (manager, "parse"),
                (manager, "parse_file"),
                (manager, "read"),
            ])
    except Exception:
        pass

    for target, func_name in candidates:
        func = getattr(target, func_name, None)
        if not callable(func):
            continue
        try:
            parsed = func(file_path)
        except TypeError:
            continue
        except Exception:
            continue

        if isinstance(parsed, str):
            return parsed
        if isinstance(parsed, dict):
            for key in ("text", "content", "plain_text"):
                val = parsed.get(key)
                if isinstance(val, str) and val.strip():
                    return val
        # 常见对象结构：.content 或 .text
        for attr in ("content", "text"):
            val = getattr(parsed, attr, None)
            if isinstance(val, str) and val.strip():
                return val

    return ""


def _load_with_dedoc_fallback(file_path: str):
    if not conf.DEDOC_FALLBACK_ENABLE:
        return []

    extracted_text = _dedoc_extract_text(file_path)
    if extracted_text and extracted_text.strip():
        logger.info(f"Dedoc 兜底解析成功: {file_path}")
        return [Document(page_content=extracted_text, metadata={"source": file_path})]

    logger.warning(f"Dedoc 兜底未获得有效文本: {file_path}")
    return []


def _load_file_with_fallback(file_path: str):
    file_extension = os.path.splitext(file_path)[1].lower()

    if file_extension in document_loaders:
        try:
            return _load_with_primary_loader(file_path, file_extension)
        except Exception as e:
            logger.error(f"主加载器失败，尝试 Dedoc 兜底: {file_path}, 错误: {str(e)}")
            return _load_with_dedoc_fallback(file_path)

    if file_extension in DEDOC_FALLBACK_EXTENSIONS:
        return _load_with_dedoc_fallback(file_path)

    logger.warning(f"不支持的文件类型: {file_path}")
    return []
# 定义函数，从指定文件夹加载多种类型文件并添加元数据
def load_documents_from_directory(directory_path):
    # 初始化空列表，用于存储加载的文档
    documents = []
    # 获取支持的文件扩展名集合
    supported_extensions = SUPPORTED_EXTENSIONS
    # print(f'supported_extensions--》{supported_extensions}')
    # 从目录名提取学科类别（如 "mining" -> "ai"）
    # print(f'1---》{os.path.basename(directory_path)}')
    source = os.path.basename(directory_path).replace("_data", "")
    # print(f'source-->{source}')
    # 遍历指定目录及其子目录
    for root, _, files in os.walk(directory_path):
        # print(f'root---》{root}')
        # print(f'files---》{files}')
        # 遍历当前目录下的所有文件
        for file in files:
            # 跳过 OCR 缓存文件（.ocr_cache.json）
            if file.endswith('.ocr_cache.json'):
                continue
            
            # 构造文件的完整路径
            file_path = os.path.join(root, file)
            # print(f'file_path--》{file_path}')
            # print(os.path.splitext(file_path))
            # 获取文件扩展名并转换为小写
            file_extension = os.path.splitext(file_path)[1].lower()
            # print(f'file_extension--》{file_extension}')
            # 检查文件类型是否在支持的扩展名列表中
            if file_extension in supported_extensions:
                # 使用 try-except 捕获加载过程中的异常
                try:
                    loaded_docs = _load_file_with_fallback(file_path)
                    # print(f'loaded_docs--》{loaded_docs}')
                    # print(f'loaded_docs--》{len(loaded_docs)}')
                    for doc in loaded_docs:
                        stored_name = os.path.basename(file_path)
                        file_id = ""
                        file_name = stored_name
                        if "__" in stored_name:
                            prefix, original = stored_name.split("__", 1)
                            if len(prefix) >= 8:
                                file_id = prefix
                                file_name = original or stored_name

                        # 为文档添加学科类别元数据
                        doc.metadata["source"] = source
                        # 为文档添加文件路径元数据
                        doc.metadata["file_path"] = file_path
                        # 为文档添加文件名元数据（用于知识库文件级统计）
                        doc.metadata["file_name"] = file_name
                        doc.metadata["file_id"] = file_id
                        # 为文档添加当前时间戳元数据
                        doc.metadata["timestamp"] = datetime.now().isoformat()
                    # print(f'loaded_docs111--》{loaded_docs}')
                    documents.extend(loaded_docs)
                    # 记录成功加载文件的日志
                    logger.info(f"成功加载文件: {file_path}")
                except Exception as e:
                    logger.error(f"加载文件 {file_path} 失败: {str(e)}")
            # 如果文件类型不在支持列表中
            else:
                # 记录警告日志，提示不支持的文件类型
                logger.warning(f"不支持的文件类型: {file_path}")
    # 返回加载的所有文档列表
    return documents

# 定义函数，处理文档并进行分层切分，返回子块结果
def process_documents(directory_path, parent_chunk_size=conf.PARENT_CHUNK_SIZE,
                     child_chunk_size=conf.CHILD_CHUNK_SIZE,
                     chunk_overlap=conf.CHUNK_OVERLAP):
    # 从指定目录加载所有文档
    documents = load_documents_from_directory(directory_path)
    # 记录加载的文档总数日志
    logger.info(f"加载的文档数量: {len(documents)}")

    child_chunks = _split_loaded_documents(
        documents,
        parent_chunk_size,
        child_chunk_size,
        chunk_overlap,
        source=os.path.basename(directory_path).replace("_data", ""),
        chunk_role="retrieval",
    )

    # 记录子块总数日志
    logger.info(f"子块数量: {len(child_chunks)}")
    # 返回所有子块列表
    return child_chunks


def process_single_file(file_path, parent_chunk_size=conf.PARENT_CHUNK_SIZE,
                        child_chunk_size=conf.CHILD_CHUNK_SIZE,
                        chunk_overlap=conf.CHUNK_OVERLAP,
                        source=None):
    """仅处理一个文件，避免上传单文件时重复扫描整个目录。"""
    file_path = os.path.abspath(file_path)
    if not os.path.isfile(file_path):
        logger.warning(f"文件不存在，无法处理: {file_path}")
        return []

    file_extension = os.path.splitext(file_path)[1].lower()
    if file_extension not in SUPPORTED_EXTENSIONS:
        logger.warning(f"不支持的文件类型: {file_path}")
        return []

    if source is None:
        source = os.path.basename(os.path.dirname(file_path)).replace("_data", "")
    loaded_docs = _load_file_with_fallback(file_path)
    if not loaded_docs:
        logger.error(f"加载文件 {file_path} 失败: 无可用内容")
        return []

    documents = []
    for doc in loaded_docs:
        stored_name = os.path.basename(file_path)
        file_id = ""
        file_name = stored_name
        if "__" in stored_name:
            prefix, original = stored_name.split("__", 1)
            if len(prefix) >= 8:
                file_id = prefix
                file_name = original or stored_name

        doc.metadata["source"] = source
        doc.metadata["file_path"] = file_path
        doc.metadata["file_name"] = file_name
        doc.metadata["file_id"] = file_id
        doc.metadata["timestamp"] = datetime.now().isoformat()
        documents.append(doc)

    logger.info(f"单文件加载完成: {file_path}, 文档数: {len(documents)}")

    child_chunks = _split_loaded_documents(
        documents,
        parent_chunk_size,
        child_chunk_size,
        chunk_overlap,
        source=source,
        chunk_role="retrieval",
    )

    logger.info(f"单文件子块数量: {len(child_chunks)}")
    return child_chunks


def process_graph_documents(directory_path, parent_chunk_size=conf.GRAPH_PARENT_CHUNK_SIZE,
                            child_chunk_size=conf.GRAPH_CHILD_CHUNK_SIZE,
                            chunk_overlap=conf.GRAPH_CHUNK_OVERLAP):
    """为 GraphRAG 实体抽取准备更大的上下文块。"""
    documents = load_documents_from_directory(directory_path)
    logger.info(f"GraphRAG 加载的文档数量: {len(documents)}")
    child_chunks = _split_loaded_documents(
        documents,
        parent_chunk_size,
        child_chunk_size,
        chunk_overlap,
        source=os.path.basename(directory_path).replace("_data", ""),
        chunk_role="graph",
    )
    logger.info(f"GraphRAG 子块数量: {len(child_chunks)}")
    return child_chunks


def process_graph_single_file(file_path, parent_chunk_size=conf.GRAPH_PARENT_CHUNK_SIZE,
                              child_chunk_size=conf.GRAPH_CHILD_CHUNK_SIZE,
                              chunk_overlap=conf.GRAPH_CHUNK_OVERLAP,
                              source=None):
    """为单文件生成 GraphRAG 实体抽取输入块。"""
    file_path = os.path.abspath(file_path)
    if not os.path.isfile(file_path):
        logger.warning(f"文件不存在，无法处理: {file_path}")
        return []

    file_extension = os.path.splitext(file_path)[1].lower()
    if file_extension not in SUPPORTED_EXTENSIONS:
        logger.warning(f"不支持的文件类型: {file_path}")
        return []

    if source is None:
        source = os.path.basename(os.path.dirname(file_path)).replace("_data", "")

    loaded_docs = _load_file_with_fallback(file_path)
    if not loaded_docs:
        logger.error(f"加载文件 {file_path} 失败: 无可用内容")
        return []

    documents = []
    for doc in loaded_docs:
        stored_name = os.path.basename(file_path)
        file_id = ""
        file_name = stored_name
        if "__" in stored_name:
            prefix, original = stored_name.split("__", 1)
            if len(prefix) >= 8:
                file_id = prefix
                file_name = original or stored_name

        doc.metadata["source"] = source
        doc.metadata["file_path"] = file_path
        doc.metadata["file_name"] = file_name
        doc.metadata["file_id"] = file_id
        doc.metadata["timestamp"] = datetime.now().isoformat()
        documents.append(doc)

    logger.info(f"GraphRAG 单文件加载完成: {file_path}, 文档数: {len(documents)}")
    child_chunks = _split_loaded_documents(
        documents,
        parent_chunk_size,
        child_chunk_size,
        chunk_overlap,
        source=source,
        chunk_role="graph",
    )
    logger.info(f"GraphRAG 单文件子块数量: {len(child_chunks)}")
    return child_chunks
if __name__ == '__main__':
    directory_path = '/Users/ligang/Desktop/EduRAG课堂资料/codes/integrated_qa_system/rag_qa/data/mining'
    # documents = load_documents_from_directory(directory_path)
    # print(documents)
    child_chunks = process_documents(directory_path)
    print(f'child_chunks--》{child_chunks[0]}')

