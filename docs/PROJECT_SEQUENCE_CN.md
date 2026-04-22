# 项目时序图导读（中文）

这份文档专门用时序图解释项目，不再按目录讲，而是按“用户发一句话之后，系统内部怎么流转”来讲。

建议配合下面这些文件一起看：

- `D:\nageoffer\agentic-rag-for-dummies\project\core\chat_interface.py`
- `D:\nageoffer\agentic-rag-for-dummies\project\rag_agent\graph.py`
- `D:\nageoffer\agentic-rag-for-dummies\project\rag_agent\edges.py`
- `D:\nageoffer\agentic-rag-for-dummies\project\rag_agent\nodes.py`
- `D:\nageoffer\agentic-rag-for-dummies\project\rag_agent\tools.py`
- `D:\nageoffer\agentic-rag-for-dummies\project\services\appointment_skill\__init__.py`
- `D:\nageoffer\agentic-rag-for-dummies\project\services\appointment_service.py`

---

## 1. 总览：一次消息从前端进入系统

```mermaid
sequenceDiagram
    participant U as 用户
    participant UI as "gradio_app.py"
    participant CI as "chat_interface.py"
    participant RM as "RedisSessionMemory"
    participant SS as "SummaryStore"
    participant RG as "RAGSystem"
    participant G as "LangGraph 主图"

    U->>UI: 在聊天框输入一句话
    UI->>CI: chat(user_message, history, thread_id)
    CI->>RG: 检查系统是否 ready
    CI->>RM: 读取 thread 的 session state
    CI->>RM: 读取 recent messages
    CI->>SS: 读取 conversation summary
    CI->>CI: 组装 graph state
    CI->>G: 调用 agent_graph.stream / invoke
    G-->>CI: 返回节点更新、消息、状态
    CI->>RM: 写回最新 session state
    CI->>RM: 写回 recent messages
    CI-->>UI: 返回对用户可见的消息
    UI-->>U: 展示最终回答
```

### 这张图对应什么代码

- UI 入口：`D:\nageoffer\agentic-rag-for-dummies\project\ui\gradio_app.py`
- 会话编排：`D:\nageoffer\agentic-rag-for-dummies\project\core\chat_interface.py`
- 系统总装配：`D:\nageoffer\agentic-rag-for-dummies\project\core\rag_system.py`

### 理解重点

- 前端本身不做业务判断。
- `ChatInterface` 是“请求总编排器”。
- 真正决定“走哪条业务链”的，是 LangGraph 主图。

---

## 2. 主图：用户一句话进入后怎么被路由

```mermaid
sequenceDiagram
    participant CI as "ChatInterface"
    participant G as "graph.py"
    participant SH as "summarize_history"
    participant AT as "analyze_turn"
    participant IR as "intent_router"
    participant RW as "rewrite_query"
    participant RD as "recommend_department"
    participant AS as "handle_appointment_skill"
    participant GC as "grounded_answer_generation"
    participant AGC as "answer_grounding_check"

    CI->>G: 传入 State
    G->>SH: summarize_history
    SH-->>G: summary / history info
    G->>AT: analyze_turn
    AT-->>G: primary_intent / secondary_intent / topic_focus / recent_context
    G->>IR: intent_router

    alt medical_rag
        IR-->>G: intent = medical_rag
        G->>RW: rewrite_query
        RW-->>G: rewrittenQuestions / questionIsClear
        G->>GC: 经过 agent 子图后做聚合
        GC->>AGC: grounding check
        AGC-->>G: final answer
    else triage
        IR-->>G: intent = triage
        G->>RD: recommend_department
        RD-->>G: 推荐科室
    else appointment / cancel
        IR-->>G: intent = appointment 或 cancel_appointment
        G->>AS: handle_appointment_skill
        AS-->>G: discovery / preview / confirm result
    else clarification
        IR-->>G: intent = clarification
        G-->>CI: 返回澄清问题
    end

    G-->>CI: 最终消息和最新状态
```

