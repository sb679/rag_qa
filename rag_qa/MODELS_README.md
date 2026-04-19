# 模型文件获取指南

由于模型文件体积较大（总计约 4GB），未包含在 Git 仓库中。请按以下方法获取所需模型。

## 📦 需要的模型

| 模型名称 | 用途 | 大小 | 来源 |
|---------|------|------|------|
| bert-base-chinese | BERT 基础模型 | ~400MB | HuggingFace |
| bge-m3 | 文本嵌入模型 | ~2GB | HuggingFace |
| bge-reranker-large | 重排序模型 | ~1.2GB | HuggingFace |
| nlp_bert_document-segmentation_chinese-base | 文档分割模型 | ~400MB | HuggingFace |

## 🔧 自动下载脚本

创建 `download_models.py` 文件并运行：

```python
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
        ("your-org/nlp_bert_document-segmentation_chinese-base", 
         "nlp_bert_document-segmentation_chinese-base"),
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
```

运行脚本：
```bash
python download_models.py
```

## 🌐 手动下载（推荐国内用户）

### 方法 1: 使用 HuggingFace Mirror

```bash
# 设置镜像加速
export HF_ENDPOINT=https://hf-mirror.com

# 下载模型
python download_models.py
```

### 方法 2: 从 ModelScope 下载（阿里云）

```python
from modelscope import snapshot_download

# 下载 BERT
model_dir = snapshot_download('AI-ModelScope/bert-base-chinese', 
                              cache_dir='models')

# 下载 BGE-M3
model_dir = snapshot_download('AI-ModelScope/bge-m3', 
                              cache_dir='models')

# 下载 BGE-Reranker
model_dir = snapshot_download('AI-ModelScope/bge-reranker-large', 
                              cache_dir='models')
```

### 方法 3: 百度网盘下载

如有提供百度网盘链接：
```
链接: https://pan.baidu.com/s/xxx
提取码: xxxx
```

下载后解压到项目根目录，确保目录结构如下：
```
rag_qa/
├── models/
│   ├── bert-base-chinese/
│   ├── bge-m3/
│   └── bge-reranker-large/
└── nlp_bert_document-segmentation_chinese-base/
```

## ✅ 验证模型

下载完成后，运行验证脚本：

```python
"""验证模型是否正确加载"""
import torch
from transformers import AutoModel, AutoTokenizer
from sentence_transformers import SentenceTransformer

print("验证模型加载...")

# 测试 BERT
try:
    bert_model = AutoModel.from_pretrained('models/bert-base-chinese')
    bert_tokenizer = AutoTokenizer.from_pretrained('models/bert-base-chinese')
    print("✅ BERT 模型加载成功")
except Exception as e:
    print(f"❌ BERT 模型加载失败: {e}")

# 测试 BGE-M3
try:
    bge_model = SentenceTransformer('models/bge-m3')
    print("✅ BGE-M3 模型加载成功")
except Exception as e:
    print(f"❌ BGE-M3 模型加载失败: {e}")

# 测试 BGE-Reranker
try:
    reranker_model = AutoModel.from_pretrained('models/bge-reranker-large')
    print("✅ BGE-Reranker 模型加载成功")
except Exception as e:
    print(f"❌ BGE-Reranker 模型加载失败: {e}")

print("\n所有模型验证完成！")
```

## 💡 提示

1. **网络问题**: 如果下载速度慢，建议使用镜像加速
2. **磁盘空间**: 确保至少有 10GB 可用空间
3. **模型更新**: 如需更新模型，删除对应目录后重新下载
4. **自定义模型**: 如使用自己训练的模型，替换相应目录即可

## 🔗 相关链接

- HuggingFace: https://huggingface.co/
- ModelScope: https://modelscope.cn/
- BGE 模型主页: https://github.com/FlagOpen/FlagEmbedding
