# Medical Document Sources

这份清单面向 RAG 文档建设，优先选择官方、稳定、可追溯的医学来源，而不是随机抓取论坛或营销站点。

## 建议的首批来源

1. `MedlinePlus`
   - 适合患者教育、疾病基础说明、就诊准备、药物常识。
   - 优点是结构化程度高，官方提供批量 XML。

2. `WHO Health Topics`
   - 适合公共卫生、疾病概览、风险因素、筛查与预防。
   - 适合作为基础健康知识补充。

3. `NICE Guidance`
   - 适合临床路径、指南摘要、管理建议。
   - 更偏专业，适合单独分库或加权较低。

4. `国家卫生健康委`
   - 适合中文诊疗规范、疾病诊疗方案、政策与标准。
   - 适合中文主库，但需要更强的 PDF 清洗。

## 不建议直接混入主知识库的来源

- 随机论文全文
- 医疗商业营销站
- 无发布日期或无机构署名的文章
- 自媒体二次转载

## 推荐分层

- `patient_education`
  - 患者向问答主库，优先使用。
- `clinical_guideline`
  - 医生/专业参考层，回答时需要显式降级为“仅供参考，不替代诊疗”。
- `research_article`
  - 研究补充层，不建议默认参与所有检索。

## 项目内清单

项目里已经提供了一个可导出的官方来源目录：

- [document_source_catalog.py](/D:/nageoffer/agentic-rag-for-dummies/project/core/document_source_catalog.py)

后续可以基于它继续做：

- manifest 驱动的批量下载
- URL 白名单校验
- 抓取时间与来源版本记录
- 中文 PDF 清洗和去噪