### 这张图的意义

这张图说明主图并不是一上来就 RAG。

它一定先做两步：

1. `analyze_turn`
2. `intent_router`

也就是说，你可以把整个后端理解成：

- 先判断“这轮到底在干嘛”
- 再进入正确业务分支

---

## 3. `analyze_turn` 到底做了什么

```mermaid
sequenceDiagram
    participant U as 用户输入
    participant AT as "analyze_turn"
    participant S as "State"

    U->>AT: 当前 user query
    S->>AT: pending_action / clarification_target / summary / recent_context
    AT->>AT: 检查是否继续上一轮 pending 流程
    AT->>AT: 提取 recent_context
    AT->>AT: 提取 topic_focus
    AT->>AT: 判断是否是复合请求
    alt 是复合请求
        AT->>AT: 拆成 primary_user_query + secondary_user_query
        AT->>AT: 生成 primary_intent + secondary_intent
        AT->>AT: 保存 deferred_user_question
    else 单一请求
        AT->>AT: 只生成 primary_intent 候选
    end
    AT-->>S: 更新 primary_intent / secondary_intent / topic_focus / recent_context
```

### 为什么它重要

`analyze_turn` 是这个项目里最容易“看不见但很关键”的节点。

它不是直接回答问题，而是帮系统做三件特别重要的事：

- 记住你现在是不是还在某个预约/取消流程里
- 记住这一轮的主题是什么
- 把一句话里的两件事拆开

例如：

- “取消刚才那个预约，然后我这个咳嗽还要看吗”

它会拆成：

- 主意图：取消预约
- 次意图：医学问答

---

## 4. 医学问题：RAG 路线怎么走

```mermaid
sequenceDiagram
    participant IR as "intent_router"
    participant RW as "rewrite_query"
    participant PQ as "plan_retrieval_queries"
    participant AG as "agent 子图"
    participant OR as "orchestrator"
    participant T as "tools.py"
    participant DB as "vector_db / parent_store"
    participant CA as "collect_answer"
    participant GA as "grounded_answer_generation"
    participant AC as "answer_grounding_check"

    IR-->>RW: intent = medical_rag
    RW->>RW: 判断问题是否清晰、是否需要改写
    RW-->>PQ: rewrittenQuestions
    PQ->>PQ: 生成 2-4 条 retrieval queries
    PQ-->>AG: planned_queries

    loop 每个 query 并行进入 agent 子图
        AG->>OR: orchestrator
        OR->>T: 调用 search_child_chunks / retrieve_parent_chunks
        T->>DB: 向量检索 + 关键词检索 + 父块读取
        DB-->>T: docs / chunks
        T-->>OR: 检索结果文本
        OR-->>CA: 生成这一条 query 的 answer
        CA-->>AG: question-level answer + confidence + citations
    end

    AG-->>GA: 汇总多个 query 的 answers
    GA->>GA: 合成最终回答、附来源、附 confidence
    GA->>AC: grounding check
    AC-->>GA: 如有必要压成更保守答案
```

### 医学问答这条线最关键的 5 件事

1. **不是只查一次**  
   `plan_retrieval_queries` 会生成多条检索表达。

2. **不是只做向量检索**  
   还会做关键词检索，然后用 RRF 融合。

3. **有来源分层**  
   会优先考虑：
   - `patient_education`
   - `public_health`
   - `clinical_guideline`

4. **有证据强度**  
   最终会给：
   - `high`
   - `medium`
   - `low`
   - `no_evidence`

5. **没证据也不一定拒答**  
   医学问题在 `no_evidence / low` 时，可以进入“通用医学信息回答”模式，但会带安全提醒。

---

## 5. 检索层内部是怎么做的

