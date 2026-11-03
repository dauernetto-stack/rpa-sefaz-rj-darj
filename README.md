# RPA SEFAZ-RJ — emissão de DARJ em lote

Automação que lê notas pendentes no Google Sheets, agrupa parcelas da mesma NF, preenche o portal da SEFAZ-RJ, confere os valores, valida o PDF, envia ao Google Drive e registra o resultado na planilha.

**Um disparo processa as pendências em sequência.** Cada NF gera uma guia; parcelas consecutivas da mesma NF com alíquotas diferentes são somadas. O lote para na primeira falha.

Esta documentação corresponde ao código revisado em **03/11/2026**. O ZIP desta revisão passou em **116 testes Python e 9 cenários simulados do Apps Script**, sem emissão real. Detalhes das regras e das funções: [DOCUMENTACAO.md](DOCUMENTACAO.md).

## Operação diária

1. Confira as notas reais, datas, parcelas, alíquotas e valores na aba de controle.
2. Deixe `PROC DARJ` vazio apenas nas notas ainda não emitidas e sem número, vencimento, valor ou link de guia.
3. Dispare pela planilha: **🤖 Guias RJ → ▶️ Criar Guias DARJ**. Outra opção é **GitHub → Actions → RPA DARJ-RJ - lote de pendentes → Run workflow → main**.
4. Acompanhe a execução no GitHub. Não edite, ordene ou insira linhas enquanto o lote estiver rodando.
5. Ao concluir cada guia, o robô preenche os dados do DARJ, grava o hyperlink **Link PDF** e marca `X` nas parcelas da NF.

O agendamento está **comentado** no workflow atual: a execução é manual. A mensagem do Apps Script confirma a solicitação ao GitHub, não a conclusão da emissão.

## Regras implementadas

### Valores e encargos

- `DARJ Normal` e `FECP` são os **principais**, calculados na planilha.
- Cada linha deve ter `DARJ Normal + FECP = TOTAL DA GUIA DE ICMS ST`, em centavos exatos e com total positivo. FECP zero é válido.
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

**Não acrescente os encargos às fórmulas dos principais para fazer a validação passar.** J/K/L continuam com o principal; o resultado efetivo fica em `Valor DARJ`.

### Datas

O cálculo usa a data da execução em `America/Sao_Paulo` e os feriados configurados para RJ.

| Situação | Pagamento | Vencimento |
|---|---|---|
| Mês da entrada já encerrado | Dia da execução | Último dia **corrido** do mês da entrada, inclusive sábado/domingo/feriado |
| D+2 permanece no mês da entrada | Execução + 2 dias **corridos**, avançando até dia útil | Mesma data do pagamento |
| D+2 ultrapassa o mês e o fechamento ainda está disponível | Antecipa para o último dia **útil** do mês da entrada | Mesmo fechamento |

Assim, uma nota de outubro executada em **03/11/2026** recebe pagamento **03/11/2026**, vencimento **31/10/2026** e referência **10/2026**. Encargos eventualmente calculados pelo portal são conferidos separadamente.

Não se contam dois dias úteis: numa sexta-feira, sem feriados e sem virada de mês, D+2 cai no domingo e é ajustado para segunda-feira. A referência sempre vem do mês/ano da entrada. O caso de execução após o último dia útil, mas ainda no mesmo mês, está descrito na documentação técnica.

### Mesma NF em várias linhas

Mantenha as parcelas consecutivas, com a mesma NF/série e o mesmo Centro, quando usado. Cada parcela deve ter alíquota diferente. A primeira linha precisa de data; continuações vazias herdam essa data. Datas explicitamente preenchidas precisam coincidir.

`SOMA VALORES` pode fechar o grupo: seus totais são conferidos, sem somá-los novamente nem emitir uma guia para o subtotal. Uma mesma NF/Centro/período em blocos separados ou um grupo parcialmente marcado bloqueia o lote.

## Planilha

Padrão: aba **Página1**, cabeçalhos na **linha 2**. As colunas são encontradas pelos cabeçalhos, não pelas letras.

| Modelo | Cabeçalho | Finalidade |
|---|---|---|
| A | Data entrada | Entrada da nota e referência |
| B | Nº Nota Fiscal | Número e série, como `650874-7` |
| G | ALQ ICMS | Identificação da alíquota das parcelas agrupadas |
| J | DARJ Normal | Principal de ICMS-ST |
| K | FECP | Principal de FECP |
| L | TOTAL DA GUIA DE ICMS ST | Principal total da parcela |
| O | PROC DARJ | Status |
| P | Nº DARJ | Número da guia, preservado como texto |
| Q | Vcto DARJ | Vencimento validado no PDF |
| R | Valor DARJ | Total final validado, incluindo encargos quando houver |
| S | Link DARJ | Hyperlink com rótulo `Link PDF` |

