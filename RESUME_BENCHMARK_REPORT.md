# Resume Benchmark Report

## Scope

This report captures two resume-oriented benchmark views for the medical assistant project:

1. Hybrid memory versus full-history prompting token usage
2. Baseline medical retrieval versus optimized retrieval on the bundled NHC/WHO markdown corpus

## Commands

Run from the repository root with the project `venv`:

```powershell
.\venv\Scripts\python.exe project\benchmarks\evaluate_memory_token_benchmark.py --json
.\venv\Scripts\python.exe project\benchmarks\evaluate_medical_rag_benchmark.py --json
.\venv\Scripts\python.exe -m unittest tests.test_resume_benchmarks -v
```

## Current Snapshot

### Memory benchmark

- Sample set: `4` long multi-turn transcripts
- Baseline: full conversation history + current user turn
- Optimized: conversation summary + persisted state + recent window + current user turn

Current result:

- `avg_baseline_tokens`: `813.25`
- `avg_optimized_tokens`: `662.25`
- `avg_token_reduction_rate`: `17.71%`
- `p95_token_reduction_rate`: `27.37%`

Suggested resume phrasing:

- Built a hybrid memory strategy combining Redis short-term context, LLM summary, and persisted state, reducing prompt tokens by **17.7% on average** and **27.4% at P95** versus full-history prompting in long medical transcripts.

### RAG retrieval benchmark

- Sample set: `10` medical retrieval questions
- Corpus: local `markdown_docs/` NHC + WHO documents
- Baseline: naive fixed-size chunks + dense retrieval
- Optimized: parent-child chunking + hybrid retrieval + query planning + RRF fusion + rerank

Current result:

- `baseline_precision_at_5`: `0.6833`
- `optimized_precision_at_5`: `0.8333`
- `precision_uplift`: `+0.15`
- `baseline_recall_at_5`: `1.0`
- `optimized_recall_at_5`: `1.0`
- `baseline_mrr_at_10`: `1.0`
- `optimized_mrr_at_10`: `1.0`

Suggested resume phrasing:

- Optimized the medical RAG pipeline with parent-child chunking, hybrid dense+sparse retrieval, query rewrite, and RRF fusion, improving **Precision@5 from 0.68 to 0.83** on an isolated **NHC/WHO medical guideline benchmark** while maintaining **Recall@5 = 1.00**.

### Offline answer benchmark

- Sample set: `11` offline answer-evaluation questions
- Corpus: local `markdown_docs/` NHC + WHO documents
- Baseline answer path: naive chunks + dense retrieval + deterministic grounded synthesis
- Optimized answer path: parent-child chunking + hybrid retrieval + query planning + parent-context reconstruction + grounded synthesis

Current result:

- `baseline_avg_answer_score`: `0.3321`
- `optimized_avg_answer_score`: `0.5838`
- `answer_score_uplift`: `+0.2517`
- `baseline_avg_overall_score`: `0.3510`
- `optimized_avg_overall_score`: `0.3968`

Suggested resume phrasing:

- Extended the RAG evaluation stack from retrieval-only metrics to an offline answer-level benchmark, raising grounded answer quality score from **0.33 to 0.58** on an isolated **NHC/WHO** benchmark set.

## Notes

- These numbers come from the repository's bundled offline benchmark fixtures and do not depend on an external vector store.
- The retrieval benchmark intentionally uses an isolated in-memory corpus so it does not mutate the live PostgreSQL `child_chunks` table.
- If the document corpus or benchmark samples change, rerun both scripts before reusing the numbers externally.
