# Retrieval evaluation

Committed output of `backend/scripts/03_eval_retrieval.py`.

| Metric | Value | Healthy |
|---|---|---|
| recall@3 | 1.00 | >= 0.8 |
| recall@5 | 1.00 | >= 0.9 |
| mean top-1 score | 0.8259 | report, no threshold |
| worst query | Posso usar o FGTS para dar entrada no imóvel? (top-1 score 0.7878) | inspect manually |

## Golden set results

| # | Query | Product | Expected | Retrieved (top 5) | Hit@3 |
|---|---|---|---|---|---|
| 1 | Qual o limite de LTV para financiamento imobiliário residencial? | mortgage | POL-001 | POL-001, POL-024, POL-028, POL-020, POL-018 | yes |
| 2 | Quanto da minha renda posso comprometer com a parcela do financiamento da casa? | mortgage | POL-004 | POL-004, POL-001, POL-024, POL-020, POL-016 | yes |
| 3 | Qual a idade máxima somada ao prazo para financiar um imóvel? | mortgage | POL-006 | POL-006, POL-028, POL-010, POL-001, POL-020 | yes |
| 4 | Meu score está baixo, ainda consigo financiar um carro? | auto | POL-009 | POL-009, POL-015, POL-005, POL-002, POL-017 | yes |
| 5 | Posso usar o FGTS para dar entrada no imóvel? | mortgage | POL-010 | POL-010, POL-011, POL-024, POL-001, POL-022 | yes |
| 6 | Sou autônomo e não tenho holerite, como comprovo renda para financiar a casa? | mortgage | POL-012 | POL-012, POL-030, POL-024, POL-004, POL-016 | yes |
| 7 | Que garantia adicional posso oferecer se o LTV solicitado for maior que o limite? | mortgage | POL-014 | POL-014, POL-020, POL-001, POL-028, POL-024 | yes |
| 8 | Como o compartilhamento de dados via Open Finance pode ajudar a aprovar um financiamento com DTI acima do limite? | mortgage | POL-016 | POL-016, POL-004, POL-020, POL-014, POL-028 | yes |
| 9 | Qual a alçada de aprovação e a taxa de juros para um financiamento imobiliário de alto valor? | mortgage | POL-018, POL-020 | POL-020, POL-018, POL-001, POL-004, POL-008 | yes |
| 10 | O imóvel que eu quero comprar ainda está em inventário, dá pra financiar mesmo assim? | mortgage | POL-022 | POL-022, POL-023, POL-001, POL-010, POL-028 | yes |
