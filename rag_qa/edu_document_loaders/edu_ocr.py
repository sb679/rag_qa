import threading

from base import logger

'''
OCR 配置说明：
使用 CPU 模式进行 OCR 识别
不使用 GPU 加速
'''

_OCR_INSTANCE = None
_OCR_LOCK = threading.Lock()


def get_ocr() -> "RapidOCR":
    '''
    获取 OCR 实例（CPU 模式，单例复用）

    Returns:
        RapidOCR 实例（CPU 模式）
    '''
    global _OCR_INSTANCE
    if _OCR_INSTANCE is not None:
        return _OCR_INSTANCE

    with _OCR_LOCK:
        if _OCR_INSTANCE is None:
            from rapidocr_onnxruntime import RapidOCR

            _OCR_INSTANCE = RapidOCR()
            logger.info("OCR 引擎初始化完成 (rapidocr_onnxruntime, CPU)")

    return _OCR_INSTANCE
