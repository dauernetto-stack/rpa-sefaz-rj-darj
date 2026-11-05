# RPA SEFAZ-RJ — emissão de DARJ em lote

Automação que lê o relatório na aba Entrada RJ do Google Sheets, recebe ST e FCP prontos, preenche o portal da SEFAZ-RJ, confere principal e encargos, valida o PDF, envia ao Google Drive e registra o resultado.

**Um disparo processa as pendências em sequência.** No relatório direto, cada linha precisa conter uma NF consolidada; repetições bloqueiam para conferência. O agrupamento por alíquota continua disponível somente no modelo antigo. O lote para na primeira falha.

Esta documentação corresponde ao código revisado em **05/11/2026**. O ZIP desta revisão passou em **148 testes Python e 9 cenários simulados do Apps Script**, sem emissão real. Detalhes das regras e das funções: [DOC.md](DOC.md).

## Operação diária

1. Confira as notas reais, Data Lanc, Doc MIRO, Centro e valores na aba Entrada RJ.
2. Deixe `PROC DARJ` vazio apenas nas notas ainda não emitidas e sem número, vencimento, valor ou link de guia.
3. Dispare pela planilha: **🤖 Guias RJ → ▶️ Criar Guias DARJ**. Outra opção é **GitHub → Actions → RPA DARJ-RJ - lote de pendentes → Run workflow → main**.
4. Acompanhe a execução no GitHub. Não edite, ordene ou insira linhas enquanto o lote estiver rodando.
5. Ao concluir cada guia, o robô preenche os dados do DARJ, grava o hyperlink **Link PDF** e marca `X` nas parcelas da NF.

O agendamento está **comentado** no workflow atual: a execução é manual. A mensagem do Apps Script confirma a solicitação ao GitHub, não a conclusão da emissão.

## Regras implementadas

### Valores e encargos

- No relatório direto, `Valor ST` é o principal de ICMS e `Valor FCP` é o principal de FECP: são valores separados.
- O backend calcula `principal total = Valor ST + Valor FCP`, em Decimal, sem fórmulas na planilha. O total precisa ser positivo; FCP zero é válido, mas vazio não é zero.
- Exemplo: `173,35 + 20,07 = 193,42`. Montante e Data Fatur não determinam o principal nem a referência.
- No modelo antigo, permanece a conferência `DARJ Normal + FECP = TOTAL DA GUIA DE ICMS ST`.
- O robô confere os principais informados no portal e a composição de cada imposto: **principal + mora + multa = total**.
- Encargos são aceitos quando o pagamento é posterior ao vencimento. Principal atualizado diferente da planilha, campo vazio, valor negativo ou composição divergente continuam bloqueando.
- O total final auditado acompanha o resumo, a confirmação da emissão e o PDF. Esse é o valor registrado em **Valor DARJ**.

Exemplo observado na revisão:

| Componente | ICMS | FECP |
|---|---:|---:|
| Principal | 1.953,44 | 214,49 |
| Mora | 19,53 | 2,14 |
| Multa | 6,45 | 0,71 |
| Total calculado pelo portal | 1.979,42 | 217,34 |

Principal: **R$ 2.167,93**. Encargos: **R$ 28,83**. Total final: **R$ 2.196,76**. O robô lê os encargos do portal; não calcula percentuais fiscais próprios.

**Não some os encargos em Valor ST/Valor FCP para fazer a validação passar.** Esses campos continuam com o principal; o resultado final fica em `Valor DARJ`.

### Datas

A entrada vem de **Data Lanc**, não de Data Fatur. O cálculo usa a data da execução em `America/Sao_Paulo` e os feriados configurados para RJ.

| Situação | Pagamento | Vencimento |
|---|---|---|
| Mês da entrada já encerrado | Dia da execução | Último dia **corrido** do mês da entrada, inclusive sábado/domingo/feriado |
| D+2 permanece no mês da entrada | Execução + 2 dias **corridos**, avançando até dia útil | Mesma data do pagamento |
| D+2 ultrapassa o mês e o fechamento ainda está disponível | Antecipa para o último dia **útil** do mês da entrada | Mesmo fechamento |

