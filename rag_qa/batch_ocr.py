# -*- coding:utf-8 -*-
"""
批量处理采矿手册 PDF 的 OCR 识别
"""
import os
import sys
from base import Config, logger
from edu_document_loaders import OCRPDFLoader

conf = Config()

def process_all_pdfs():
    """处理 data/mining 目录下所有 PDF"""
    pdf_dir = "data/mining"
    
    if not os.path.exists(pdf_dir):
        print(f"❌ 目录不存在：{pdf_dir}")
        return
    
    # 获取所有 PDF 文件
    pdf_files = [f for f in os.listdir(pdf_dir) if f.endswith('.pdf')]
    
    print("=" * 60)
    print(f"发现 {len(pdf_files)} 个 PDF 文件")
    print("=" * 60)
    
    for i, pdf_file in enumerate(pdf_files, 1):
        pdf_path = os.path.join(pdf_dir, pdf_file)
        cache_file = pdf_path + '.ocr_cache.json'
        
        print(f"\n[{i}/{len(pdf_files)}] 处理：{pdf_file}")
        print("-" * 60)
        
        # 检查是否已有缓存
        if os.path.exists(cache_file):
            print(f"⚠️  已存在缓存，跳过")
            continue
        
        try:
            # 禁用缓存，强制 OCR
            loader = OCRPDFLoader(file_path=pdf_path, use_cache=False)
            docs = loader.load()
            
            # 统计结果
            total_chars = sum(len(doc.page_content) for doc in docs)
            print(f"✓ OCR 完成")
            print(f"  识别字符数：{total_chars:,}")
            print(f"  缓存文件：{cache_file}")
            
        except Exception as e:
            print(f"❌ OCR 失败：{e}")
            logger.error(f"处理 {pdf_file} 失败：{e}")
    
    print("\n" + "=" * 60)
    print("批量处理完成！")
    print("=" * 60)

if __name__ == '__main__':
    process_all_pdfs()
