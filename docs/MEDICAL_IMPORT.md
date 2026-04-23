# Medical Import

现在项目已经支持第一条官方医学文档批量导入链路：`MedlinePlus XML`。
现在也支持第二条中文官方链路：`国家卫健委 PDF 白名单`。
现在还支持第三条公共卫生链路：`WHO Fact Sheets 白名单`。

## 用法

现在除了命令行，你也可以直接在 Documents 页通过 `Import Official Docs` 按钮导入官方资料。

Documents 页的本地上传支持：

- 默认支持：Markdown、PDF、TXT、HTML
- 安装可选依赖后支持：DOCX、PPTX、XLSX 等 `unstructured` 可解析格式

安装可选多格式解析依赖：

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-unstructured.txt
```

实现策略是：PDF 继续优先使用项目已有的 PyMuPDF / OCR 回退链路；其他办公文档格式走 `unstructured` 解析成 Markdown，再进入统一的知识库同步、hash 比对和索引更新流程。

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

下载 WHO 白名单主题页：

```powershell
.\venv\Scripts\python.exe project\import_medical_sources.py --source who --limit 3
```

下载 WHO 白名单主题页并直接入库：

```powershell
.\venv\Scripts\python.exe project\import_medical_sources.py --source who --limit 3 --index
```

覆盖已存在的 Markdown：

```powershell
.\venv\Scripts\python.exe project\import_medical_sources.py --source medlineplus --limit 50 --overwrite
```

## 当前范围

- 已支持：
  - `MedlinePlus XML` 官方批量源
  - `国家卫健委 PDF` 白名单导入
  - `WHO Fact Sheets` 白名单导入
  - 本地 Markdown / PDF / TXT / HTML 上传
  - 可选 `unstructured` 多格式解析
- 已具备：
  - 自动发现最新 XML 压缩包链接
  - XML 解析
  - HTML 摘要转 Markdown
  - 国家卫健委官方 PDF 白名单 manifest
  - PDF 下载与 Markdown 转换
  - WHO 官方主题页白名单 manifest
  - WHO 页面正文抽取与 Markdown 转换
  - 写入本地 `markdown_docs/`
  - 可选直接索引进知识库
  - 同名文档按 source_key + content_hash 做新增、更新、未变化判断

## 后续建议

下一步可以继续扩展：

1. 文档 manifest 与抓取时间记录
2. “患者教育 / 临床指南 / 研究补充” 分层索引策略
3. 更强的 PDF 清洗和 OCR 兜底