```mermaid
sequenceDiagram
    participant OR as "orchestrator"
    participant SC as "search_child_chunks"
    participant V as "pgvector similarity search"
    participant K as "tsvector keyword search"
    participant R as "RRF fusion"
    participant L as "source layering"
    participant RR as "rerank"

    OR->>SC: query
    SC->>V: 向量召回
    SC->>K: 关键词召回
    V-->>SC: vector results
    K-->>SC: keyword results
    SC->>R: 融合两组结果
    R-->>SC: fused results
    SC->>L: 按 source_type 分层排序
    L-->>SC: layered results
    SC->>RR: 最终 rerank
    RR-->>SC: final docs
    SC-->>OR: 文档内容 + metadata + confidence bucket
```

### 为什么不是“只向量搜索一下”

因为这个项目要解决两类问题：

- 语义相近
- 术语精确命中

所以它用了：

- 向量检索解决“相近语义”
- 关键词检索解决“精确匹配”
- RRF 解决“如何把两种结果合起来”

---

## 6. 预约发现到确认：挂号流程怎么走

```mermaid
sequenceDiagram
    participant U as 用户
    participant G as "handle_appointment_skill"
    participant SK as "AppointmentSkill"
    participant CAT as "catalog.py"
    participant PLAN as "planner.py"
    participant ACT as "actions.py"
    participant SVC as "appointment_service.py"
    participant DB as "PostgreSQL"

    U->>G: 我想挂号 / 呼吸内科 / 张医生 / 任一可用医生

    alt discovery
        G->>SK: discover_departments / discover_doctors / discover_availability
        SK->>CAT: 查科室 / 查医生 / 查号源
        CAT->>SVC: 调预约服务查询
        SVC->>DB: 查 departments / doctors / schedules / appointments
        DB-->>SVC: 查询结果
        SVC-->>CAT: 结构化 rows
        CAT-->>SK: 候选信息
        SK-->>G: discovery message + candidates
        G-->>U: 展示科室 / 医生 / 可预约时段
    else planning
        G->>SK: prepare_appointment
        SK->>PLAN: 选医生 / 替代方案 / 任一可用医生
        PLAN->>SVC: 查目标 schedule
        SVC->>DB: 查 doctor_schedules
        DB-->>SVC: 匹配 schedule
        SVC-->>PLAN: schedule
        PLAN->>ACT: 生成 AppointmentPreview
        ACT-->>SK: preview
        SK-->>G: preview payload
        G-->>U: 请回复确认预约
    else confirm
        U->>G: 确认预约
        G->>SK: confirm_appointment
        SK->>SVC: create_appointment
        SVC->>DB: 扣减 quota + 写 appointments
        DB-->>SVC: 预约成功
        SVC-->>SK: booking result
        SK-->>G: success
        G-->>U: 预约成功 + 预约号
    end
```

### 这条链的关键思想

不是“模型直接挂号”，而是：

- 先 discovery
- 再 planning
- 再 confirm

这就是现在项目里的“半受控 Function Calling”。

---

## 7. 取消预约流程怎么走

```mermaid
sequenceDiagram
    participant U as 用户
    participant G as "handle_appointment_skill"
    participant SK as "AppointmentSkill"
    participant SVC as "appointment_service.py"
    participant DB as "PostgreSQL"

    U->>G: 取消预约 / 取消最近那个 / 取消第2个

    alt 需要找候选
        G->>SK: prepare_cancellation
        SK->>SVC: find_candidate_appointments
        SVC->>DB: 查 active appointments
        DB-->>SVC: candidate list
        SVC-->>SK: 候选预约
        SK-->>G: 候选列表
        G-->>U: 让用户选预约号 / 第1个 / 第2个
    else 候选已确定
        G->>SK: 生成 CancellationPreview
        SK-->>G: preview
        G-->>U: 请确认取消
    end

    U->>G: 确认取消
    G->>SK: confirm_cancellation
    SK->>SVC: cancel_appointment
    SVC->>DB: 更新 appointments + 返还 quota
    DB-->>SVC: cancellation result
    SVC-->>SK: success
    G-->>U: 取消成功
```

---

## 8. 改约流程怎么走

