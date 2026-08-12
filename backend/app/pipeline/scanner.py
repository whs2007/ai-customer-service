"""恶意文件扫描（可插拔，08 §8 上传安全）。

默认关闭（SCAN_ENABLED=false）。接入点：
- 本地 ClamAV：安装 clamav 后配置 `SCAN_CMD=clamdscan`，本模块调用子进程扫描；
- 外部 API：实现 `scan_file` 调用安全厂商接口即可。
命中返回 ok=False + reason。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

# 扩展名 → 期望的文件头（内容嗅探，08 §8 拒绝伪装扩展名）
MAGIC_PREFIXES: dict[str, tuple[bytes, ...]] = {
    ".xlsx": (b"PK\x03\x04",),
    ".docx": (b"PK\x03\x04",),
    ".pdf": (b"%PDF-",),
}
TEXT_EXTENSIONS = {".csv", ".md", ".txt"}


def sniff_content(ext: str, content: bytes) -> bool:
    """按扩展名校验文件头：二进制格式校验 magic，文本格式拒绝 NUL（二进制伪装）。"""
    head = content[:512]
    if ext in MAGIC_PREFIXES:
        return head.startswith(MAGIC_PREFIXES[ext])
    if ext in TEXT_EXTENSIONS:
        return b"\x00" not in head
    return True


@dataclass
class ScanResult:
    ok: bool
    reason: str = ""


def scan_file(path: str | Path, file_type: str) -> ScanResult:
    """扫描上传文件。SCAN_ENABLED=false 时直接放行（可插拔默认关闭）。"""
    settings = get_settings()
    if not settings.scan_enabled:
        return ScanResult(ok=True, reason="scanner disabled")
    # 占位接入点：本地 ClamAV（clamdscan）示例；外部 API 在此扩展
    try:
        result = subprocess.run(
            ["clamdscan", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        infected = "FOUND" in (result.stdout + result.stderr).upper()
        if infected:
            return ScanResult(ok=False, reason="疑似恶意文件（病毒扫描命中）")
        return ScanResult(ok=True)
    except FileNotFoundError:
        # clamdscan 未安装：保守拒绝或放行由部署方决定；此处放行并记录
        return ScanResult(ok=True, reason="scanner not installed, skipped")
    except Exception as exc:  # noqa: BLE001
        return ScanResult(ok=False, reason=f"扫描失败：{exc}")
