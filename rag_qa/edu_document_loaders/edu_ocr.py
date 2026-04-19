from typing import TYPE_CHECKING
'''
OCR 配置说明：
使用 CPU 模式进行 OCR 识别
不使用 GPU 加速
'''

def get_ocr() -> "RapidOCR":
    '''
    获取 OCR 实例（CPU 模式）
    
    Returns:
        RapidOCR 实例（CPU 模式）
    '''
    # 强制使用 CPU 模式
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()
    print(f"ℹ OCR 使用 CPU 模式 (rapidocr_onnxruntime)")
    return ocr