`Centro` é opcional. `ALQ ICMS` é necessária para distinguir parcelas quando uma NF ocupa várias linhas. Demais colunas de cálculo e comparação não são enviadas diretamente pelo robô.

O Google Sheets é lido com `FORMATTED_VALUE`. Arredonde efetivamente os principais nas fórmulas, não apenas na exibição. O código não aplica tolerância de um centavo nem transforma entrada inválida em zero.

## Status e recuperação

| Status | Tratamento |
|---|---|
| Vazio | Candidato à emissão, sujeito às validações |
| PROCESSANDO | Grupo reservado; não liberar durante uma execução |
| X | PDF validado, upload e resultados confirmados |
| ERRO | Falha antes do ponto de possível envio registrado pelo controle |
| REVISAR | Houve tentativa a partir da confirmação do item ou falha posterior; pode existir guia |

Qualquer status preenchido exclui o grupo da seleção normal. Resultados de guia com status vazio também bloqueiam.

**Não apague `X`, `PROCESSANDO` ou `REVISAR` para repetir uma emissão.** Confira o log, o portal e os PDFs existentes. Uma falha no Drive ou na gravação pode acontecer depois de a guia ter sido emitida. Procedimento detalhado: [recuperação de falhas](DOCUMENTACAO.md#recuperação-de-falhas).

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
| ABA_CONTROLE | Ambiente; padrão `Página1` | Aba preferida |
| HEADLESS | Ambiente | `true` executa Chrome sem janela |
| CHROME_BINARY | Ambiente | Caminho do Chrome |
| GOOGLE_CREDENTIALS_B64 | Secret do repositório no GitHub | JSON da conta de serviço codificado em Base64 |
| GITHUB_TOKEN_RJ | Propriedade do Apps Script | Token de disparo do workflow |

`LINHA_CABECALHO = 2` e `CNPJ_RESPONSAVEL = '58248352001201'` são constantes do `bot.py`, não variáveis de ambiente. O Centro não troca o CNPJ: o contribuinte é fixo nesta versão.

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

A configuração atual **usa** `/usr/bin/google-chrome`; ela não instala o navegador. A limpeza de cache é restrita a um caminho conferido do runner. Consulte [infraestrutura](DOCUMENTACAO.md#workflows-e-infraestrutura) antes de migrar de máquina. O código não verifica nem exige um IP fixo; a conectividade da máquina deve ser verificada no ambiente de destino.

Há também um bloqueio local `.darj-rj.lock`. Ele não coordena cópias independentes em máquinas ou pastas diferentes.

## PDFs e diagnósticos

Nome atual:

```text
{Centro_}CE12_DARJ_NF_{NF_com_serie}.pdf
```

Exemplos: `CE12_DARJ_NF_650874-7.pdf` ou `RJ01_CE12_DARJ_NF_650874-7.pdf`. `Centro_` é opcional e sanitizado. **CE12 é texto fixo** no nome atual; o número do DARJ não entra no nome, mas fica na planilha.

O PDF é enviado ao destino configurado e o hyperlink recebe o rótulo **Link PDF**. O upload não cria permissão pública; o acesso depende das permissões do Drive.

Os diagnósticos ficam em `diagnosticos/` e os PDFs em `downloads_darj/`. O workflow tenta anexá-los como `diagnostico-darj-<run_id>-<run_attempt>`, com retenção de **3 dias**. Como o checkout preserva arquivos, o artefato pode incluir registros antigos: confira a hora do `contexto.json`.

## Arquivos auxiliares da atualização

`aplicar_encargos_v3.py` é um aplicador pontual. Não faz parte do fluxo de emissão e não precisa ser executado novamente depois da atualização concluída. O ZIP também contém `.backup_encargos_.../`, com cópias anteriores.

Esses arquivos não são importados pelo robô. Preserve o backup enquanto houver necessidade de recuperação; após conferir e manter o código atual no Git, o aplicador e o backup podem ser retirados do repositório. O `.gitignore` atual não cobre automaticamente essas pastas. Não remova PDFs ou diagnósticos pendentes de revisão junto com eles.

## Documentação completa

[DOCUMENTACAO.md](DOCUMENTACAO.md) descreve os módulos e funções, cálculos, datas, encargos, agrupamento, credenciais, workflows, testes, limites e recuperação de falhas.
