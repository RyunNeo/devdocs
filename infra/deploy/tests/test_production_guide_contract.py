from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
GUIDE = ROOT / "infra/deploy/README-production.md"


def _guide():
    return GUIDE.read_text(encoding="utf-8")


def test_production_guide_covers_baota_first_deploy():
    guide = _guide()
    for phrase in (
        "常规创建",
        "compose.production.yml",
        "production.env.example",
        "GitHub",
        "本机构建",
        "不从远端仓库拉取应用镜像",
        "SILICONFLOW_API_KEY",
        "http://47.106.71.228",
        "健康",
    ):
        assert phrase in guide
    assert "IMAGE_TAG" not in guide
    assert "Publish container images" not in guide


def test_guide_requires_repository_file_source_for_relative_build_context():
    guide = _guide()
    assert "GitHub 仓库" in guide
    assert "选择 **文件**" in guide
    assert "infra/deploy/compose.production.yml" in guide
    assert "相对构建上下文" in guide
    assert "编辑" in guide and "不适合" in guide


def test_guide_explains_registry_network_and_memory_prerequisites():
    guide = _guide()
    for phrase in (
        "pgvector/pgvector:pg16",
        "python:3.14-slim",
        "node:22-slim",
        "Registry 网络",
        "npm",
        "PyPI",
        "2 GiB",
        "OOM",
    ):
        assert phrase in guide


def test_production_guide_warns_about_http_and_security_group():
    guide = _guide()
    assert "/32" in guide
    assert "明文 HTTP" in guide and "没有传输加密保护" in guide
    assert "COOKIE_SECURE" in guide
    assert "不要" in guide and "5432" in guide and "8000" in guide


def test_production_guide_documents_backup_and_rollback():
    guide = _guide()
    assert "磁盘快照" in guide
    assert "恢复磁盘快照" in guide
    assert "源码提交" in guide
    assert "删除数据卷" in guide


def test_production_guide_never_embeds_real_secrets():
    guide = _guide()
    assert "production.env.example" in guide
    assert re.search(r"POSTGRES_PASSWORD\s*=\s*(?!REPLACE_WITH)[^\s]+", guide) is None
    assert re.search(r"sk-[A-Za-z0-9]{20,}", guide) is None
    assert "docker compose down -v" not in guide
