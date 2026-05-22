from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEACHER_DEMO_DIR = ROOT / "teacher_demo_experiments"

CHUNKING_EXPERIMENT_DIR = TEACHER_DEMO_DIR / "01_chunking_performance"
STRATEGY_SELECTOR_EXPERIMENT_DIR = TEACHER_DEMO_DIR / "02_strategy_selector"
QUERY_CLASSIFIER_EXPERIMENT_DIR = TEACHER_DEMO_DIR / "03_query_classifier"
RAGAS_DATASET_EXPERIMENT_DIR = TEACHER_DEMO_DIR / "04_ragas_dataset_quality"
RAGAS_EVALUATION_EXPERIMENT_DIR = TEACHER_DEMO_DIR / "05_ragas_evaluation"