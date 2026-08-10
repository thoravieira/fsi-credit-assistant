# Copiloto de Crédito PF — visão geral da demo

> Documento em português, voltado para validação de negócio.
> A especificação técnica está em [`docs/specs/`](specs/00-overview.md), em inglês.

---

## O que é

Um copiloto de originação de crédito para pessoa física — financiamento imobiliário e de
veículo — construído sobre um agente de IA orquestrado com LangGraph, tendo o MongoDB Atlas
como único banco de dados de toda a arquitetura.

## O problema

Hoje a originação de crédito trava nas duas pontas. **O cliente** entra num funil opaco:
simula, não entende por que foi negado, e quando o pedido cai em análise manual fica dias
sem resposta. **O analista** recebe um caso cru e refaz a análise do zero a cada cenário
alternativo — reduzir o valor, aumentar a entrada, alongar o prazo, aceitar garantia
adicional. Cada "e se" é uma rodada de planilha, consulta a política e busca de casos
parecidos na memória de quem já viu muito caso. O resultado é caro dos dois lados: o banco
perde negócio bom por lentidão e o cliente desiste sem saber o que faltava.

## O que a demo resolve

O agente atua nas duas pontas do mesmo pedido. Para a cliente, ele simula, aplica a política
de crédito e responde em linguagem natural **por que** o pedido foi pré-aprovado ou por que
precisa de análise — não só o resultado. Para o analista, ele chega com o caso já
instruído: recomendação, comprometimento de renda, LTV, os artigos da política que se
aplicam e casos históricos parecidos com o desfecho de cada um. E aí vem o núcleo: o
analista conversa com o agente testando cenários, e cada "e se" é re-simulado em segundos,
com o cálculo feito por código determinístico — o modelo escolhe o cenário, a matemática
não é inventada por ele. Nada é gravado como decisão sem aprovação humana explícita, e toda
simulação, **inclusive as descartadas**, vira trilha de auditoria. A decisão de hoje é
indexada e vira o precedente recuperado no caso de amanhã: o sistema melhora com o uso, sem
retreinar modelo nenhum.

## Benefícios

| Para o cliente | Para o analista | Para o banco |
|---|---|---|
| Resolve sozinho quando o caso é simples | Copiloto que testa cenários em segundos | Menos casos escalados sem necessidade |
| Entende o motivo, não só o "não" | Chega no caso já instruído, não cru | Trilha de auditoria completa e consultável |
| Sabe o que fazer para virar o jogo | Mantém a decisão na mão dele | Conhecimento institucional que acumula |

## Por que MongoDB

Um agente precisa de quatro coisas ao mesmo tempo: dados operacionais, estado da conversa,
memória de longo prazo e busca semântica. O caminho convencional resolve isso com quatro
sistemas diferentes — banco relacional, cache, banco vetorial, mais um store de memória.
Aqui é **um cluster só**: um driver, um modelo de consistência, uma política de backup, uma
superfície de segurança.

---

## Fluxo da demo

```mermaid
flowchart TD
    subgraph CLI["👤 Mariana — app do banco"]
        M1["Quero financiar R$ 448 mil<br/>em 360 meses"]
        M2["Resposta em linguagem natural:<br/>o resultado e o porquê"]
    end

    subgraph AG["⚙ Agente de crédito — LangGraph"]
        A1["Entende o pedido<br/>valor, prazo, entrada"]
        A2["Carrega contexto<br/>perfil + memória de longo prazo"]
        A3["Consulta a política de crédito<br/>busca semântica"]
        A4["Calcula<br/>parcela, CET, LTV, comprometimento"]
        A5{"Passa na<br/>política?"}
        A6["Busca precedentes<br/>casos históricos parecidos"]
        A7["Monta o dossiê do caso<br/>recomendação + explicabilidade"]
        A8["Negocia cenários<br/>agente com ferramentas"]
        A9{"Analista<br/>fechou?"}
        A10["⏸ Aguarda aprovação humana"]
        A11["Registra a decisão"]
    end

    subgraph AN["💼 Carlos — console do analista"]
        C1["Abre o caso na fila"]
        C2["E se aumentar a entrada?<br/>E se alongar o prazo?<br/>E se compartilhar investimentos<br/>via Open Finance?"]
        C3["Aprova ou nega"]
    end

    subgraph DB["🍃 MongoDB Atlas — um único banco"]
        D1[("Memória de curto prazo<br/>estado da conversa")]
        D2[("Memória de longo prazo<br/>preferências e fatos")]
        D3[("Políticas de crédito<br/>busca vetorial")]
        D4[("Casos históricos<br/>busca vetorial")]
        D5[("Trilha de auditoria<br/>toda decisão e simulação")]
    end

    M1 --> A1 --> A2 --> A3 --> A4 --> A5
    A5 -->|"Pré-aprovado"| M2
    A5 -->|"Análise manual"| C1
    C1 --> A6 --> A7 --> C2
    C2 --> A8 --> A9
    A9 -->|"Testa outro cenário"| A8
    A9 -->|"Decisão final"| A10 --> C3 --> A11
    A11 --> M2

    A2 -.->|"lê"| D2
    A3 -.->|"lê"| D3
    A6 -.->|"lê"| D4
    A8 -.->|"lê"| D3
    A8 -.->|"lê"| D4
    A11 -.->|"grava"| D5
    A11 -.->|"vira novo precedente"| D4
    A11 -.->|"aprende preferências"| D2
    AG -.->|"salva o estado a cada passo"| D1

    classDef mongo fill:#00684A,stroke:#001E2B,color:#fff
    classDef human fill:#E3FCF7,stroke:#00684A,color:#001E2B
    class D1,D2,D3,D4,D5 mongo
    class M1,M2,C1,C2,C3 human
```

### Como ler o diagrama

- **Linha cheia** = fluxo do pedido. **Linha pontilhada** = leitura ou escrita no MongoDB.
- O ciclo `A8 ⇄ A9` é o coração da demo: cada "e se" do analista é uma volta ali, em segundos.
- O `⏸` antes de gravar é literal — o agente pausa e só continua com aprovação humana.
- A seta `A11 → D4` fecha o ciclo de aprendizado: a decisão de hoje é o precedente de amanhã.
- Mariana e Carlos estão na **mesma conversa** do ponto de vista do sistema; o contexto dela
  chega até ele sem nenhum handoff explícito.
