"""生成离线评测集（12 份合成简历 + 逐字段 gold 与 evidence）。

为什么要合成而不是拿真实简历：
- 真实简历涉及个人信息，不能进公开仓库；
- 合成简历可以把「年份/学历/技能组合」做成可控变量，指标才可复现。

运行：
    python eval/make_dataset.py          # 写出 eval/dataset.jsonl
"""
from __future__ import annotations

import json
from pathlib import Path

PERSONAS = [
    # (姓名, 手机, 邮箱, 城市, 年限, 学校, 专业, 学历, 起, 止, 公司, 职位, 技能)
    ("张伟", "13812345678", "zhangwei01@example.com", "深圳", 3, "华南理工大学", "软件工程", "本科",
     "2016.09", "2020.06", "云启科技", "后端开发工程师", ["Python", "FastAPI", "MySQL", "Redis"]),
    ("李娜", "13987654321", "lina02@example.com", "杭州", 1, "杭州电子科技大学", "计算机科学与技术", "本科",
     "2019.09", "2023.06", "数联智能", "算法工程师", ["Python", "PyTorch", "RAG", "LangChain"]),
    ("王强", "13712340987", "wangqiang03@example.com", "成都", 0, "成都信息工程大学", "数据科学", "本科",
     "2020.09", "2024.06", "青柚信息", "数据开发实习生", ["SQL", "Pandas", "Python"]),
    ("刘敏", "13698761234", "liumin04@example.com", "北京", 5, "北京邮电大学", "通信工程", "硕士",
     "2015.09", "2018.06", "北辰网络", "高级后端工程师", ["Go", "Kubernetes", "MySQL", "gRPC"]),
    ("陈晨", "13509871234", "chenchen05@example.com", "上海", 2, "上海大学", "计算机应用", "硕士",
     "2018.09", "2021.06", "临港数据", "大模型应用工程师", ["Python", "LangGraph", "Chroma", "FastAPI"]),
    ("杨帆", "13456782345", "yangfan06@example.com", "广州", 4, "暨南大学", "信息管理", "本科",
     "2014.09", "2018.06", "南沙物流", "Java 开发工程师", ["Java", "Spring Boot", "MySQL"]),
    ("赵磊", "13345678901", "zhaolei07@example.com", "深圳", 6, "中山大学", "计算机科学与技术", "硕士",
     "2013.09", "2016.06", "海翼支付", "架构师", ["Java", "Kafka", "Microservices", "MySQL"]),
    ("周静", "13234567890", "zhoujing08@example.com", "南京", 1, "南京邮电大学", "软件工程", "本科",
     "2019.09", "2023.06", "紫金云", "前端开发工程师", ["TypeScript", "React", "Vite"]),
    ("吴昊", "13123456789", "wuhao09@example.com", "武汉", 2, "华中科技大学", "自动化", "本科",
     "2017.09", "2021.06", "光谷智造", "嵌入式工程师", ["C", "C++", "FreeRTOS", "Python"]),
    ("徐婷", "13012345678", "xuting10@example.com", "西安", 0, "西安电子科技大学", "计算机科学与技术", "本科",
     "2020.09", "2024.06", "秦云软件", "测试开发实习生", ["Python", "pytest", "Selenium"]),
    ("孙浩", "18912345670", "sunhao11@example.com", "苏州", 3, "苏州大学", "软件工程", "本科",
     "2016.09", "2020.06", "吴中科技", "全栈工程师", ["Python", "FastAPI", "Vue", "MySQL"]),
    ("马丽", "18812345671", "mali12@example.com", "重庆", 2, "重庆大学", "统计学", "硕士",
     "2018.09", "2021.06", "两江数科", "数据分析师", ["Python", "SQL", "Tableau"]),
]


def build(item: tuple) -> dict:
    (name, phone, email, city, years, school, major, degree,
     start, end, company, title, skills) = item

    skills_line = "、".join(skills)
    text = f"""姓名：{name}
手机：{phone}    邮箱：{email}
期望城市：{city}    工作年限：{years}
教育背景：
{start} - {end} {school} {major} {degree}
专业技能：{skills_line}
工作经历：
{start} - 至今 {company} {title}
- 负责核心业务模块的设计与开发，接口 QPS 峰值 1200。
- 主导一次性能优化，接口 P99 从 800ms 降到 210ms。
项目经历：
内部知识库问答系统
- 基于 RAG 搭建文档问答，覆盖 3000 份内部文档。
"""

    gold = {
        "profile": {
            "name": name,
            "phone": phone,
            "email": email,
            "city": city,
            "years_of_experience": float(years),
            "education": [
                {"school": school, "major": major, "degree": degree, "start": start, "end": end}
            ],
            "skills": skills,
            "experiences": [
                {"company": company, "title": title, "start": start, "end": None,
                 "highlights": ["负责核心业务模块的设计与开发，接口 QPS 峰值 1200。"]}
            ],
            "projects": [
                {"name": "内部知识库问答系统", "role": None, "tech": ["RAG"], "description": None}
            ],
        },
        "evidence": {
            "name": f"姓名：{name}",
            "phone": f"手机：{phone}",
            "email": f"邮箱：{email}",
            "city": f"期望城市：{city}",
            "years_of_experience": f"工作年限：{years}",
            "education.0.school": school,
            "education.0.major": major,
            "education.0.degree": degree,
            "experiences.0.company": company,
        },
    }
    return {"id": f"CV-{item[0]}-{item[1][-4:]}", "text": text, "gold": gold}


def main() -> None:
    out = Path(__file__).with_name("dataset.jsonl")
    rows = [build(p) for p in PERSONAS]
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} samples -> {out}")


if __name__ == "__main__":
    main()