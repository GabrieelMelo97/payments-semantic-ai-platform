# ADR-002: Arquitetura GCP Serverless, Terraform Modular & FinOps

- **Status:** Aceito
- **Data:** 2026-11-21

## Contexto
A plataforma precisa operar em produção no **Google Cloud Platform (GCP)** com alta governança, segurança *Least Privilege* e custos previsíveis — sem manter servidores ociosos (VMs ou clusters sempre ligados) e sem expor credenciais estáticas em repositórios públicos.

## Decisão
Provisionar toda a infraestrutura via **Terraform modular** (`infra/terraform/modules/`: `storage`, `warehouse`, `security`, `compute`, `finops`) utilizando stack 100% serverless/scale-to-zero no GCP:
- **Cloud Storage (GCS):** Bucket privado (`uniform_bucket_level_access = true`, `public_access_prevention = "enforced"`) com lifecycle automático (Coldline após 60 dias, expiração de arquivos temporários em 180 dias).
- **BigQuery:** Datasets segregados por camada (`payments_raw`, `payments_stg`, `payments_int`, `payments_marts`), tabelas fato particionadas por `transaction_date` e clusterizadas por `(region, mcc_category, payment_method)`, e trava `maximum_bytes_billed` nas queries do Copilot.
- **Compute Serverless:** **Cloud Run Jobs** (disparado via Cloud Scheduler) para executar `dbt build`, e **Cloud Run Service** (`min_instance_count = 0`) para servir a API FastAPI / Streamlit Copilot com **Vertex AI (Gemini)**.
- **Security by Design:** 3 Service Accounts distintas (`sa-ingest`, `sa-dbt-runner`, `sa-ai-copilot`) com papéis mínimos por dataset/recurso e zero chaves JSON estáticas (uso de Application Default Credentials e Workload Identity Federation no CI/CD).
- **FinOps:** Labels obrigatórias em 100% dos recursos (`project`, `env`, `managed_by`, `domain`) e módulo opcional de `google_billing_budget` com alertas em 50%, 80% e 100%.

## Alternativas Consideradas
1. **Cloud Composer (Airflow Gerenciado) para orquestrar dbt:** Custo mínimo fixo elevado (~US\$ 300+/mês mesmo ocioso), desproporcional para um pipeline analítico diário/horário onde Cloud Run Jobs + Cloud Scheduler custam centavos por mês.
2. **GKE Autopilot para servir o Copilot:** Complexidade operacional desnecessária comparada ao Cloud Run serverless com scale-to-zero.

## Consequências & Trade-offs
- **Positivas:** Custo mensal em dev próximo de **US\$ 1–5/mês** (dentro do Free Tier do BigQuery/Cloud Run para baixos volumes), alta postura de segurança e `terraform destroy` limpo.
- **Negativas / Riscos:** *Cold start* de 1–3 segundos no Cloud Run quando `min_instance_count = 0` (aceitável para ferramenta interna de BI/Copilot; mitigável elevando `min_instance_count = 1` em produção).
