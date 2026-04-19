# -*- coding:utf-8 -*-
import ast
import configparser
import os

current_file_path = os.path.abspath(__file__)
current_dir_path = os.path.dirname(current_file_path)
project_root = os.path.dirname(current_dir_path)
config_file_path = os.path.join(project_root, 'config.ini')


class Config:
    def __init__(self, config_file=config_file_path):
        self.config = configparser.ConfigParser()
        self.config.read(config_file, encoding='utf-8')

        self.MYSQL_HOST = self._get_str('EDURAG_MYSQL_HOST', 'mysql', 'host', 'localhost')
        self.MYSQL_PORT = self._get_int('EDURAG_MYSQL_PORT', 'mysql', 'port', 3306)
        self.MYSQL_USER = self._get_str('EDURAG_MYSQL_USER', 'mysql', 'user', 'root')
        self.MYSQL_PASSWORD = self._get_str('EDURAG_MYSQL_PASSWORD', 'mysql', 'password', 'demo-mysql-password')
        self.MYSQL_DATABASE = self._get_str('EDURAG_MYSQL_DATABASE', 'mysql', 'database', 'subjects_kg')

        self.REDIS_HOST = self._get_str('EDURAG_REDIS_HOST', 'redis', 'host', 'localhost')
        self.REDIS_PORT = self._get_int('EDURAG_REDIS_PORT', 'redis', 'port', 6379)
        self.REDIS_PASSWORD = self._get_str('EDURAG_REDIS_PASSWORD', 'redis', 'password', 'demo-redis-password')
        self.REDIS_DB = self._get_int('EDURAG_REDIS_DB', 'redis', 'db', 0)

        self.MILVUS_HOST = self._get_str('EDURAG_MILVUS_HOST', 'milvus', 'host', 'localhost')
        self.MILVUS_PORT = self._get_str('EDURAG_MILVUS_PORT', 'milvus', 'port', '19530')
        self.MILVUS_DATABASE_NAME = self._get_str('EDURAG_MILVUS_DATABASE_NAME', 'milvus', 'database_name', 'itcast')
        self.MILVUS_COLLECTION_NAME = self._get_str('EDURAG_MILVUS_COLLECTION_NAME', 'milvus', 'collection_name', 'edurag_final')

        self.LLM_MODEL = self._get_str('EDURAG_LLM_MODEL', 'llm', 'model', 'qwen-plus')
        self.DASHSCOPE_API_KEY = self._get_str('EDURAG_DASHSCOPE_API_KEY', 'llm', 'dashscope_api_key', 'demo-key-change-me')
        self.DASHSCOPE_BASE_URL = self._get_str(
            'EDURAG_DASHSCOPE_BASE_URL',
            'llm',
            'dashscope_base_url',
            'https://dashscope.aliyuncs.com/compatible-mode/v1',
        )
        self.DEEPSEEK_API_KEY = self._get_str('EDURAG_DEEPSEEK_API_KEY', 'llm', 'deepseek_api_key', 'demo-key-change-me')
        self.DEEPSEEK_BASE_URL = self._get_str('EDURAG_DEEPSEEK_BASE_URL', 'llm', 'deepseek_base_url', 'https://api.deepseek.com/v1')

        self.PARENT_CHUNK_SIZE = self._get_int('EDURAG_PARENT_CHUNK_SIZE', 'retrieval', 'parent_chunk_size', 1200)
        self.CHILD_CHUNK_SIZE = self._get_int('EDURAG_CHILD_CHUNK_SIZE', 'retrieval', 'child_chunk_size', 300)
        self.CHUNK_OVERLAP = self._get_int('EDURAG_CHUNK_OVERLAP', 'retrieval', 'chunk_overlap', 50)
        self.CHUNKING_MODE = self._get_str('EDURAG_CHUNKING_MODE', 'retrieval', 'chunking_mode', 'rule').strip().lower()
        self.CHUNKING_MODE_BY_SOURCE = self._get_mapping(
            'EDURAG_CHUNKING_MODE_BY_SOURCE',
            'retrieval',
            'chunking_mode_by_source',
            {'default': self.CHUNKING_MODE},
        )
        self.STRUCT_MIN_PARAGRAPH_CHARS = self._get_int(
            'EDURAG_STRUCT_MIN_PARAGRAPH_CHARS',
            'retrieval',
            'struct_min_paragraph_chars',
            80,
        )
        self.SEMANTIC_SIM_THRESHOLD = self._get_float(
            'EDURAG_SEMANTIC_SIM_THRESHOLD',
            'retrieval',
            'semantic_sim_threshold',
            0.74,
        )
        self.SEMANTIC_MIN_CHUNK_SIZE = self._get_int(
            'EDURAG_SEMANTIC_MIN_CHUNK_SIZE',
            'retrieval',
            'semantic_min_chunk_size',
            220,
        )
        self.SEMANTIC_MAX_CHUNK_SIZE = self._get_int(
            'EDURAG_SEMANTIC_MAX_CHUNK_SIZE',
            'retrieval',
            'semantic_max_chunk_size',
            520,
        )
        self.SEMANTIC_MODEL_PATH = self._get_str(
            'EDURAG_SEMANTIC_MODEL_PATH',
            'retrieval',
            'semantic_model_path',
            os.path.join(project_root, 'models', 'bge-m3'),
        )
        self.GRAPH_PARENT_CHUNK_SIZE = self._get_int(
            'EDURAG_GRAPH_PARENT_CHUNK_SIZE',
            'graphrag',
            'graph_parent_chunk_size',
            1600,
        )
        self.GRAPH_CHILD_CHUNK_SIZE = self._get_int(
            'EDURAG_GRAPH_CHILD_CHUNK_SIZE',
            'graphrag',
            'graph_child_chunk_size',
            500,
        )
        self.GRAPH_CHUNK_OVERLAP = self._get_int(
            'EDURAG_GRAPH_CHUNK_OVERLAP',
            'graphrag',
            'graph_chunk_overlap',
            100,
        )

        self.OCR_ENABLE = self._get_bool('EDURAG_OCR_ENABLE', 'ocr', 'enable', True)
        self.PDF_IMAGE_OCR_ENABLE = self._get_bool(
            'EDURAG_PDF_IMAGE_OCR_ENABLE',
            'ocr',
            'pdf_image_ocr_enable',
            True,
        )
        self.PDF_OCR_MIN_IMAGE_WIDTH_RATIO = self._get_float(
            'EDURAG_PDF_OCR_MIN_IMAGE_WIDTH_RATIO',
            'ocr',
            'pdf_ocr_min_image_width_ratio',
            0.3,
        )
        self.PDF_OCR_MIN_IMAGE_HEIGHT_RATIO = self._get_float(
            'EDURAG_PDF_OCR_MIN_IMAGE_HEIGHT_RATIO',
            'ocr',
            'pdf_ocr_min_image_height_ratio',
            0.3,
        )
        self.DOC_IMAGE_OCR_ENABLE = self._get_bool(
            'EDURAG_DOC_IMAGE_OCR_ENABLE',
            'ocr',
            'doc_image_ocr_enable',
            True,
        )
        self.PPT_IMAGE_OCR_ENABLE = self._get_bool(
            'EDURAG_PPT_IMAGE_OCR_ENABLE',
            'ocr',
            'ppt_image_ocr_enable',
            True,
        )
        self.DEDOC_FALLBACK_ENABLE = self._get_bool(
            'EDURAG_DEDOC_FALLBACK_ENABLE',
            'loader_fallback',
            'dedoc_fallback_enable',
            True,
        )
        self.RETRIEVAL_K = self._get_int('EDURAG_RETRIEVAL_K', 'retrieval', 'retrieval_k', 5)
        self.CANDIDATE_M = self._get_int('EDURAG_CANDIDATE_M', 'retrieval', 'candidate_m', 2)

        self.CUSTOMER_SERVICE_PHONE = self._get_str('EDURAG_CUSTOMER_SERVICE_PHONE', 'app', 'customer_service_phone', '400-000-0000')
        self.VALID_SOURCES = self._get_list('EDURAG_VALID_SOURCES', 'app', 'valid_sources', ['mining'])
        self.LOG_FILE = self._get_str('EDURAG_LOG_FILE', 'logger', 'log_file', 'logs/app.log')

        self.JWT_SECRET = self._get_str('EDURAG_JWT_SECRET', 'auth', 'jwt_secret', 'demo-jwt-secret-change-me')
        self.DEFAULT_SUPERVISOR_PASSWORD = self._get_str(
            'EDURAG_DEFAULT_SUPERVISOR_PASSWORD',
            'auth',
            'default_supervisor_password',
            'demo-supervisor-pass-change-me',
        )

        self.STORAGE_BACKEND = self._get_str('EDURAG_STORAGE_BACKEND', 'storage', 'backend', 'local').lower()
        self.STORAGE_LOCAL_ROOT = self._get_str(
            'EDURAG_STORAGE_LOCAL_ROOT',
            'storage',
            'local_root',
            os.path.join(project_root, 'user_data', 'knowledge_files'),
        )
        self.MINIO_ENDPOINT = self._get_str('EDURAG_MINIO_ENDPOINT', 'storage', 'minio_endpoint', '127.0.0.1:9000')
        self.MINIO_ACCESS_KEY = self._get_str('EDURAG_MINIO_ACCESS_KEY', 'storage', 'minio_access_key', 'minioadmin')
        self.MINIO_SECRET_KEY = self._get_str('EDURAG_MINIO_SECRET_KEY', 'storage', 'minio_secret_key', 'minioadmin')
        self.MINIO_BUCKET = self._get_str('EDURAG_MINIO_BUCKET', 'storage', 'minio_bucket', 'edurag-knowledge')
        self.MINIO_SECURE = self._get_bool('EDURAG_MINIO_SECURE', 'storage', 'minio_secure', False)

    def _get_str(self, env_name, section, option, fallback):
        value = os.getenv(env_name)
        if value is not None and value != '':
            return value
        try:
            if not self.config.has_section(section):
                return fallback
            return self.config.get(section, option, fallback=fallback)
        except Exception:
            return fallback

    def _get_int(self, env_name, section, option, fallback):
        value = os.getenv(env_name)
        if value is not None and value != '':
            try:
                return int(value)
            except ValueError:
                return fallback
        try:
            if not self.config.has_section(section):
                return fallback
            return self.config.getint(section, option, fallback=fallback)
        except Exception:
            return fallback

    def _get_bool(self, env_name, section, option, fallback):
        value = os.getenv(env_name)
        if value is not None and value != '':
            return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}
        try:
            if not self.config.has_section(section):
                return fallback
            return self.config.getboolean(section, option, fallback=fallback)
        except Exception:
            return fallback

    def _get_float(self, env_name, section, option, fallback):
        value = os.getenv(env_name)
        if value is not None and value != '':
            try:
                return float(value)
            except ValueError:
                return fallback
        try:
            if not self.config.has_section(section):
                return fallback
            return self.config.getfloat(section, option, fallback=fallback)
        except Exception:
            return fallback

    def _get_mapping(self, env_name, section, option, fallback):
        value = os.getenv(env_name)
        raw = value
        if raw is None or raw == '':
            try:
                if not self.config.has_section(section):
                    return fallback
                raw = self.config.get(section, option, fallback='')
            except Exception:
                return fallback

        if not raw:
            return fallback

        mapping = {}
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, dict):
                return {str(key).strip().lower(): str(val).strip().lower() for key, val in parsed.items()}
        except (ValueError, SyntaxError):
            pass

        for item in str(raw).split(','):
            if ':' not in item:
                continue
            key, val = item.split(':', 1)
            key = key.strip().lower()
            val = val.strip().lower()
            if key and val:
                mapping[key] = val

        return mapping or fallback

    def _get_list(self, env_name, section, option, fallback):
        value = os.getenv(env_name)
        if value:
            return [item.strip() for item in value.split(',') if item.strip()]

        try:
            if not self.config.has_section(section):
                return fallback
            raw = self.config.get(section, option, fallback='')
        except Exception:
            return fallback
        if not raw:
            return fallback

        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except (ValueError, SyntaxError):
            pass

        return [item.strip() for item in raw.split(',') if item.strip()] or fallback


if __name__ == '__main__':
    conf = Config()
    print(conf.CHUNK_OVERLAP)
    print(conf.VALID_SOURCES)
    print(type(conf.VALID_SOURCES))