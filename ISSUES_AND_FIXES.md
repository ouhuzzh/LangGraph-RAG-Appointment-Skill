# Issues And Fixes

## Resolved / Verified

- `resolved` 预约确认与取消确认已经升级为纯对话式半受控流程，只有明确确认语义才会真正落库。
- `resolved` `pending_action_type`、`pending_action_payload`、`pending_confirmation_id`、`pending_candidates` 已经进入图状态并参与会话恢复。
- `resolved` 默认用户视图不再直接暴露内部诊断信息，诊断输出只保留给调试场景。
- `resolved` 知识库启动改成轻启动，支持后台补建、状态展示和官方文档导入。
- `resolved` 预约服务的基础幂等、重复取消、重复确认、无号源等边界已经补回归测试。
- `resolved` 图内 `intent_router` 现在是正式业务路由单一真源，`ChatInterface` 不再前置决定预约/取消/分诊等业务流转。
- `resolved` `rewrite_query -> agent` 已经补上 `recent_context` 传递，follow-up 不再只能依赖长期 summary。
- `resolved` `clarification_target` 已经进入会话恢复链路，刷新后补充信息会继续回到原节点。
- `resolved` agent 子图对 repeated `NO_EVIDENCE` 和 repeated search query 增加了 fallback 保护，减少低价值循环。

## Current Priorities

### P0

- `resolved` 普通医学问题和上下文追问现在会先走规则判定，能明显减少不必要的 `intent_router` LLM 调用。
- `resolved` `rewrite_query()` 不再删除全部非系统消息，而是只裁掉更早历史，保留最近两轮对话和当前消息。
- `resolved` mixed intent 的优先级已重排，像“预约前高血压药还要不要吃”会优先走 `medical_rag`，显式“取消刚才那个预约”才优先走取消链路。
- `resolved` 检索现在支持 `pgvector + tsvector` 混合召回、RRF 融合、query-aware source layering，并对检索写入 `retrieval_logs`。
- `resolved` 无检索结果时不再返回裸哨兵字符串，而是明确的 `NO_EVIDENCE` 提示；提示词也同步收紧为“没有证据就不要补全”。

### P1

- `resolved` 预约/取消结构化工具调用现在优先产出标准化 `date=YYYY-MM-DD` 与 `time_slot=morning|afternoon|evening`，后端保留兼容归一化兜底。
- `resolved` `last_appointment_no` 只在“最近的 / 上次 / 刚才那个”这类显式引用时才参与取消推断。
- `resolved` 已补预约并发回归测试，当前版本依赖 PostgreSQL `UPDATE ... WHERE quota_available > 0 RETURNING` 的行级锁语义防止超卖。
- `resolved` QA 样本集已经扩到患者教育 / 公共卫生 / 临床指南 / 跟进问句 / 无证据场景，不再只覆盖演示样本。

### P2

- `deferred` 前端视觉层级和最终产品化打磨延后处理，本轮不继续调整 UI。
- `open` 检索质量评估目前已有最小样本集，但还缺更大规模的真实 transcript 基线和更细的分类型评分。
- `open` OCR 兜底已经增强，但扫描件 PDF 的真实命中率还需要更多样本验证。
- `open` 多意图单轮请求目前仍以“先完成主动作”优先，例如“取消预约，然后问症状”需要分到下一轮继续；后续可以考虑显式拆分 compound requests。

## Notes

- 本文件已按当前代码状态重排，避免继续围绕已修复问题重复改造。
- 后续新增问题优先补“可回归测试 + 最小修复”，再更新本清单状态。
