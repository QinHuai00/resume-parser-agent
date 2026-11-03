# 评测结果（真实运行，2026-11-03）

命令：

```bash
python -m resume_agent.cli eval --provider mock --corrupt-rate 0.35 --max-repairs 1
```

`mock` 模式的含义（重要，别误读）：用一个**注入故障的模拟模型**替代真实大模型，
按固定种子对同一批 12 份合成简历注入三类真实会发生的错误——JSON 被截断、
字段类型不合法（年限写成「3 年」）、字段多吐 / 幻觉手机号。
它的作用是**证明修复环真的干活**，而不是证明模型有多聪明。
真实模型的数字要配 key 自己跑（`--provider openai`），本仓库不预设。

## 1. 有修复环（max_repairs=1，注入率 35%）

| 指标 | 数值 |
| --- | --- |
| 样本数 | 12 |
| 结构合法率 | 100.0% |
| 触发修复的比例 | 8.3% |
| 平均修复轮次 | 0.08 |
| 幻觉字段被丢弃 | 3 个 |
| 技能集合 F1 | 1.000 |
| name / email / city / years / education.school | 100.0% |
| phone | 75.0% |

## 2. 基线：关掉修复（max_repairs=0，注入率 35%）

| 指标 | 数值 |
| --- | --- |
| 结构合法率 | 91.7% |
| 技能集合 F1 | 0.917 |
| name / email / city / years / education.school | 91.7% |
| phone | 66.7% |

## 3. 极端情况：100% 脏输出（max_repairs=1）

| 指标 | 数值 |
| --- | --- |
| 结构合法率 | 100.0% |
| 触发修复的比例 | 50.0% |
| 平均修复轮次 | 0.50 |
| 幻觉字段被丢弃 | 6 个 |
| phone 准确率 | 50.0% |

## 怎么读这三张表

1. **结构合法率 91.7% → 100%**：修复环把「模型吐了坏 JSON / 字段类型错」这一类**可修复**故障全部救回来，
   代价是平均每份多 0.08 次模型调用。
2. **phone 准确率只有 75%（甚至 50%）不是 bug，是取舍**：模拟模型会编一个不存在的手机号，
   证据过滤发现「原文里找不到 13900000000」就把它置空。宁可为 null，也不入库一条假号码。
   —— 这正是抽取类任务的核心矛盾：**召回 vs 可信**，这里明确选可信。
3. **为什么修复只做 1 轮**：100% 脏输入下触发率 50%、平均轮次 0.5，说明修复请求本身是少数派；
   再叠加第 2 轮收益很小而延迟成本线性上涨，所以默认 `max_repairs=1`，可通过参数改。

## 复现

```bash
python eval/make_dataset.py
python -m resume_agent.cli eval --provider mock --corrupt-rate 0.35 --max-repairs 1
python -m resume_agent.cli eval --provider mock --corrupt-rate 0.35 --max-repairs 0
python -m resume_agent.cli eval --provider mock --corrupt-rate 1.0  --max-repairs 1
```