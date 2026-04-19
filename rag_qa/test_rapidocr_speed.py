# -*- coding:utf-8 -*-
"""
测试 RapidOCR 速度并估算处理时间
"""
import time
import fitz
from edu_document_loaders.edu_ocr import get_ocr

def test_rapidocr_speed():
    print("=" * 70)
    print("RapidOCR 速度测试")
    print("=" * 70)
    
    # 初始化 OCR 引擎
    print("\n初始化 RapidOCR 引擎...")
    ocr_engine = get_ocr()
    
    # 使用小样本测试（前 5 页）
    test_pdf = "data/mining/现代采矿手册 上册.pdf"
    print(f"\n测试文件：{test_pdf}")
    
    doc = fitz.open(test_pdf)
    test_pages = min(5, doc.page_count)
    
    total_time = 0
    page_times = []
    
    print(f"\n开始测试前 {test_pages} 页...")
    print("-" * 70)
    
    for i in range(test_pages):
        start = time.time()
        
        page = doc[i]
        img_list = page.get_image_info(xrefs=True)
        
        page_ocr_time = 0
        images_processed = 0
        
        for img in img_list:
            if xref := img.get("xref"):
                bbox = img["bbox"]
                # 检查图片尺寸是否超过阈值
                if ((bbox[2] - bbox[0]) / (page.rect.width) < 0.3
                        or (bbox[3] - bbox[1]) / (page.rect.height) < 0.3):
                    continue
                
                pix = fitz.Pixmap(doc, xref)
                img_array = __import__('numpy').frombuffer(
                    pix.samples, dtype=__import__('numpy').uint8
                ).reshape(pix.height, pix.width, -1)
                
                # OCR 识别
                ocr_result, _ = ocr_engine(img_array)
                if ocr_result:
                    images_processed += 1
        
        elapsed = time.time() - start
        page_times.append(elapsed)
        total_time += elapsed
        
        print(f"第 {i+1} 页：{elapsed:.2f}秒，处理 {images_processed} 张图片")
    
    doc.close()
    
    avg_page_time = sum(page_times) / len(page_times)
    
    print("-" * 70)
    print(f"\n测试结果:")
    print(f"  平均每页耗时：{avg_page_time:.2f}秒")
    print(f"  总测试时间：{total_time:.2f}秒")
    
    # 估算全部页面的时间
    total_pages = 923 + 1423 + 892  # 上 + 中 + 下
    
    print(f"\n{'='*70}")
    print(f"预估处理全部 {total_pages} 页的时间")
    print(f"{'='*70}")
    
    estimated_seconds = total_pages * avg_page_time
    estimated_minutes = estimated_seconds / 60
    estimated_hours = estimated_minutes / 60
    
    print(f"\n📊 统计信息:")
    print(f"  上册：923 页")
    print(f"  中册：1423 页")
    print(f"  下册：892 页")
    print(f"  总计：{total_pages} 页")
    
    print(f"\n⏱️ 预估时间:")
    print(f"  按每页 {avg_page_time:.2f}秒计算:")
    print(f"  - 总秒数：{estimated_seconds:.0f}秒")
    print(f"  - 总分钟：{estimated_minutes:.1f}分钟")
    print(f"  - 总小时：{estimated_hours:.2f}小时")
    
    if estimated_hours >= 1:
        hours = int(estimated_hours)
        minutes = int((estimated_hours - hours) * 60)
        print(f"  ≈ {hours}小时 {minutes}分钟")
    
    print(f"\n💡 优化建议:")
    print(f"  1. 使用缓存：处理过的页面不会重复 OCR")
    print(f"  2. 并行处理：可以同时处理多个 PDF 文件")
    print(f"  3. 降低阈值：当前 0.3 已经比较低，会处理更多图片")
    print(f"\n⚠️ 注意:")
    print(f"  - 实际时间取决于 PDF 中图片数量")
    print(f"  - 扫描版 PDF（图片多）会比电子版慢")
    print(f"  - 第一次处理最慢，后续使用缓存很快")

if __name__ == '__main__':
    test_rapidocr_speed()
