# Medical Import

现在项目已经支持第一条官方医学文档批量导入链路：`MedlinePlus XML`。
现在也支持第二条中文官方链路：`国家卫健委 PDF 白名单`。

## 用法

只下载并生成 Markdown：

```powershell
.\venv\Scripts\python.exe project\import_medical_sources.py --source medlineplus --limit 50
```

下载后直接入库：

```powershell
.\venv\Scripts\python.exe project\import_medical_sources.py --source medlineplus --limit 50 --index
```

下载国家卫健委白名单 PDF 并转成 Markdown：

```powershell
.\venv\Scripts\python.exe project\import_medical_sources.py --source nhc --limit 3
```

下载国家卫健委白名单 PDF 后直接入库：

```powershell
.\venv\Scripts\python.exe project\import_medical_sources.py --source nhc --limit 3 --index
```

使用自定义白名单 manifest：

```powershell
.\venv\Scripts\python.exe project\import_medical_sources.py --source nhc --manifest .\my_nhc_manifest.json --limit 10
```

覆盖已存在的 Markdown：

```powershell
.\venv\Scripts\python.exe project\import_medical_sources.py --source medlineplus --limit 50 --overwrite
```

## 当前范围

- 已支持：
  - `MedlinePlus XML` 官方批量源
  - `国家卫健委 PDF` 白名单导入
- 已具备：
  - 自动发现最新 XML 压缩包链接
  - XML 解析
  - HTML 摘要转 Markdown
  - 国家卫健委官方 PDF 白名单 manifest
  - PDF 下载与 Markdown 转换
  - 写入本地 `markdown_docs/`
  - 可选直接索引进知识库

## 后续建议

下一步可以继续扩展：

1. `WHO Health Topics` HTML 抓取器
2. `WHO Health Topics` HTML 抓取器
3. 文档 manifest 与抓取时间记录
4. “患者教育 / 临床指南 / 研究补充” 分层索引策略
