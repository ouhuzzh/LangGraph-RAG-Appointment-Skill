# QA Evaluation

项目现在带了一套可重复运行的真实问答样本评估入口，用来检查检索层是否把问题路由到合适的资料来源，并生成可读的质量评分报表。

## 默认样本集

默认样本文件在：

- `tests/fixtures/qa_eval_samples.json`

当前样本已经扩成 transcript 风格的最小回归集，覆盖：

- 患者教育
- 公共卫生
- 临床指南
- 多轮 follow-up 追问
- 无证据 / 无匹配场景

每条样本除了最终问题，还可以包含：

- `transcript_turns`
- `conversation_summary`
- `category`
- `difficulty`
- `tags`

## 运行评估

在已有知识库索引的前提下运行：

```powershell
.\venv\Scripts\python.exe project\benchmarks\evaluate_qa_quality.py
```

输出会包含：

- `avg_retrieval_score`
- `avg_overall_score`
- `clarification_rate`
- `source_type_hit_rate`
- `by_category / by_difficulty / by_top_source_type`
- 低分样本列表
- 每条样本的首条来源类型与 transcript 预览
- 命中的检索关键词

如果你想导出 Markdown 报表：

```powershell
.\venv\Scripts\python.exe project\benchmarks\evaluate_qa_quality.py --markdown --output reports\qa_eval_report.md
```

如果你想直接拿 JSON 结果做后续分析：

```powershell
.\venv\Scripts\python.exe project\benchmarks\evaluate_qa_quality.py --json --output reports\qa_eval_report.json
```

## 可选答案评分

如果你想评估一批现成答案文本，可以提供一个 JSON 文件，格式为：

```json
{
  "patient-hypertension-symptoms": "高血压有时没有明显症状，但也可能出现头痛头晕，平时建议低盐饮食并定期复诊。"
}
```

然后运行：

```powershell
.\venv\Scripts\python.exe project\benchmarks\evaluate_qa_quality.py --answers answers.json
```

项目也自带了一份真实风格答案夹具：

- `tests/fixtures/qa_eval_answers.json`

可以直接这样跑：

```powershell
.\venv\Scripts\python.exe project\benchmarks\evaluate_qa_quality.py --fixture-answers --markdown --output reports\qa_eval_answers_report.md
```

这时报告会额外计算：

- `avg_answer_score`
- `avg_safety_score`
- `avg_tone_score`
- `patient_friendly_rate`
- `no_evidence_answer_rate`
- 是否出现不必要澄清
- 安全提示关键词覆盖情况
- 患者友好表达命中情况
- 答案关键词覆盖情况
- 低分答案样本列表

## 设计目标

这套评估优先回答三个问题：

1. 问题是否命中了对的资料层
2. 检索片段里是否带回了关键事实
3. 如果提供答案文本，答案是否覆盖关键点且没有过度澄清
4. 哪一类 transcript 最容易掉分，方便后续针对性补样本或调检索
