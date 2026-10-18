# Blue Market Scout — baseline e piloto governado (18/10/2026)

**Fonte:** Odoo Conexão Azul Digital, company_id **1**, consultado em 18/10/2026 pelo MCP Conexão Azul Ops, via `odoo_consultas_get_current_context` e `odoo_consultas_aggregate_records`. Visão **somente leitura**, agregada, sem contatos pessoais.

**Não é estimativa de TAM, número de clientes válidos ou receita potencial.** São contagens de registros de CRM e Company 360. Perfis empresariais e leads têm granularidades diferentes, portanto não dividir perfis por leads como métrica de cobertura confiável.

## Retrato da base comercial

| Métrica | Valor | Escopo |
|---|---:|---|
| Leads CRM ativos | 55.581 | `crm.lead`, `company_id=1`, `active=true` |
| Etapa `01 · Capturado` | 41.071 | `stage_id=1` |
| Etapa `90 · Nurture / Frio` | 13.399 | `stage_id=24` |
| Demais etapas | 1.111 | Subtração do total |
| Fonte de origem `source_id=false` | 31.804 | Não equivale a "origem desconhecida no mundo real"; campo CRM ausente |
| Origem WhatsApp/Chatwoot | 13.897 | `source_id=50` |
| Origem Google Maps | 7.996 | `source_id=52` |
| Origem Migração pg6 → consultas | 1.673 | `source_id=121` |
| ICP A | 180 | `blue_icp_grade=a` |
| ICP B | 1.981 | `blue_icp_grade=b` |
| ICP C | 5.828 | `blue_icp_grade=c` |
| Leads com timestamp de scoring | 7.989 | `blue_icp_scored_at != false` |
| Leads com enriquecimento datado | 24 | `blue_enriched_at != false` **não garante qualidade real** |
| Leads vinculados ao Company 360 | 26 | `blue_company_profile_id != false` |
| Perfis Company 360 nesta empresa | 38 | `blue.company.profile`, `company_id=1` |

### Política de contato: bloqueio de qualquer campanha automática

| `blue_contact_policy` | Leads |
|---|---:|
| `manual_only` | 55.545 |
| `do_not_contact` | 23 |
| `approved` | 13 |

Dos **180** leads ICP A, apenas **10** têm política `approved`; outros **170** são `manual_only`. A marcação `approved` isolada não prova autorização para WhatsApp/email nem abertura da janela de atendimento. É obrigatório conciliar finalidade, canal, contato anterior, opt-out e aprovação humana.

**Novos registros de outubro de 2026**: 152 leads ativos, **152 `manual_only`**, 89 com origem Google Maps e 58 sem `source_id`. Isso invalida qualquer tese de liberar disparos automáticos para novos leads sem etapa de consentimento.

## Company 360 — setores já representados (não cobertura de mercado)

Dos 38 perfis da empresa 1:
- Contabilidade CNAE `6920601`: **16 perfis**
- Atividades de atendimento médico ambulatorial CNAE `8630504`: **5**
- Educação infantil `8512100`: **2** e apoio à educação `8550302`: **1**
- Outros CNAEs isolados: 1 por categoria, mais 2 sem CNAE
- Perfis identificados diretamente nas categorias agronegócio e transporte/logística: **não demonstrados nesta amostra**. Isso não prova inexistência de leads desses setores entre os 55.581.

## Piloto P0/P1: 100 empresas — apenas pesquisa, nenhuma escrita externa

| Coorte | Quantidade-alvo | Por quê |
|---|---:|---|
| 10 ICP-A já com política `approved` | 10 | Validar origem, identidade, produto e permissões separadas por canal |
| 30 ICP-A com política `manual_only` | 30 | Medir melhoria de qualificação SEM contato |
| 12 empresas externas de agronegócio | 12 | Segmento de produto Blue Agro, pouca evidência Company 360 |
| 12 empresas externas industriais | 12 | Odoo MRP/projetos e automação |
| 12 empresas externas de logística | 12 | ERP, integração e operações |
| 9 empresas externas de educação | 9 | CRM/automação/atendimento e integração |
| 9 empresas externas de saúde | 9 | Blue Voice, interoperabilidade, processos |
| 6 empresas externas contábeis | 6 | Testar especialização onde já há conhecimento |
| **Total planejado** | **100** | Alvos, NÃO pessoas contatadas |

Regras de amostragem:
1. Uma empresa = uma identidade `external_ref` / CNPJ comprovado ou registro público. O `company_id=1` é da **Conexão Azul Digital**, não da empresa prospectada.
2. Evidência fonte+data por sinal; não fazer scraping de dados pessoais nem executar páginas suspeitas no mesmo ambiente do CRM.
3. Deduplicação prévia e pesquisa somente leitura. Bônus de score para fonte, sinal de mudança, relevância do produto e verificabilidade; não fabricar orçamento, dor, cargo ou interesse.
4. Não usar `enrichment_state=validated` só porque Hermes gerou um relatório; evidência exige validação em fonte independente antes do review gate.
5. `requires_human_approval=true`, `can_send=false`, `can_write_odoo=false`; não instalar habilidade nem ativar cron outbound neste piloto.
6. Toda promoção para CRM passa pela futura ponte autenticada e segura (n8n `Smuy1GhkCvCzmHLy` é apenas LAB sintético). Ver PR de integração https://github.com/conexaoazul/n8n-conector-ca/pull/1.

### Métricas de eficiência — metas de piloto, não resultados

- Tempo humano por pesquisa **antes/depois** em amostra pareada.
- Custo LLM e de extração por empresa pesquisada, com `correlation_id`.
- `evidence_valid_rate` e `duplicate_rate` por origem e setor.
- Taxa de empresas com identidade empresarial resolvida, por setor.
- Aderência ao ICP e indicação de produto com evidência.
- **Guardrails:** zero envios, zero CRM writes, zero contatos PII coletados, 100% empresas com escopo e correlation ID.
- Só depois, com dados financeiros conciliados, estimar conversão, CAC e receita atribuída.

## Reprodução das contagens

Executar sempre em `company_id=1` com `active=true` e `odoo_consultas_aggregate_records`:
- `model="crm.lead", groupby=["stage_id"]`
- `model="crm.lead", groupby=["source_id"]`
- `model="crm.lead", groupby=["blue_contact_policy"]`
- `model="crm.lead", groupby=["blue_icp_grade"]`
- `model="blue.company.profile", groupby=["primary_cnae_code"], domain=[["company_id","=",1]]`

Contagens e estado de políticas são mutáveis. Revisar no dia de execução. Não inferir consentimento de origem Google Maps/Chatwoot e não migrar `company_id=false` automaticamente.
