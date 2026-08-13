# Storytelling da demo — da intenção à contratação

Roteiro validado para uma apresentação de **7 a 9 minutos**. A história é curta, mas cria
tensão real: um score alto não garante aprovação, uma solução aparentemente óbvia é
matematicamente impossível, um dado útil não pode ser usado sem consentimento e a decisão
continua sendo humana.

## Abertura — 30 segundos

> Mariana é cliente desde 2016 e encontrou um imóvel de R$ 400 mil. Ela tem R$ 100 mil para
> a entrada, mas não quer comprometer toda a reserva. Do outro lado está Carlos: ele precisa
> encontrar uma estrutura responsável sem transformar cada exceção em horas de trabalho
> manual.

Abra `http://localhost:3000`. Antes de clicar, pergunte à plateia:

> Com score 782, vocês esperariam aprovação automática? O que ainda poderia impedir?

## Cena 1 — a surpresa da cliente

Na tela de Mariana, mantenha os valores padrão e clique em **Simular**:

- imóvel: **R$ 400.000**;
- entrada: **R$ 100.000**;
- prazo: **360 meses**;
- finalidade: **Compra de imóvel residencial**.

Resultado esperado: **análise manual**, parcela de **R$ 2.658,78**, LTV de **75%** e DTI de
**35,8%**. Diga:

> O modelo interpreta e explica; quem calculou parcela, LTV e DTI foi código determinístico.
> E a decisão cita as políticas que realmente dispararam a revisão.

Digite exatamente:

> Meu score é 782. Por que isso não bastou para uma aprovação automática?

O assistente deve explicar que score é apenas um fator: LTV acima de 70% e DTI acima de 30%
impedem o automático, mas o caso não foi recusado.

Faça a pergunta-surpresa:

> E a Selic de hoje: você consegue consultar ao vivo e dizer se ela muda esta proposta?

O comportamento correto é reconhecer que não possui cotação em tempo real e não inventar
uma relação que não consta nas políticas da simulação.

## Cena 2 — um copiloto que também sabe dizer “não”

Abra **Analista**, selecione o caso de Mariana no topo da fila e destaque que cliente e
analista trabalham sobre o **mesmo `thread_id`**. Após o dossiê, pergunte:

> O score é alto. Qual variável realmente impede a aprovação automática e qual alavanca não
> depende de aumentar a renda?

Em seguida, imponha uma restrição deliberadamente difícil:

> Sem alterar a entrada nem o valor financiado, leve o DTI a 30% mexendo somente no prazo.

Resultado esperado: o agente deve dizer que o alvo é **inviável**. O melhor prazo permitido
pela idade é **524 meses**, ainda com DTI de **34,9%** e LTV de **75%**. Pergunte à plateia:

> Um bom copiloto precisa sempre encontrar uma saída — ou precisa provar quando a saída pedida
> não existe?

## Cena 3 — dado disponível não é dado autorizado

Digite:

> A cliente diz ter investimentos em outra instituição. O que conseguimos verificar sem
> presumir que houve consentimento?

Resultado esperado: **consentimento não concedido**; nenhum ativo, saldo ou mitigante deve
ser usado ou exposto. Diga:

> Governança não é um aviso no rodapé. Sem consentimento, o próprio dado deixa de atravessar a
> fronteira da ferramenta.

Pergunta para a plateia:

> Sem consentimento, o saldo deveria ser apenas mascarado — ou nem sequer devolvido ao agente?

## Cena 4 — a contraproposta explicável

Mariana aceita considerar um imóvel menor para preservar os R$ 100 mil de entrada. Digite:

> Mantendo a entrada de R$ 100 mil e o prazo de 360 meses, reduza somente o valor financiado
> até o DTI chegar a 30%.

Resultado esperado:

- financiamento: **R$ 226.795,20**;
- imóvel implícito: **R$ 326.795,20**;
- parcela: **R$ 2.009,99**;
- LTV: **69,4%**;
- DTI: **30%**;
- parecer calculado: **aprovação automática**.

Clique em **Aprovar** e depois em **Confirmar Aprovado**. Mostre que o agente apenas propõe;
o registro definitivo só acontece após a confirmação humana.

## Cena 5 — fechar o ciclo

Volte a **Cliente**. O sino deve sinalizar a nova decisão. Abra a notificação e confirme que
Mariana vê apenas a conversa destinada a ela, não o raciocínio interno de Carlos. Clique em
**Contratar**.

Resultado esperado: o botão muda para **Proposta contratada**, o aceite sobrevive ao reload e
o status aprovado não é recalculado nem substituído.

Feche com:

> Uma única jornada saiu da intenção, atravessou cálculo e política, reconheceu um limite,
> protegeu um dado sem consentimento, recebeu uma decisão humana e terminou em contratação.
> O modelo conversa e pesquisa; Python calcula; o grafo controla; o MongoDB preserva estado,
> evidência e memória.

## Checklist de 60 segundos antes da demo

- `http://localhost:8000/api/health` retorna `connected: true` e índices consultáveis.
- A simulação padrão de R$ 400 mil / R$ 100 mil / 360 meses cai em análise manual.
- O caso novo aparece no topo de **Pendentes**.
- O navegador começa na tela **Nova simulação**, sem histórico aberto.
- Se o tempo apertar, pule a pergunta sobre Selic; não pule a impossibilidade matemática nem
  o consentimento de Open Finance.
