# Medical Import

现在项目已经支持第一条官方医学文档批量导入链路：`MedlinePlus XML`。

## 用法

只下载并生成 Markdown：

```powershell
.\venv\Scripts\python.exe project\import_medical_sources.py --source medlineplus --limit 50
```

下载后直接入库：

```powershell
.\venv\Scripts\python.exe project\import_medical_sources.py --source medlineplus --limit 50 --index
```

覆盖已存在的 Markdown：

```powershell
.\venv\Scripts\python.exe project\import_medical_sources.py --source medlineplus --limit 50 --overwrite
```

## 当前范围

- 已支持：
  - `MedlinePlus XML` 官方批量源
- 已具备：
  - 自动发现最新 XML 压缩包链接
  - XML 解析
  - HTML 摘要转 Markdown
  - 写入本地 `markdown_docs/`
  - 可选直接索引进知识库

## 后续建议

下一步可以继续扩展：

1. `WHO Health Topics` HTML 抓取器
2. `国家卫健委` PDF 白名单下载与清洗
3. 文档 manifest 与抓取时间记录
4. “患者教育 / 临床指南 / 研究补充” 分层索引策略
