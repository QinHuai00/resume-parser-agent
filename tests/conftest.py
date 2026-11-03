"""共享测试夹具：一个「干净」的模型输出，供各测试改写。"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def tmp_path():
    """把临时目录放到仓库内，兼容限制严格的宿主环境（系统 TEMP 可能不可写）。"""
    base = REPO_ROOT / "out" / "test_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"case_{uuid.uuid4().hex[:8]}"
    path.mkdir()  # 不用 tempfile.mkdtemp：它建出来的目录在某些沙箱里不可写
    yield path
    shutil.rmtree(path, ignore_errors=True)


SAMPLE_TEXT = """姓名：张伟
手机：13812345678    邮箱：zhangwei01@example.com
期望城市：深圳    工作年限：3
教育背景：
2016.09 - 2020.06 华南理工大学 软件工程 本科
专业技能：Python、FastAPI、MySQL
工作经历：
2020.07 - 2023.12 云启科技 后端开发工程师
- 负责订单服务重构，P99 从 800ms 降到 210ms。
"""

GOOD_RESULT = {
    "profile": {
        "name": "张伟",
        "phone": "13812345678",
        "email": "zhangwei01@example.com",
        "city": "深圳",
        "years_of_experience": 3.0,
        "education": [
            {"school": "华南理工大学", "major": "软件工程", "degree": "本科", "start": "2016.09", "end": "2020.06"}
        ],
        "skills": ["Python", "FastAPI", "MySQL"],
        "experiences": [
            {"company": "云启科技", "title": "后端开发工程师", "start": "2020.07", "end": "2023.12",
             "highlights": ["负责订单服务重构，P99 从 800ms 降到 210ms。"]}
        ],
        "projects": [],
    },
    "evidence": {
        "name": "姓名：张伟",
        "phone": "手机：13812345678",
        "email": "邮箱：zhangwei01@example.com",
        "city": "期望城市：深圳",
        "years_of_experience": "工作年限：3",
        "education.0.school": "华南理工大学",
        "education.0.major": "软件工程",
        "education.0.degree": "本科",
        "experiences.0.company": "云启科技",
    },
}


def good_json() -> str:
    return json.dumps(GOOD_RESULT, ensure_ascii=False)


@pytest.fixture()
def sample_text() -> str:
    return SAMPLE_TEXT


@pytest.fixture()
def good_result() -> dict:
    return json.loads(json.dumps(GOOD_RESULT))