# Copiloto de Crédito PF — visão geral da demo

> Documento em português, para validação de negócio.
> Especificação técnica em [`docs/specs/`](specs/00-overview.md).

---

## Em uma frase

Um copiloto de crédito PF que atende as duas pontas do mesmo pedido. A cliente simula e
entende **por que** passou ou não; o analista recebe o caso já instruído — recomendação,
política aplicável e casos parecidos — e testa cenários alternativos em segundos, com o
cálculo feito por código, não pelo modelo. Nada vira decisão sem aprovação humana, tudo fica
em trilha de auditoria, e cada decisão vira precedente para o próximo caso. Tudo em um único
banco: MongoDB Atlas.

---

## Fluxo da demo

```mermaid
sequenceDiagram
    actor C as 👤 Mariana · cliente
    participant A as 🤖 Agente de IA
    participant M as 🍃 MongoDB Atlas
    actor N as 💼 Carlos · analista

    rect rgb(232, 245, 240)
    Note over C,N: 1 · Cliente simula o crédito
    C->>A: Imóvel de R$ 400 mil, entrada de R$ 100 mil, 360 meses
    A->>M: Perfil da cliente + política de crédito
    M-->>A: Regras que se aplicam
    A->>A: Calcula parcela, CET, LTV, renda comprometida
    A-->>C: Não passa no automático — segue para análise
    A->>M: Registra o pedido
    end

    rect rgb(255, 248, 230)
    Note over A,N: 2 · Analista recebe o caso instruído
    N->>A: Abre o caso na fila
    A->>M: Casos históricos parecidos
    M-->>A: Precedentes e seus desfechos
    A-->>N: Recomendação + motivo + política + precedentes
    end

    rect rgb(232, 245, 240)
    Note over A,N: 3 · Negociação de cenários
    N->>A: E se ela aumentar a entrada?
    A-->>N: Passa na política. Parcela cai
    N->>A: E se compartilhar investimentos via Open Finance?
    A-->>N: Risco melhora. Recomendo aprovar
    end

    rect rgb(255, 248, 230)
    Note over C,N: 4 · Decisão e aprendizado
    A->>N: Aguarda aprovação humana
    N->>A: Aprovado
    A->>M: Grava decisão e trilha de auditoria
    A->>M: Indexa o caso como novo precedente
    A-->>C: Aprovado, com as condições
    end
```

**Quatro etapas:** a cliente simula · o analista recebe o caso pronto · negocia cenários ·
decide, e a decisão vira aprendizado.

**Quatro componentes:** cliente · analista · agente de IA · MongoDB Atlas — que guarda
sozinho os dados, a memória da conversa, o histórico e a busca semântica.
