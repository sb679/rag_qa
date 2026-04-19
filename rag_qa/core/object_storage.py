# -*- coding: utf-8 -*-
import os
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from base import Config, logger


def _split_s3_uri(uri: str) -> Tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"invalid s3 uri: {uri}")
    rest = uri[5:]
    if "/" not in rest:
        return rest, ""
    bucket, key = rest.split("/", 1)
    return bucket, key


class LocalObjectStorage:
    backend = "local"

    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def build_key(self, source: str, file_id: str, original_name: str) -> str:
        return f"{source}/{file_id}__{original_name}"

    def put_bytes(self, source: str, file_id: str, original_name: str, content: bytes) -> str:
        rel_key = self.build_key(source, file_id, original_name)
        file_path = self.root_dir / rel_key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)
        return str(file_path)

    def get_bytes(self, uri: str) -> bytes:
        file_path = Path(uri)
        with open(file_path, "rb") as f:
            return f.read()

    def delete_uri(self, uri: str) -> bool:
        file_path = Path(uri)
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
            return True
        return False


class MinioObjectStorage:
    backend = "minio"

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool):
        try:
            from minio import Minio
        except ImportError as e:
            raise RuntimeError("minio package not installed, run pip install minio") from e

        self.bucket = bucket
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)
            logger.info(f"MinIO bucket created: {bucket}")

    def build_key(self, source: str, file_id: str, original_name: str) -> str:
        return f"{source}/{file_id}__{original_name}"

    def put_bytes(self, source: str, file_id: str, original_name: str, content: bytes) -> str:
        object_key = self.build_key(source, file_id, original_name)
        stream = BytesIO(content)
        self.client.put_object(
            bucket_name=self.bucket,
            object_name=object_key,
            data=stream,
            length=len(content),
            content_type="application/octet-stream",
        )
        return f"s3://{self.bucket}/{object_key}"

    def get_bytes(self, uri: str) -> bytes:
        bucket, key = _split_s3_uri(uri)
        response = self.client.get_object(bucket_name=bucket, object_name=key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete_uri(self, uri: str) -> bool:
        bucket, key = _split_s3_uri(uri)
        self.client.remove_object(bucket_name=bucket, object_name=key)
        return True


_storage_instance = None


def get_object_storage():
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    cfg = Config()
    backend = (cfg.STORAGE_BACKEND or "local").strip().lower()
    if backend == "minio":
        _storage_instance = MinioObjectStorage(
            endpoint=cfg.MINIO_ENDPOINT,
            access_key=cfg.MINIO_ACCESS_KEY,
            secret_key=cfg.MINIO_SECRET_KEY,
            bucket=cfg.MINIO_BUCKET,
            secure=cfg.MINIO_SECURE,
        )
    else:
        _storage_instance = LocalObjectStorage(cfg.STORAGE_LOCAL_ROOT)

    logger.info(f"Object storage backend: {_storage_instance.backend}")
    return _storage_instance
