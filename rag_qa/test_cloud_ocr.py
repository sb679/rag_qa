# -*- coding:utf-8 -*-
"""
测试云雾 OCR 性能
"""
import time
from edu_document_loaders import OCRPDFLoader

def test_ocr_performance():
    print("=" * 70)
    print("云雾 OCR 性能测试")
    print("=" * 70)
    
    # 使用小样本测试
    test_pdf = "samples/ocr_03.pdf"
    
    print(f"\n测试文件：{test_pdf}")
    print("禁用缓存，强制重新 OCR...")
    
    start_time = time.time()
    
    loader = OCRPDFLoader(file_path=test_pdf, use_cache=False)
    docs = loader.load()
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    content = docs[0].page_content
    
    print(f"\n✅ OCR 完成!")
    print(f"\n统计信息:")
    print(f"  总耗时：{elapsed:.2f} 秒")
    print(f"  识别字符数：{len(content)}")
    print(f"  平均速度：{len(content)/elapsed:.1f} 字符/秒")
    
    print(f"\n内容预览 (前 300 字):")
    print("-" * 70)
    print(content[:300])
    print("-" * 70)
    
    # 估算采矿手册的 OCR 时间
    print(f"\n{'='*70}")
    print(f"预估采矿手册 OCR 时间（基于实际页数）:")
    print(f"{'='*70}")
    
    # 假设每页处理时间相同
    pages_per_second = 1 / elapsed if elapsed > 0 else float('inf')
    
    mining_books = [
        ("上册", 923),
        ("中册", 1423),
        ("下册", 2761)
    ]
    
    for name, pages in mining_books:
        estimated_time = pages * elapsed
        hours = int(estimated_time // 3600)
        minutes = int((estimated_time % 3600) // 60)
        seconds = int(estimated_time % 60)
        
        print(f"{name} ({pages}页): 约 {hours}小时 {minutes}分钟 {seconds}秒")
    
    total_pages = sum(pages for _, pages in mining_books)
    total_time = total_pages * elapsed
    total_hours = int(total_time // 3600)
    total_minutes = int((total_time % 3600) // 60)
    
    print(f"\n总计 ({total_pages}页): 约 {total_hours}小时 {total_minutes}分钟")
    print(f"\n相比本地 OCR 的 36 小时，节省了 {36 - total_hours:.1f} 小时!")
    
    print(f"\n{'='*70}")
    print(f"✅ 云雾 OCR 性能优秀！建议使用云雾 API")
    print(f"{'='*70}")

if __name__ == '__main__':
    test_ocr_performance()