Assim, uma nota com **Data Lanc em outubro**, executada em **03/11/2026** recebe pagamento **03/11/2026**, vencimento **31/10/2026** e referência **10/2026**. Encargos eventualmente calculados pelo portal são conferidos separadamente.

Não se contam dois dias úteis: numa sexta-feira, sem feriados e sem virada de mês, D+2 cai no domingo e é ajustado para segunda-feira. A referência sempre vem do mês/ano da entrada. O caso de execução após o último dia útil, mas ainda no mesmo mês, está descrito na documentação técnica.

### Compatibilidade com o modelo antigo

**Somente no modelo antigo**, mantenha as parcelas consecutivas, com a mesma NF/série e o mesmo Centro, quando usado. Cada parcela deve ter alíquota diferente. A primeira linha precisa de data; continuações vazias herdam essa data. Datas explicitamente preenchidas precisam coincidir.

`SOMA VALORES` pode fechar o grupo: seus totais são conferidos, sem somá-los novamente nem emitir uma guia para o subtotal. Uma mesma NF/Centro/período em blocos separados ou um grupo parcialmente marcado bloqueia o lote.

## Planilha: relatório direto

Aba padrão: **Entrada RJ**, selecionada de forma obrigatória por `ABA_CONTROLE`. Se ela não existir ou estiver inválida, o robô para; não procura pendências em outra aba. O cabeçalho pode estar na linha **1 ou 2**. Cabeçalho duplicado/ambíguo bloqueia.

Cole as 18 colunas do relatório e acrescente as cinco de resultado. No exemplo, elas ficam em S:W; o backend identifica por nome e aceita outra ordem.

| Coluna do exemplo | Cabeçalho | Uso |
|---|---|---|
| A | Doc MIRO | Identificador numérico positivo; conferência de duplicidade por ano da Data Lanc |
| B | Tipo | Precisa ser compra para emitir |
| C | N.Fiscal | NF e série, como 652063-7 |
| D | Data Fatur | Metadado; não define referência/vencimento |
| E | Data Lanc | Data de entrada e mês/ano de referência |
| K | Centro | Obrigatório; identifica o Centro e fornece o prefixo do PDF |
| N | Valor ST | Principal de ICMS |
| O | Valor FCP | Principal de FECP |
| S | PROC DARJ | Status |
| T | Nº DARJ | Número da guia, preservado como texto |
| U | Vcto DARJ | Vencimento validado no PDF |
| V | Valor DARJ | Total final validado, incluindo encargos quando houver |
| W | Link DARJ | Hyperlink com rótulo Link PDF |

Fornecedor, Nome, Região, Montante, Nº pedido, Texto, Usuário, Doc Contab, Doc Materi e FUNEF ficam como informações de origem. Não substituem os campos monetários usados para emitir. O contribuinte do portal continua fixo em CNPJ_RESPONSAVEL.

As antigas colunas Vlr Produtos, IPI, ICMS Normal, ALQ ICMS, BC da ST e ST não são necessárias no relatório direto. Não misture os cabeçalhos novos com Data entrada, DARJ Normal, FECP ou TOTAL DA GUIA DE ICMS ST na mesma aba. O modelo antigo continua suportado em uma aba configurada explicitamente, com suas regras de alíquotas/subtotais.

Exemplo: Data Fatur 28/10/2026 e Data Lanc 03/11/2026 produzem referência **11/2026**. Executando em 05/11/2026, o D+2 ajustado resulta em pagamento e vencimento em **09/11/2026**, considerando o calendário configurado.

**Migração:** preserve o histórico antigo e confira quais NFs do relatório já tiveram guia emitida. Traga seus status e resultados reais, ou importe apenas pendências conferidas. A duplicidade é verificada dentro da aba selecionada; o código não cruza automaticamente as abas históricas. Não importe guias já emitidas como linhas vazias de status.

Os valores são lidos com FORMATTED_VALUE. O relatório precisa fornecer centavos válidos; não há tolerância de um centavo nem conversão silenciosa de campos inválidos em zero. Na aba nova, não há fórmula de total para manter.

## Status e recuperação

| Status | Tratamento |
|---|---|
| Vazio | Candidato à emissão, sujeito às validações |
| PROCESSANDO | Grupo reservado; não liberar durante uma execução |
| X | PDF validado, upload e resultados confirmados |
| ERRO | Falha antes do ponto de possível envio registrado pelo controle |
| REVISAR | Houve tentativa a partir da confirmação do item ou falha posterior; pode existir guia |

