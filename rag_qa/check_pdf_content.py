# -*- coding:utf-8 -*-
"""
检查 PDF 文件的文本和 OCR 情况
"""
import fitz
import os

def check_pdf(pdf_path):
    """分析 PDF 文件"""
    print("=" * 60)
    print(f"检查 PDF: {pdf_path}")
    print("=" * 60)
    
    doc = fitz.open(pdf_path)
    
    print(f"\n总页数：{len(doc)}")
    print(f"\n前 3 页内容分析:")
    
    for i, page in enumerate(doc[:3]):
        print(f"\n--- 第 {i+1} 页 ---")
        
        # 提取文本
        text = page.get_text("text")
        print(f"文本长度：{len(text)}")
        if len(text) > 200:
            print(f"文本预览：{text[:200]}...")
        else:
            print(f"文本预览：{text}")
        
        # 获取图片信息
        img_list = page.get_image_info()
        print(f"图片数量：{len(img_list)}")
        
        # 检查是否有大尺寸图片
        large_imgs = []
        for img in img_list:
            bbox = img["bbox"]
            page_rect = page.rect
            if ((bbox[2] - bbox[0]) / page_rect.width > 0.3 or 
                (bbox[3] - bbox[1]) / page_rect.height > 0.3):
                large_imgs.append(bbox)
        
        print(f"大尺寸图片（>30% 页面）：{len(large_imgs)}")
    
    doc.close()

if __name__ == '__main__':
    pdf_file = "data/mining/现代采矿手册 上册.pdf"
    if os.path.exists(pdf_file):
        check_pdf(pdf_file)
    else:
        print(f"文件不存在：{pdf_file}")
