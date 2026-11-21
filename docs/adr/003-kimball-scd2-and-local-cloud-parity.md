# ADR-003: Modelagem Kimball com SCD Type 2 (MDR) e Paridade Local-to-Cloud

- **Status:** Aceito
- **Data:** 2026-11-21

## Contexto
Em adquirência de pagamentos, a taxa MDR (*Merchant Discount Rate*) e o custo de intercâmbio de um lojista mudam ao longo do tempo (renegociações comerciais, mudança de faixa de faturamento). Se a tabela fato `fct_payments` fizer join apenas com a taxa *atual* do lojista, o reprocessamento histórico (backfill) corrompe a receita passada. Além disso, chargebacks chegam com até 30 dias de atraso (*late-arriving facts*).

Por fim, precisamos que qualquer avaliador ou pipeline de CI execute 100% dos modelos, testes e contratos localmente sem depender de credenciais de nuvem.

## Decisão
1. **Modelagem Kimball (Staging → Intermediate → Marts):**
   - `staging`: limpeza 1:1, tipagem e normalização.
   - `snapshots`: `snap_merchant_mdr_rates` (**SCD Type 2**) rastreando `dbt_valid_from` e `dbt_valid_to` das tarifas de cada merchant.
   - `intermediate`: `int_transactions_enriched` realiza deduplicação determinística por `transaction_id`, join temporal com o snapshot SCD2 para atribuir a tarifa vigente na data da transação, e agregação prévia de chargebacks (evitando *fan-out*).
   - `marts`: `fct_payments` (materializado como **incremental** com `unique_key='transaction_id'`), `dim_merchants`, `dim_date`, `fct_daily_payment_metrics` e `metricflow_time_spine`, protegidos por **dbt Model Contracts** (`enforced: true`), **dbt Unit Tests** e teste singular de **reconciliação financeira**.
2. **Paridade Local-to-Cloud:** O mesmo projeto dbt roda com `--target local` (**DuckDB**, custo \$0) e `--target bigquery` (**GCP BigQuery**), garantindo SQL ANSI compatível entre os dois motores.

## Alternativas Consideradas
1. **One Big Table (OBT) sem dimensões separadas:** Simplifica queries ad-hoc, mas dificulta governança de atributos de lojista e reuso em múltiplos marts. Adotamos Star Schema (`fct_payments` + `dim_merchants` + `dim_date`) com desnormalização controlada das dimensões-chave na `fct_payments` para baixa latência na Semantic Layer.
2. **Apenas BigQuery (sem DuckDB local):** Quebraria a reprodutibilidade instantânea em CI e para recrutadores sem conta GCP.

## Consequências & Trade-offs
- **Positivas:** Precisão histórica contábil (backfills idempotentes sem distorcer receita passada), CI rápido (<30s) e custo zero para desenvolvimento local.
- **Negativas / Riscos:** Requer disciplina de SQL portátil (evitar funções proprietárias do BigQuery sem macro/compatibilidade DuckDB), validada automaticamente pelo CI com `dbt build --target local` e `sqlfluff`.
