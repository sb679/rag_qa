# RAG_QA 项目结构整理方案

## 当前项目分析

### 可以删除的文件（一次性脚本、历史实验）
这些文件是数据处理、模型训练、测试的一次性脚本，不属于核心系统：

**数据分析脚本：**
- `analyze_complex_queries.py`
- `analyze_data.py`
- `analyze_mining_data.py`
- `analyze_strategy_dataset.py`

**数据集构建脚本：**
- `build_mining_55_splits.py`
- `build_mining_curated_100.py`
- `build_mining_evaluation_dataset.py`
- `build_mining_readable_top100.py`
- `build_strategy_dataset.py`
- `create_final_strategy_dataset.py`

**数据生成脚本：**
- `generate_mining_qg_dataset.py`
- `generate_new_training_data.py`
- `generate_pdf_docs.py`
- `generate_training_data.py`
- `generate_training_report.py`

**模型训练脚本：**
- `train_classifier.py`
- `train_strategy_classifier.py`
- `quick_train.py`

**测试脚本：**
- `test_cloud_ocr_new.py`
- `test_cloud_ocr.py`
- `test_conversation_manager.py`
- `test_diagnosis.py`
- `test_integration.py`
- `test_mining_rag.py`
- `test_query.py`
- `test_rapidocr_speed.py`

**工具脚本：**
- `batch_ocr.py`
- `check_database.py`
- `check_ocr_progress.py`
- `check_pdf_content.py`
- `convert_mining_data_to_ragas.py`
- `download_models.py`
- `monitor_and_report.py`
- `scan_sensitive_info.py`
- `simulate_complex_mining_queries.py`
- `view_sources.py`

**示例脚本：**
- `examples_01_build_knowledge_base.py`
- `examples_02_interactive_qa.py`
- `examples_03_view_sources.py`

### 可以删除的目录
- `bert_strategy_logs/` - 训练日志
- `classify_data/` - 分类数据临时文件
- `test_conversations/` - 测试会话
- `tmp_trainer/` - 临时训练文件
- `rag_assesment/` - 评估脚本（只有一个 rag_as.py）

### 可以删除的文档
- `采矿评估数据集使用说明.md` - 历史文档
- `会话管理使用指南.md` - 历史文档
- `文档索引.md` - 历史文档
- `文档整理总结.md` - 历史文档
- `DESENSITIZATION_REPORT.md` - 脱敏报告
- `.github_upload_checklist.md` - GitHub 上传清单

### 需要保留的核心文件

**主程序入口：**
- `rag_main.py` - 主程序
- `config.ini` - 配置文件

**核心业务模块：**
- `core/` - 核心业务逻辑
- `base/` - 基础配置和日志
- `edu_document_loaders/` - 文档加载器
- `edu_text_spliter/` - 文本分割器

**后端 API：**
- `web/backend/` - FastAPI 后端
- `web/frontend/` - Vue 前端

**模型文件：**
- `models/` - 预训练模型
- `bert_query_classifier_new/` - 查询分类器
- `bert_strategy_classifier/` - 策略分类器
- `nlp_bert_document-segmentation_chinese-base/` - 文档分割模型

**数据文件：**
- `data/` - 知识库数据
- `samples/` - 示例文件
- `conversations/` - 会话记录
- `knowledge_versions/` - 知识库版本（新增）
- `feedback_data/` - 反馈数据（新增）
- `audit_logs/` - 审计日志（新增）

**文档：**
- `README.md` - 项目说明
- `MODELS_README.md` - 模型说明
- `INDUSTRIAL_FEATURES_PLAN.md` - 工业化功能方案（新增）
- `PROJECT_STRUCTURE.md` - 项目结构说明（新增）

## 推荐的整理方案