Qualquer status preenchido exclui o grupo da seleção normal. Resultados de guia com status vazio também bloqueiam.

**Não apague `X`, `PROCESSANDO` ou `REVISAR` para repetir uma emissão.** Confira o log, o portal e os PDFs existentes. Uma falha no Drive ou na gravação pode acontecer depois de a guia ter sido emitida. Procedimento detalhado: [recuperação de falhas](DOC.md#recuperação-de-falhas).

## Instalação e testes

No terminal do Codespaces/Linux, na raiz do projeto:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m py_compile bot.py controle_darj.py
python -m unittest discover -s tests -v
```

Com Node.js disponível, teste o Apps Script:

```bash
node tests/test_appscript.cjs
```

Os testes usam planilhas, navegador e serviços simulados; não emitem guias reais. No Windows, o interpretador do ambiente fica em `.venv\Scripts\python.exe`.

### Validação da planilha real

Configure a credencial Google e execute:

```bash
python bot.py --validar
```

Esse comando lê e valida a planilha, sem emitir, enviar PDF ou alterar status. Não testa o preenchimento do portal nem comprova upload no Drive.

### Emissão real

Somente depois de conferir as pendências:

```bash
HEADLESS=true python bot.py
```

O lote não exige um comando por linha. Não use dados inventados para testar o portal de produção.

## Configuração

| Nome | Onde configurar | Uso |
|---|---|---|
| ID_PLANILHA | Ambiente; padrão em `bot.py` | Planilha de controle |
| ID_PASTA_DRIVE | Ambiente; padrão em `bot.py` | Pasta dos PDFs |
| ABA_CONTROLE | Ambiente; padrão `Entrada RJ` | Aba obrigatória de operação |
| HEADLESS | Ambiente | `true` executa Chrome sem janela |
| CHROME_BINARY | Ambiente | Caminho do Chrome |
| GOOGLE_CREDENTIALS_B64 | Secret do repositório no GitHub | JSON da conta de serviço codificado em Base64 |
| GITHUB_TOKEN_RJ | Propriedade do Apps Script | Token de disparo do workflow |

`LINHA_CABECALHO = 2` é a referência histórica; a leitura reconhece cabeçalhos nas linhas 1/2. Ela e `CNPJ_RESPONSAVEL = '58248352001201'` são constantes do `bot.py`, não variáveis de ambiente. O Centro não troca o CNPJ: o contribuinte é fixo nesta versão.

Localmente, use a chave real em `credenciais.json`, ao lado do `bot.py`. `credenciais.example.json` é só um modelo. A conta de serviço precisa de acesso à planilha e de condições para criar arquivos no destino do Drive. Não publique chaves ou tokens. Base64 é codificação, não criptografia.

No GitHub, o secret `GOOGLE_CREDENTIALS_B64` recria a credencial durante o job; uma etapa com `if: always()` tenta removê-la ao final.

## Menu da planilha

1. Abra **Extensões → Apps Script** na planilha.
2. Copie `AppsScript_RJ.gs` para o projeto vinculado.
3. Cadastre `GITHUB_TOKEN_RJ` em **Propriedades do script**.
4. Recarregue a planilha e autorize o script quando solicitado.

O token precisa acessar o repositório e permitir **Actions: leitura e escrita**. O script chama `dauernetto-stack/rpa-sefaz-rj-darj`, workflow `darj-rj.yml`, branch `main`, sem input de linha. Se algum desses nomes mudar, atualize o `.gs`.

Referência: [permissões do endpoint de disparo](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event). HTTP 403 exige conferir acesso, permissão e eventual aprovação do token; não exponha o token em logs.

## Runner e execução no GitHub

O workflow usa `runs-on: self-hosted`, limite de 120 minutos e concorrência `emissao-darj-rj`, sem cancelar uma execução em andamento. A máquina precisa estar ligada, com Chrome e acesso aos serviços usados.

A configuração atual **usa** `/usr/bin/google-chrome`; ela não instala o navegador. A limpeza de cache é restrita a um caminho conferido do runner. Consulte [infraestrutura](DOC.md#workflows-e-infraestrutura) antes de migrar de máquina. O código não verifica nem exige um IP fixo; a conectividade da máquina deve ser verificada no ambiente de destino.

Há também um bloqueio local `.darj-rj.lock`. Ele não coordena cópias independentes em máquinas ou pastas diferentes.

## PDFs e diagnósticos

No relatório direto, o nome segue:

```text
{Centro}_DARJ_NF_{NF_com_serie}.pdf
```

Exemplo: `CE12_DARJ_NF_652063-7.pdf`. O prefixo vem do Centro e é sanitizado; não se acrescenta outro CE12 fixo. A série é preservada para distinguir NFs de mesmo número. O número do DARJ fica na planilha, não no nome.

No modelo antigo, permanece o padrão `{Centro_}CE12_DARJ_NF_{NF_com_serie}.pdf`, com Centro opcional. São comportamentos diferentes conforme o layout reconhecido.

O PDF é enviado ao destino configurado e o hyperlink recebe o rótulo **Link PDF**. O upload não cria permissão pública; o acesso depende das permissões do Drive.

Os diagnósticos ficam em `diagnosticos/` e os PDFs em `downloads_darj/`. O workflow tenta anexá-los como `diagnostico-darj-<run_id>-<run_attempt>`, com retenção de **3 dias**. Como o checkout preserva arquivos, o artefato pode incluir registros antigos: confira a hora do `contexto.json`.

## Limpeza dos arquivos do projeto

| Arquivo/pasta do ZIP | Pode retirar? | Efeito |
|---|---|---|
| `.backup_encargos_20261103_151621_b45cb0/` | Sim, após guardar uma cópia de segurança e conferir o código atual no Git | Não é carregado pelo RPA |
| `aplicar_encargos_v3.py` | Sim, após concluir a atualização | Aplicador pontual; não é chamado pelo workflow |
| `testar_acesso.py` | Opcional | Perde apenas o diagnóstico auxiliar; o workflow não o executa |
| `.github/workflows/diagnosticar-espaco-rj.yml` | Opcional | Perde o workflow manual de diagnóstico de disco |
| `credenciais.example.json` | Opcional | Perde o modelo de configuração; não é a credencial real |
| `AppsScript_RJ.gs` | Recomenda-se manter | Fonte do menu da planilha. Apagar do repositório não remove o script já instalado no Google, mas perde a cópia de manutenção |
| `tests/` | Mantenha | O workflow executa os testes Python antes de emitir |
| `bot.py`, `controle_darj.py`, `requirements.txt` | Mantenha | Código e dependências do processo |
| `.github/workflows/darj-rj.yml`, `.gitignore` | Mantenha | Execução pelo GitHub e proteção de arquivos locais |
| `README.md`, `DOC.md` | Mantenha | Operação e manutenção documentadas |

Não confunda `.backup_encargos_.../bot.py` com o `bot.py` da raiz: só a cópia de backup é dispensável. A pasta `.github` inteira não deve ser removida, pois contém o workflow principal.

O `.gitignore` atual não ignora automaticamente os backups. Se já estiverem versionados, adicionar uma regra ao ignore não os retira do Git. Nenhum arquivo do ZIP foi apagado nesta revisão documental.

## Documentação completa

[DOC.md](DOC.md) descreve os módulos e funções, cálculos, datas, encargos, agrupamento, credenciais, workflows, testes, limites e recuperação de falhas.

## Mudanças desta revisão

- Entrada direta de Valor ST/Valor FCP e total calculado no Python.
- Referência pela Data Lanc; Data Fatur é metadado.
- Aba Entrada RJ obrigatória, cabeçalho nas linhas 1/2 e sem fallback para histórico.
- Doc MIRO e Tipo conferidos também nas releituras durante a execução.
- NF consolidada por linha no relatório direto; agrupamento por alíquota mantido apenas no modelo antigo.
- Prefixo do PDF dinâmico pelo Centro no relatório direto.
- 148 testes Python; Apps Script e dependências mantidos.
- As linhas `# if: ...` presentes no YAML são comentários: a etapa de emissão está **ativa**, sujeita ao sucesso das etapas anteriores. O agendamento permanece comentado.
