"""Cloudflare R2 (S3兼容)上传工具。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError


@dataclass(slots=True)
class R2Config:
    """R2客户端配置。"""

    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    region_name: str = "auto"
    public_base_url: Optional[str] = None


class R2StorageError(RuntimeError):
    """上传失败时抛出。"""


class R2StorageClient:
    """简单的异步R2上传封装。"""

    def __init__(self, config: R2Config):
        self._config = config
        session = boto3.session.Session()
        self._client = session.client(
            "s3",
            endpoint_url=config.endpoint_url,
            aws_access_key_id=config.access_key_id,
            aws_secret_access_key=config.secret_access_key,
            region_name=config.region_name,
            config=BotoConfig(signature_version="s3v4"),
        )

    @property
    def bucket(self) -> str:
        return self._config.bucket

    @property
    def public_base_url(self) -> Optional[str]:
        return self._config.public_base_url.rstrip("/") if self._config.public_base_url else None

    async def upload_bytes(self, *, key: str, data: bytes, content_type: str) -> str:
        """上传二进制数据并返回可访问URL（如配置)."""

        try:
            await asyncio.to_thread(
                self._client.put_object,
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except (ClientError, BotoCoreError) as exc:
            raise R2StorageError(f"R2上传失败: {exc}") from exc

        return self.build_public_url(key)

    def build_public_url(self, key: str) -> str:
        """根据配置拼接公开访问URL。"""
        if not self.public_base_url:
            # 若未配置公开域名，退回R2默认路径
            return f"https://{self.bucket}.r2.cloudflarestorage.com/{key}"
        base = self.public_base_url.rstrip("/")
        return f"{base}/{key.lstrip('/')}"
