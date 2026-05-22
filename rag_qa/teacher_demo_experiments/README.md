# 教师演示实验总览

本目录用于给老师集中演示项目里的核心实验，目标是做到三件事：

1. 每类实验都有单独入口，避免再去根目录里找脚本。
2. 实验数据、结果、图表集中放在对应主题下，便于现场展示。
3. 已有 Python 实验脚本的输出路径统一指向本目录。

## 建议演示顺序

### 01_chunking_performance
- 主题：分块相关实验，包含 K/M 检索参数基准与父子块大小内部对比
- 启动入口：
  - launchers/run_chunking_benchmark.ps1
  - launchers/run_chunk_config_internal.ps1
- 重点看：
  - artifacts/benchmark_km_report.json
  - artifacts/chunk_config_internal/

### 02_strategy_selector
- 主题：检索策略分类器分类效果
- 启动入口：
  - launchers/build_strategy_dataset.ps1
  - launchers/train_strategy_classifier.ps1
  - launchers/evaluate_strategy_selector.ps1
- 重点看：artifacts/reports、artifacts/training_results_v2、artifacts/illustrative_only

### 03_query_classifier
- 主题：通用知识 / 专业知识分类效果
- 启动入口：
  - launchers/build_query_classifier_dataset.ps1
  - launchers/train_query_classifier.ps1
- 重点看：artifacts/query_classifier_dataset_v2.summary.json、model_snapshot

### 04_ragas_dataset_quality
- 主题：RAGAS 测试数据集生成质量
- 启动入口：launchers/build_ragas_datasets.ps1
- 重点看：artifacts/datasets、artifacts/generated_datasets、artifacts/results、artifacts/plots

### 05_ragas_evaluation
- 主题：RAGAS 效果评估
- 启动入口：launchers/run_official_ragas_eval.ps1
- 重点看：artifacts/official_ragas_eval

## 首次整理

如果老的数据、图片、结果还散落在 rag_qa 根目录，请先运行：

- migrate_artifacts.ps1

运行后会把已有产物复制到本目录下的对应主题中，原始文件会保留，适合演示前安全整理。

## 说明

- 本目录只负责演示组织，不替代源码目录。
- 若某个主题下 artifacts 为空，说明该实验入口已就位，但历史产物尚未生成或尚未整理进来。