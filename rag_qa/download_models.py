"""
模型自动下载脚本
从 HuggingFace 下载所需的预训练模型
"""
from transformers import AutoModel, AutoTokenizer
from sentence_transformers import SentenceTransformer
import os

def download_model(model_name, save_path):
    """下载单个模型"""
    print(f"正在下载 {model_name}...")
    print(f"保存路径: {save_path}")
    
    # 创建目录
    os.makedirs(save_path, exist_ok=True)
    
    try:
        if "bge-m3" in model_name.lower():
            # BGE-M3 使用 SentenceTransformers
            model = SentenceTransformer(model_name)
            model.save(save_path)
        else:
            # 其他模型使用 Transformers
            model = AutoModel.from_pretrained(model_name)
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            
            model.save_pretrained(save_path)
            tokenizer.save_pretrained(save_path)
        
        print(f"✅ {model_name} 下载完成\n")
    except Exception as e:
        print(f"❌ {model_name} 下载失败: {e}\n")

if __name__ == "__main__":
    models = [
        ("bert-base-chinese", "models/bert-base-chinese"),
        ("BAAI/bge-m3", "models/bge-m3"),
        ("BAAI/bge-reranker-large", "models/bge-reranker-large"),
        # 注意：nlp_bert_document-segmentation_chinese-base 需要根据实际来源调整
        # ("your-org/nlp_bert_document-segmentation_chinese-base", 
        #  "nlp_bert_document-segmentation_chinese-base"),
    ]
    
    print("=" * 60)
    print("开始下载模型文件")
    print("=" * 60)
    print()
    
    for model_name, save_path in models:
        download_model(model_name, save_path)
    
    print("=" * 60)
    print("所有模型下载完成！")
    print("=" * 60)
    print("\n提示：")
    print("1. nlp_bert_document-segmentation_chinese-base 模型需要手动配置")
    print("2. 详见 MODELS_README.md 获取详细说明")