### 第一步：创建 `scripts/` 目录，移动所有一次性脚本
```
scripts/
├── data_analysis/
│   ├── analyze_complex_queries.py
│   ├── analyze_data.py
│   ├── analyze_mining_data.py
│   └── analyze_strategy_dataset.py
├── dataset_build/
│   ├── build_mining_55_splits.py
│   ├── build_mining_curated_100.py
│   ├── build_mining_evaluation_dataset.py
│   ├── build_mining_readable_top100.py
│   ├── build_strategy_dataset.py
│   └── create_final_strategy_dataset.py
├── data_generation/
│   ├── generate_mining_qg_dataset.py
│   ├── generate_new_training_data.py
│   ├── generate_pdf_docs.py
│   ├── generate_training_data.py
│   └── generate_training_report.py
├── model_training/
│   ├── train_classifier.py
│   ├── train_strategy_classifier.py
│   └── quick_train.py
├── testing/
│   ├── test_cloud_ocr_new.py
│   ├── test_cloud_ocr.py
│   ├── test_conversation_manager.py
│   ├── test_diagnosis.py
│   ├── test_integration.py
│   ├── test_mining_rag.py
│   ├── test_query.py
│   └── test_rapidocr_speed.py
└── tools/
    ├── batch_ocr.py
    ├── check_database.py
    ├── check_ocr_progress.py
    ├── check_pdf_content.py
    ├── convert_mining_data_to_ragas.py
    ├── download_models.py
    ├── monitor_and_report.py
    ├── scan_sensitive_info.py
    └── simulate_complex_mining_queries.py
```

### 第二步：删除不必要的目录
- `bert_strategy_logs/`
- `classify_data/`
- `test_conversations/`
- `tmp_trainer/`
- `rag_assesment/`

### 第三步：删除历史文档
- `采矿评估数据集使用说明.md`
- `会话管理使用指南.md`
- `文档索引.md`
- `文档整理总结.md`
- `DESENSITIZATION_REPORT.md`
- `.github_upload_checklist.md`

### 第四步：保留的根目录结构
```
rag_qa/
├── README.md                          # 项目说明
├── MODELS_README.md                   # 模型说明
├── INDUSTRIAL_FEATURES_PLAN.md        # 工业化功能方案
├── PROJECT_STRUCTURE.md               # 项目结构说明
├── config.ini                         # 配置文件
├── rag_main.py                        # 主程序入口
├── requirments.txt                    # 依赖列表
│
├── base/                              # 基础模块
├── core/                              # 核心业务逻辑
├── edu_document_loaders/              # 文档加载器
├── edu_text_spliter/                  # 文本分割器
│
├── models/                            # 预训练模型
├── bert_query_classifier_new/         # 查询分类器
├── bert_strategy_classifier/          # 策略分类器
├── nlp_bert_document-segmentation_chinese-base/  # 文档分割模型
│
├── data/                              # 知识库数据
├── samples/                           # 示例文件
├── conversations/                     # 会话记录
├── knowledge_versions/                # 知识库版本
├── feedback_data/                     # 反馈数据
├── audit_logs/                        # 审计日志
│
├── web/                               # Web 应用
│   ├── backend/                       # FastAPI 后端
│   └── frontend/                      # Vue 前端
│
├── examples/                          # 示例代码
├── scripts/                           # 一次性脚本（新增）
│
├── logs/                              # 日志文件
├── .venv/                             # Python 虚拟环境
└── .git/                              # Git 仓库
```

## 注意事项

1. **不要删除 `examples/` 目录** - 虽然里面有示例，但可能被文档引用
2. **保留 `config.ini`** - 这是运行时配置，不要删
3. **保留 `requirments.txt`** - 这是依赖列表
4. **不要改变 `core/` 的结构** - 这是核心业务逻辑，改了会导致导入路径错误
5. **不要改变 `web/` 的结构** - 这是前后端分离的关键
6. **新增的 `knowledge_versions/`、`feedback_data/`、`audit_logs/` 目录会自动创建** - 不需要手动创建

## 执行步骤

如果你同意这个方案，我会按这个顺序执行：

1. 创建 `scripts/` 目录结构
2. 移动所有一次性脚本到 `scripts/`
3. 删除不必要的目录
4. 删除历史文档
5. 验证所有导入路径是否正确
6. 生成新的 `PROJECT_STRUCTURE.md` 说明

这样做的好处：
- 项目根目录更清晰
- 核心业务逻辑和工具脚本分离
- 便于维护和扩展
- 不会破坏现有的导入路径和运行逻辑
