# ADR-001: Governed Semantic Layer (Text-to-Metrics) vs. Raw Text-to-SQL

- **Status:** Aceito
- **Data:** 2026-11-21

## Contexto
Times de Finanças, Risco e Produto em uma FinTech de pagamentos fazem perguntas analíticas diárias em linguagem natural (ex.: *"Qual foi o Net Take-Rate por região no último mês?"* ou *"Onde o chargeback está acima de 100 bps?"*).

Abordagens tradicionais de **Raw Text-to-SQL** (enviar o schema do banco para um LLM e executar o SQL gerado diretamente no BigQuery) apresentam riscos críticos em ambientes financeiros:
1. **Alucinação de regras de negócio:** o LLM frequentemente soma transações `declined` ou `refunded` no TPV, ou calcula `AVG(take_rate)` (média de médias) em vez de `SUM(net_revenue) / SUM(gross_tpv)`.
2. **Fan-out silencioso:** joins incorretos entre transações e chargebacks duplicam valores financeiros.
3. **Risco de segurança e custo:** SQL arbitrário pode expor dados fora de escopo ou disparar scans caros no BigQuery.

## Decisão
Adotar uma arquitetura **Governed Text-to-Metrics**:
1. Todas as métricas oficiais (`gross_tpv_brl`, `net_take_rate_bps`, `chargeback_rate_bps`, `approval_rate`, etc.) são definidas declarativamente na **Semantic Layer** (`dbt_project/models/marts/_semantic_models.yml` no padrão MetricFlow + catálogo sincronizado em `contracts/semantic_catalog.yaml`).
2. O **AI Copilot (Gemini via Vertex AI)** **nunca gera SQL livre**. Ele utiliza *Structured Tool / Function Calling* para produzir um `SemanticQueryPlan` tipado (lista de `metrics`, `dimensions`, `filters`, `time_grain`, `limit`).
3. Uma camada de **Guardrails** valida o plano contra a *allowlist* semântica e bloqueia tentativas de *prompt injection* ou *SQL injection*.
4. Um **Compilador Semântico determinístico** gera SQL parametrizado e auditável para **DuckDB (local)** ou **BigQuery (GCP com `maximum_bytes_billed`)**, retornando os resultados, o SQL compilado e a definição oficial de cada métrica.

## Alternativas Consideradas
1. **Raw Text-to-SQL com Few-Shot Prompting:** Rápido de prototipar, mas inaceitável para KPIs financeiros auditáveis devido à variância não determinística de fórmulas e risco de erro em ratios.
2. **dbt Cloud Semantic Layer API (Enterprise):** Excelente solução gerenciada em empresas com licença dbt Cloud Enterprise, porém exige assinatura paga e impediria avaliadores/CI de reproduzirem a camada de IA localmente a custo \$0. Mantivemos 100% de compatibilidade com os YAML do MetricFlow para migração direta caso a empresa adote dbt Cloud.

## Consequências & Trade-offs
- **Positivas:** 0% de alucinação de fórmula financeira, auditoria completa de lineage/SQL, proteção contra SQL injection, e testabilidade determinística via **AI Evals** no CI.
- **Negativas / Riscos:** Perguntas completamente ad-hoc fora do catálogo semântico são recusadas com orientação clara ao usuário até que a métrica/dimensão seja promovida ao catálogo via PR (comportamento intencional de governança).