```mermaid
sequenceDiagram
    participant U as 用户
    participant G as "handle_appointment_skill"
    participant SK as "AppointmentSkill"
    participant SVC as "appointment_service.py"
    participant DB as "PostgreSQL"

    U->>G: 把最近那个预约改到后天上午
    G->>SK: prepare_reschedule
    SK->>SVC: 查当前预约 + 查新号源
    SVC->>DB: appointments + doctor_schedules
    DB-->>SVC: 当前预约与新时段候选
    SK-->>G: ReschedulePreview
    G-->>U: 展示改约预览并等待确认

    U->>G: 确认预约
    G->>SK: confirm_reschedule
    SK->>SVC: reschedule_appointment
    SVC->>DB: 原子化取消旧号 + 占用新号
    DB-->>SVC: 改约成功
    G-->>U: 改约成功
```

---

## 9. 状态和记忆是怎么回写的

```mermaid
sequenceDiagram
    participant G as "LangGraph"
    participant CI as "ChatInterface"
    participant RM as "RedisSessionMemory"
    participant SS as "SummaryStore"
    participant RL as "RouteLogStore"

    G-->>CI: 最新 state + messages
    CI->>CI: 过滤用户可见消息
    CI->>RM: 保存 pending_action / appointment_context / topic_focus 等状态
    CI->>RM: 保存 recent messages
    CI->>SS: 必要时保存 summary
    CI->>RL: 记录本轮 route log
```

### 可以记住的要点

- Redis 存“当前线程短期状态”
- SummaryStore 存“长一点的摘要”
- RouteLogStore 存“这轮被路由到了哪里”

所以系统不是只靠模型“自己记住”，而是显式维护状态。

---

## 10. 启动时系统是怎么准备的

```mermaid
sequenceDiagram
    participant APP as "app.py"
    participant UI as "create_gradio_ui()"
    participant SYS as "RAGSystem"
    participant VDB as "VectorDbManager"
    participant MF as "model_factory.py"
    participant G as "create_agent_graph"

    APP->>UI: create_gradio_ui()
    UI->>SYS: 创建 RAGSystem
    SYS->>VDB: 检查 collection / schema / 索引
    SYS->>MF: 初始化聊天模型
    SYS->>G: 创建主图和 agent 子图
    SYS-->>UI: 系统 ready
    UI-->>APP: 返回 Gradio demo
    APP-->>用户: 页面可用
```

---

## 11. 你现在最值得记住的 3 张图

如果你不想一次消化太多，建议先只记住这 3 张：

1. **总览图**  
   先知道消息从 UI 进入后，经过 `ChatInterface -> Graph -> Redis/DB`。

2. **医学问答图**  
   先知道 RAG 是：
   - 改写
   - 多 query 检索
   - 融合
   - 聚合
   - grounding

3. **预约图**  
   先知道预约不是一步提交，而是：
   - discovery
   - planning
   - confirm

---

## 12. 你后面如果继续看代码，推荐顺序

配合这份时序图，建议你下一步按这个顺序走读源码：

1. `D:\nageoffer\agentic-rag-for-dummies\project\core\chat_interface.py`
2. `D:\nageoffer\agentic-rag-for-dummies\project\rag_agent\graph.py`
3. `D:\nageoffer\agentic-rag-for-dummies\project\rag_agent\edges.py`
4. `D:\nageoffer\agentic-rag-for-dummies\project\rag_agent\nodes.py`
5. `D:\nageoffer\agentic-rag-for-dummies\project\rag_agent\tools.py`
6. `D:\nageoffer\agentic-rag-for-dummies\project\services\appointment_skill\__init__.py`
7. `D:\nageoffer\agentic-rag-for-dummies\project\services\appointment_service.py`

---

## 13. 一句话总结

这个项目可以一句话概括成：

**用户消息先进入 `ChatInterface`，再由 LangGraph 做统一路由；医学问题走 RAG 质量闭环，挂号相关问题走 Appointment Skill，最终状态和结果落回 Redis / PostgreSQL。**

