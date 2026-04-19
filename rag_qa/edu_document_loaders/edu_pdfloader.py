import cv2
import fitz  # pyMuPDF 里面的 fitz 包，不要与 pip install fitz 混淆
import numpy as np
from PIL import Image
from tqdm import tqdm
from typing import Iterator
from langchain_core.documents import Document
from langchain_core.document_loaders import BaseLoader
import json
import os
from base import Config, logger

conf = Config()

# PDF OCR 控制：只对宽高超过页面一定比例（图片宽/页面宽，图片高/页面高）的图片进行 OCR。
# 这样可以避免 PDF 中一些小图片的干扰，提高非扫描版 PDF 处理速度
# 降低阈值以识别更多图片内容（从 0.6 降至 0.3）
PDF_OCR_THRESHOLD = (0.3, 0.3)


class OCRPDFLoader(BaseLoader):
    """An example document loader that reads a file line by line."""

    def __init__(self, file_path: str, use_cache: bool = True, save_interval: int = 50) -> None:
        """Initialize the loader with a file path.

        Args:
            file_path: The path to the file to load.
            use_cache: Whether to use OCR cache to avoid re-processing.
            save_interval: Save cache every N pages (incremental save).
        """
        self.file_path = file_path
        self.use_cache = use_cache
        self.save_interval = save_interval  # 增量保存间隔
        # 缓存文件路径（与原文件同目录）
        self.cache_file_path = file_path + '.ocr_cache.json'
        # 初始化 OCR 引擎（只初始化一次，重复使用）
        from edu_document_loaders.edu_ocr import get_ocr
        self.ocr_engine = get_ocr()

    def lazy_load(self) -> Iterator[Document]:
        # <-- Does not take any arguments
        """A lazy loader that reads a file line by line.

        When you're implementing lazy load methods, you should use a generator
        to yield documents one by one.
        """

        line = self.pdf2text()
        yield Document(page_content=line, metadata={"source": self.file_path})



    def pdf2text(self):
        # 尝试加载缓存
        if self.use_cache and os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                # 验证文件是否被修改（通过比较文件大小和修改时间）
                file_stat = os.stat(self.file_path)
                if (cache_data.get('file_size') == file_stat.st_size and 
                    cache_data.get('file_mtime') == file_stat.st_mtime):
                    logger.info(f"使用 OCR 缓存：{self.file_path}")
                    return cache_data['content']
                else:
                    logger.info(f"文件已修改，重新 OCR: {self.file_path}")
            except Exception as e:
                logger.warning(f"加载缓存失败：{e}，将重新 OCR")
            
        # 打开 pdf 文件
        doc = fitz.open(self.file_path)
        ## 获取页数
        # print(f'len(doc)-->{len(doc)}')
        resp = ""
        b_unit = tqdm(total=doc.page_count, desc="OCRPDFLoader context page index: 0")
        
        for i, page in enumerate(doc):
            b_unit.set_description("OCRPDFLoader context page index: {}".format(i))
            b_unit.refresh()
            # 提取文本：默认使用 "text" 模式提取文本。
            text = page.get_text("text")
            resp += text + "\n"
            # 获取图片：获得所有显示的图像的元信息列表。
            img_list = page.get_image_info(xrefs=True)
            for img in img_list:
                # xref 一种编号，指向该图像对象在 PDF 文件中的位置
                if xref := img.get("xref"):
                    # 图像在页面上的位置和尺寸。
                    bbox = img["bbox"]
                    # 检查图片尺寸是否超过设定的阈值
                    if ((bbox[2] - bbox[0]) / (page.rect.width) < PDF_OCR_THRESHOLD[0]
                            or (bbox[3] - bbox[1]) / (page.rect.height) < PDF_OCR_THRESHOLD[1]):
                        continue
                    pix = fitz.Pixmap(doc, xref)
                    if int(page.rotation) != 0:  # 如果 Page 有旋转角度，则旋转图片
                        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, -1)
                        tmp_img = Image.fromarray(img_array)
                        ori_img = cv2.cvtColor(np.array(tmp_img), cv2.COLOR_RGB2BGR)
                        rot_img = self.rotate_img(img=ori_img, angle=360 - page.rotation)
                        img_array = cv2.cvtColor(rot_img, cv2.COLOR_RGB2BGR)
                    else:
                        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, -1)
        
                    # 使用 RapidOCR 本地识别（复用已初始化的引擎）
                    ocr_result, _ = self.ocr_engine(img_array)
                    if ocr_result:
                        ocr_text = "\n".join([line[1] for line in ocr_result])
                        if ocr_text:
                            resp += ocr_text + "\n"
            
            # 增量保存缓存：每 save_interval 页保存一次
            if self.use_cache and (i + 1) % self.save_interval == 0:
                self._save_incremental_cache(resp, doc.page_count, i + 1)
            
            # 更新进度
            b_unit.update(1)
            
        # 最终保存完整缓存
        if self.use_cache:
            self._save_final_cache(resp)
            
        return resp
    
    def _save_incremental_cache(self, content: str, total_pages: int, processed_pages: int):
        """增量保存缓存到临时文件"""
        try:
            file_stat = os.stat(self.file_path)
            cache_data = {
                'file_size': file_stat.st_size,
                'file_mtime': file_stat.st_mtime,
                'content': content,
                'processed_pages': processed_pages,
                'total_pages': total_pages,
                'is_incremental': True
            }
            # 保存到临时缓存文件
            temp_cache_path = self.cache_file_path + '.tmp'
            with open(temp_cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            logger.info(f"增量缓存已保存：已处理 {processed_pages}/{total_pages} 页")
        except Exception as e:
            logger.warning(f"增量缓存保存失败：{e}")
    
    def _save_final_cache(self, content: str):
        """保存最终完整缓存"""
        try:
            file_stat = os.stat(self.file_path)
            cache_data = {
                'file_size': file_stat.st_size,
                'file_mtime': file_stat.st_mtime,
                'content': content,
                'processed_pages': file_stat.st_size,  # 标记为完成
                'is_incremental': False
            }
            with open(self.cache_file_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            logger.info(f"OCR 缓存已保存：{self.cache_file_path}")
            
            # 删除临时缓存文件
            temp_cache_path = self.cache_file_path + '.tmp'
            if os.path.exists(temp_cache_path):
                os.remove(temp_cache_path)
                logger.info(f"已删除临时缓存文件")
        except Exception as e:
            logger.warning(f"保存缓存失败：{e}")

    def rotate_img(self, img, angle):
        '''
        img   --image
        angle --rotation angle
        return--rotated img
        '''

        h, w = img.shape[:2]
        rotate_center = (w / 2, h / 2)
        # 获取旋转矩阵
        # 参数1为旋转中心点;
        # 参数2为旋转角度,正值-逆时针旋转;负值-顺时针旋转
        # 参数3为各向同性的比例因子,1.0原图，2.0变成原来的2倍，0.5变成原来的0.5倍
        M = cv2.getRotationMatrix2D(rotate_center, angle, 1.0)
        # 计算图像新边界
        new_w = int(h * np.abs(M[0, 1]) + w * np.abs(M[0, 0]))
        new_h = int(h * np.abs(M[0, 0]) + w * np.abs(M[0, 1]))
        # 调整旋转矩阵以考虑平移
        M[0, 2] += (new_w - w) / 2
        M[1, 2] += (new_h - h) / 2

        rotated_img = cv2.warpAffine(img, M, (new_w, new_h))
        return rotated_img

if __name__ == '__main__':
    pdf_loader = OCRPDFLoader(file_path="/Users/ligang/Desktop/EduRAG课堂资料/codes/integrated_qa_system/rag_qa/samples/ocr_03.pdf")
    doc = pdf_loader.load()

    print(type(doc))
    print(doc)
    # text_spliter = CharacterTextSplitter(chunk_size=300, chunk_overlap=20)
    # result = text_spliter.split_documents(doc)
    # print(len(result))
    # print(result[0])