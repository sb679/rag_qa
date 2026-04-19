# -*- coding:utf-8 -*-
"""
场景 1: 构建知识库 - 批量处理文档并入库

使用方法:
    python examples_01_build_knowledge_base.py
"""
import sys, os
from pathlib import Path

# 添加项目路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from core.document_processor import process_documents
from core.vector_store import VectorStore
from base import Config, logger

conf = Config()


def build_knowledge_base(data_dir="./data", batch_size=500):
    """
    构建知识库
    
    Args:
        data_dir: 数据目录
        batch_size: 批处理大小
    """
    print("="*80)
    print("📚 EduRAG 知识库构建工具")
    print("="*80)
    
    # 初始化向量存储
    print("\n正在连接 Milvus 数据库...")
    try:
        vector_store = VectorStore()
        print("✅ Milvus 连接成功")
    except Exception as e:
        print(f"❌ Milvus 连接失败：{e}")
        return False
    
    # 获取所有学科目录
    valid_sources = conf.VALID_SOURCES
    print(f"\n待处理的学科：{valid_sources}")
    
    total_chunks = 0
    
    for source in valid_sources:
        # 尝试两种目录格式
        dir_paths = [
            os.path.join(data_dir, f"{source}_data"),
            os.path.join(data_dir, source)
        ]
        
        dir_path = None
        for path in dir_paths:
            if os.path.exists(path):
                dir_path = path
                break
        
        if not dir_path:
            print(f"\n⚠️  跳过：{source} (目录不存在)")
            continue
        
        print(f"\n{'='*80}")
        print(f"📁 开始处理：{source}")
        print(f"   目录：{dir_path}")
        print(f"{'='*80}")
        
        try:
            # 处理文档
            chunks = process_documents(
                dir_path,
                parent_chunk_size=conf.PARENT_CHUNK_SIZE,
                child_chunk_size=conf.CHILD_CHUNK_SIZE,
                chunk_overlap=conf.CHUNK_OVERLAP
            )
            
            print(f"\n✅ 文档切分完成：{len(chunks)} 个块")
            
            if not chunks:
                print(f"⚠️  {source} 没有有效文档")
                continue
            
            # 批量插入向量库
            print(f"\n正在插入向量库 (批次大小：{batch_size})...")
            vector_store.add_documents(chunks, batch_size=batch_size)
            
            total_chunks += len(chunks)
            print(f"✅ {source} 处理完成，新增 {len(chunks)} 个向量")
            
        except Exception as e:
            print(f"\n❌ {source} 处理失败：{e}")
            logger.error(f"处理 {source} 失败：{e}")
            continue
    
    print("\n" + "="*80)
    print(f"🎉 知识库构建完成！")
    print(f"   总文档块数：{total_chunks}")
    print(f"   学科数量：{len(valid_sources)}")
    print("="*80)
    
    return True


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description="构建 RAG 知识库")
    parser.add_argument('--data-dir', type=str, default='./data', help='数据目录')
    parser.add_argument('--batch-size', type=int, default=500, help='批处理大小')
    
    args = parser.parse_args()
    
    success = build_knowledge_base(
        data_dir=args.data_dir,
        batch_size=args.batch_size
    )
    
    if success:
        print("\n✅ 知识库构建成功！可以开始使用问答系统了")
        print("\n运行以下命令启动问答:")
        print("  python rag_main.py")
    else:
        print("\n❌ 知识库构建失败，请检查错误信息")
        sys.exit(1)
