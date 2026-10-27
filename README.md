# RPA SEFAZ-RJ — Emissão de DARJ em lote

Automação em Python/Selenium para ler as pendências do Google Sheets, emitir **uma guia DARJ por nota fiscal**, validar o PDF, enviá-lo ao Google Drive e registrar o resultado na planilha.

Quando uma NF possui parcelas com alíquotas diferentes, o robô soma o ICMS e o FECP dessas linhas e emite uma única guia. Um disparo percorre o lote em sequência; não é necessário clicar para cada nota.

**Situação da revisão de 27/10/2026:** execução confirmada pelo responsável após as correções. A validação local desta versão passou em 85 testes Python e 9 cenários simulados do Apps Script.

## Uso no dia a dia

1. Preencha as notas reais na aba de controle e confira datas, valores e alíquotas.
2. Deixe `PROC DARJ` vazio somente nas pendências que ainda não possuem guia emitida nem dados de resultado.
3. Na planilha, use **🤖 Guias RJ → ▶️ Criar Guias DARJ**. Alternativamente, no GitHub, abra **Actions → RPA DARJ-RJ - lote de pendentes → Run workflow → main**.
4. Acompanhe os passos de validação e emissão no GitHub Actions.
5. Ao concluir, as linhas da NF recebem `X`, número, vencimento, valor e o hyperlink **Link PDF**.

O agendamento está comentado no workflow da versão revisada. O funcionamento padrão é por disparo manual, pela planilha ou pelo GitHub. Confira o YAML publicado antes de depender de uma execução automática.

**Não edite, ordene ou insira linhas no lote durante a execução.** O robô relê os dados e interrompe se identificar mudanças que comprometam a conferência.

## Fluxo de uma guia

```text
Google Sheets → validação de todas as pendências → agrupamento por NF
    → PROCESSANDO → preenchimento e auditoria no portal
    → confirmar item → conferir resumo → gerar DARJ uma vez
    → abrir boleto emitido → baixar e validar PDF
    → enviar ao Drive → gravar e conferir resultados → X
```

Se houver falha, o lote é interrompido. As guias concluídas ficam preservadas e as próximas pendências não são emitidas nessa execução.

## Estrutura da planilha

O padrão é a aba **`Página1`**, com os cabeçalhos na **linha 2**. O robô identifica as colunas pelos nomes; as letras abaixo correspondem ao modelo atual.

| Coluna | Cabeçalho | Uso |
|---|---|---|
| A | `Data entrada` | Data real de entrada da nota |
| B | `Nº Nota Fiscal` | Número da NF, com série quando informada, como `214509-1` |
| G | `ALQ ICMS` | Alíquota de cada parcela; obrigatória quando a NF ocupa várias linhas |
| J | `DARJ Normal` | ICMS-ST a emitir |
| K | `FECP` | FECP a emitir; zero é permitido |
| L | `TOTAL DA GUIA DE ICMS ST` | Soma exata de ICMS-ST e FECP da linha |
| O | `PROC DARJ` | Status do processamento |
| P | `Nº DARJ` | Identificador extraído do PDF |
| Q | `Vcto DARJ` | Vencimento conferido no PDF |
| R | `Valor DARJ` | Valor total da guia |
| S | `Link DARJ` | Hyperlink com o texto `Link PDF` |

A coluna `Centro` é opcional. Quando existe e está preenchida, participa da identificação do grupo e do prefixo do nome do PDF.

O robô lê os valores exibidos no Google Sheets. Os valores monetários devem estar consistentes em centavos: **DARJ Normal + FECP = TOTAL DA GUIA DE ICMS ST**, exatamente, e o total precisa ser positivo. O controle não aceita uma tolerância para esconder diferenças nem transforma valores inválidos em zero.

As colunas de base, alíquota, ST, valor de origem e diferença podem apoiar os cálculos da planilha, mas os valores enviados pelo robô são os de `DARJ Normal` e `FECP`. O cálculo tributário da planilha deve estar conferido antes da emissão.

Datas aceitas: `DD.MM.AAAA`, `DD/MM/AAAA` ou `AAAA-MM-DD`. Datas futuras e anos anteriores a 1900 são rejeitados nas pendências. Por exemplo, `26.10.0206` é um erro de ano e não é corrigido automaticamente para 2026.

### Mesma NF com alíquotas diferentes

As parcelas precisam estar em **linhas consecutivas**, com a mesma NF/série e o mesmo Centro, quando utilizado. Cada parcela deve ter uma alíquota diferente. A primeira linha precisa ter data; uma continuação com data vazia herda a data da primeira. Datas preenchidas dentro do grupo precisam coincidir.

Exemplo ilustrativo de estrutura, não destinado à emissão:

| Data entrada | Nº Nota Fiscal | ALQ ICMS | DARJ Normal | FECP | Total |
|---|---|---:|---:|---:|---:|
| 26/10/2026 | 123456-1 | 4% | 100,00 | 10,00 | 110,00 |
| | 123456-1 | 12% | 200,00 | 20,00 | 220,00 |
| | SOMA VALORES | | 300,00 | 30,00 | 330,00 |

O resultado é **uma guia de R$ 330,00**. O número, vencimento, valor total da guia, link e status são gravados nas duas parcelas. Portanto, a coluna `Valor DARJ` repete o total nas linhas de uma mesma NF; somá-la sem deduplicar o número do DARJ duplicaria o total do relatório.

A linha `SOMA VALORES` é opcional e deve ficar imediatamente depois do grupo, com os totais de J, K e L corretos, sem data, status ou dados de guia. Ela é conferida, mas não é somada novamente nem recebe emissão própria.

O controle bloqueia alíquota repetida dentro da mesma NF, grupos parcialmente processados e uma mesma NF/Centro/período dividida em blocos separados. Modelos vazios/zerados e rodapés de total reconhecidos não geram guias.

## Regras de datas

Esta versão preserva a regra do primeiro projeto RJ:

1. **Pagamento:** data da execução + **2 dias corridos**. Se o resultado não for dia útil, avança até o próximo dia útil.
2. **Vencimento:** se o pagamento estiver no mês e ano da entrada, usa a data de pagamento. Caso contrário, calcula o último dia útil do mês da entrada; se esse limite já passou, usa a data da execução.
3. **Período de referência:** mês e ano da entrada da NF, no formato `MM/AAAA`.

Exemplo sem feriados: execução na sexta-feira gera pagamento na segunda-feira. Essa regra é diferente de contar dois dias úteis.

O código usa o fuso `America/Sao_Paulo` e o calendário `holidays.Brazil(subdiv='RJ')` para o ano atual, anterior e seguinte. Feriados municipais ou exceções específicas não são configurados separadamente. Estas são as regras implementadas; mudanças de negócio precisam de validação do responsável e atualização dos testes.

Não existe filtro obrigatório por D-1: o lote considera todas as pendências elegíveis da planilha.

## Significado dos status

| Status | Significado | Conduta |
|---|---|---|
| Vazio | Candidato à emissão, sujeito às validações | Conferir dados antes de disparar |
| `PROCESSANDO` | Grupo reservado pela execução | Não liberar enquanto a execução estiver ativa; se ficou parado, conferir logs e portal |
| `X` | PDF validado, upload e resultados confirmados | Preservar; será ignorado nas próximas execuções |
| `ERRO` | Falha antes do ponto de possível envio registrado pelo controle | Corrigir a causa e conferir o histórico antes de liberar o grupo |
| `REVISAR` | Houve tentativa a partir da confirmação do item ou uma falha posterior | Pode existir guia; conferir documentos e portal antes de qualquer nova emissão |

Qualquer status preenchido impede a seleção normal da linha. Se só parte de um grupo estiver marcada, o lote bloqueia. Uma linha com status vazio, mas com dados de guia, também é bloqueada.

**Não apague `X`, `REVISAR` ou `PROCESSANDO` para testar.** Não use dados inventados no portal real. Uma falha no PDF, no Drive ou na gravação da planilha pode ocorrer depois de o DARJ já ter sido emitido.

## Instalação e validação local

O runner atual usa Linux, Python 3.11 e Google Chrome instalado. Para preparar o ambiente no Codespaces/Linux:

```bash
git clone https://github.com/dauernetto-stack/rpa-sefaz-rj-darj.git
cd rpa-sefaz-rj-darj
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m py_compile bot.py controle_darj.py
.venv/bin/python -m unittest discover -s tests -v
```

Se o projeto já estiver aberto no Codespaces, comece no comando de criação do ambiente. Instalação e testes usam o mesmo Python. As versões das dependências estão em `requirements.txt`, incluindo `pypdf`.

Os testes Python usam serviços simulados. Para testar também o Apps Script, com Node.js disponível:

```bash
node tests/test_appscript.cjs
```

Com as credenciais configuradas, valide a planilha real:

```bash
.venv/bin/python bot.py --validar
```

Esse modo lê e valida a planilha, mostra os grupos, datas, períodos e valores, sem emitir, enviar PDFs ou alterar status. Ele não confirma a disponibilidade do portal nem testa um upload real no Drive.

Para emitir as pendências reais conferidas:

```bash
HEADLESS=true .venv/bin/python bot.py
```

Em um ambiente com interface gráfica, sem `HEADLESS=true` e fora do GitHub Actions, o Chrome abre visível. No Windows, use o Python correspondente em `.venv\Scripts\python.exe`.

## Configurações e credenciais

| Configuração | Local | Uso |
|---|---|---|
| `ID_PLANILHA` | Variável de ambiente; padrão em `bot.py` | Planilha de controle |
| `ID_PASTA_DRIVE` | Variável de ambiente; padrão em `bot.py` | Pasta de destino dos PDFs |
| `ABA_CONTROLE` | Variável de ambiente; padrão `Página1` | Aba preferida, validada pelos cabeçalhos |
| `LINHA_CABECALHO` | Constante em `bot.py`, valor `2` | Linha de cabeçalhos |
| `CNPJ_RESPONSAVEL` | Constante em `bot.py` | Contribuinte usado no formulário e na validação do PDF |
| `HEADLESS` | Variável de ambiente | `true` executa o navegador sem janela |
| `CHROME_BINARY` | Variável de ambiente | Caminho do Chrome; o workflow atual define `/usr/bin/google-chrome` |
| `GOOGLE_CREDENTIALS_B64` | Secret do repositório no GitHub | Credencial Google codificada em Base64 |
| `GITHUB_TOKEN_RJ` | Propriedade do Apps Script | Token para solicitar a execução do workflow |

Para o Google, utilize uma conta de serviço com as APIs Sheets e Drive habilitadas e acesso adequado à planilha e à pasta/Drive de destino. A permissão precisa permitir também criar arquivos no destino.

Em execução local, a chave JSON real deve estar em **`credenciais.json`**, ao lado do `bot.py`. O arquivo `credenciais.example.json` é apenas um modelo. Nunca publique a chave no Git.

No GitHub, cadastre a chave JSON codificada em Base64 em **Settings → Secrets and variables → Actions**, com o nome `GOOGLE_CREDENTIALS_B64`. O workflow recria `credenciais.json` com permissões restritas e contém uma etapa de remoção executada com `if: always()`. Base64 é codificação, não criptografia; mantenha esse conteúdo somente no secret, sem colá-lo em logs ou no README.

O script auxiliar `testar_acesso.py` faz uma conferência básica de leitura da planilha e acesso aos metadados da pasta. Ele ainda usa IDs próprios e a primeira aba (`sheet1`), portanto não substitui `bot.py --validar` nem comprova permissão de upload.

## Apps Script e token do GitHub

1. Na planilha Google, abra **Extensões → Apps Script** e copie o conteúdo de `AppsScript_RJ.gs`.
2. Nas configurações do projeto, em **Propriedades do script**, adicione `GITHUB_TOKEN_RJ` com o token autorizado para o repositório.
3. Salve e recarregue a planilha para carregar o menu **🤖 Guias RJ**. Autorize o script quando solicitado pelo Google.

Para criar um token compatível, acesse **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**. Selecione o proprietário correto, limite o acesso ao repositório `rpa-sefaz-rj-darj` e defina uma expiração. A conta precisa ter acesso ao repositório; dependendo da organização, o token pode exigir aprovação. [Documentação de tokens do GitHub](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).

O endpoint de disparo exige a permissão de repositório **Actions: write**, apresentada na interface como leitura e escrita. Não é necessário conceder acesso administrativo para esse endpoint. [Permissão para workflow dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).

O script atual solicita `darj-rj.yml` no repositório `dauernetto-stack/rpa-sefaz-rj-darj`, com `ref: main`. Não envia número de linha nem depende de um input `linha`. Se alterar proprietário, repositório, branch ou nome do workflow, ajuste o script também.

A mensagem “Lote solicitado” confirma somente o disparo. Acompanhe o resultado no GitHub Actions. Se a resposta for incerta, confira se já existe execução antes de clicar novamente. Não grave o token diretamente no arquivo `.gs`.

## Workflow e infraestrutura

Arquivo: **`.github/workflows/darj-rj.yml`**. Nome exibido: **RPA DARJ-RJ - lote de pendentes**.

Na configuração revisada, o workflow:

1. Baixa o código preservando arquivos locais de diagnóstico.
2. Instala as dependências.
3. Usa o Chrome já instalado e trata o cache antigo de Chromium no caminho conferido.
4. Executa os testes Python.
5. Recupera a credencial temporária Google.
6. Executa `python3 bot.py --validar`.
7. Executa `python3 bot.py` para emitir o lote.
8. Preserva diagnósticos/PDFs em artefato e remove a credencial temporária.

O workflow usa **`runs-on: self-hosted`**. A máquina com o agente precisa estar ligada, online e acessível ao GitHub, Google e portal. A configuração de Chrome/cache contém caminhos específicos do runner atual; ao migrar de máquina, revise-os antes de executar.

Não foi demonstrada uma exigência de **IP fixo** para esta automação. O uso de runner próprio descreve onde o processo roda, não comprova uma regra geral de bloqueio de toda nuvem ou de todo IP dinâmico pelo portal. Se houver bloqueio de acesso, investigue a resposta e a rede daquela execução antes de trocar a infraestrutura.

Há controle de concorrência no GitHub (`emissao-darj-rj`, sem cancelar uma emissão em andamento) e bloqueio local `.darj-rj.lock`. Essas proteções não substituem coordenação caso alguém execute cópias independentes em máquinas diferentes contra a mesma planilha.

Para validar sem emitir durante uma manutenção, use temporariamente:

```yaml
      - name: Executar o lote de pendentes
        if: ${{ false }}
        run: python3 bot.py
```

Mantenha ativo o passo `python3 bot.py --validar`. Retire o `if` somente quando for liberar a emissão real. Um workflow verde com esse passo ignorado não significa que guias foram emitidas.

## PDFs, Drive e diagnósticos

O nome do PDF segue o padrão:

```text
{Centro}_DARJ_NF_{numero_da_nf}_{numero_do_darj}.pdf
```

O prefixo `Centro_` é omitido quando não há Centro. O nome usa a parte numérica da NF antes do hífen; a conferência do conteúdo do PDF considera a NF/série informada. O número do DARJ é preservado como texto para não perder dígitos na planilha.

Antes do upload, o robô confere formato PDF, CNPJ esperado, NF, identificador da guia, vencimento e total; pagamento/validade também são conferidos quando identificados no documento. A extração mantém o layout do PDF e trata os campos das diferentes vias.

O upload usa a pasta configurada. O hyperlink é gravado como **Link PDF**; o código não cria uma permissão pública no arquivo. O acesso de quem clica depende das permissões do Drive.

Arquivos locais:

```text
diagnosticos/linha_<linha>_<etapa>_<id>/
    contexto.json
    aba_0.html
    aba_0.png
    ...
downloads_darj/linha_<linha>_<id>/
    <arquivo>.pdf
```

O workflow tenta salvar ambos no artefato `diagnostico-darj-<run_id>-<run_attempt>`, com retenção configurada de **3 dias**. Baixe os arquivos necessários para conferência antes desse prazo. A retenção do artefato não limpa as pastas locais do runner; monitore o espaço e preserve documentos pendentes de revisão antes de qualquer limpeza.

## Diagnóstico de falhas

| Mensagem ou situação | O que conferir |
|---|---|
| `Período de Referência inválido` | Data real de entrada e ano; log `Entrada`/`Periodo`; valor do campo em `contexto.json`. O preenchimento atual evita a validação intermediária de um campo vazio |
| `ano 0206` ou ano abaixo do mínimo | Corrigir a data na planilha. O robô não adivinha o ano correto |
| `ICMS ... + FECP ... mas total informado` | Conferir J/K/L da linha e arredondamento dos valores em centavos |
| Subtotal diferente da soma | Conferir a linha `SOMA VALORES` e as parcelas, sem incluir o subtotal novamente |
| Grupo parcialmente processado | Conferir todas as linhas da NF e eventual guia existente antes de alterar status |
| `PDF novo não confirmado` | Conferir confirmação do portal, janelas, diagnóstico e download. Não clicar novamente em Gerar DARJ |
| Número/valor/vencimento divergente no PDF | Preservar `REVISAR` e conferir o PDF existente. Não retirar a validação para forçar `X` |
| Falha no Drive | A guia pode já existir; conferir PDF local, pasta e permissões sem emitir novamente |
| `Lote: 0 guias pendentes` | Nenhuma linha elegível; conferir status e resultados. Não há novo upload nessa situação |
| `No module named pypdf` | Instalar `requirements.txt` com o mesmo Python usado para testar/executar |
| `ENOSPC` | Falta de espaço no runner. Conferir disco/cache sem remover PDFs pendentes de revisão |
| HTTP 401/403 no Apps Script | Validade, acesso e permissão do token; aprovação da organização quando aplicável |
| HTTP 404/422 no Apps Script | Repositório, arquivo de workflow, branch e eventuais inputs obrigatórios divergentes |
| Workflow aguardando runner | Conferir agente online e compatibilidade das labels com `runs-on` |

Para investigar, reúna o log completo, a NF/linhas afetadas, o status atual e o artefato daquela execução. Diagnósticos podem conter dados fiscais; compartilhe somente com quem precisa analisá-los.

## Estrutura do projeto

```text
bot.py                       # Portal, navegador, Google, download e diagnóstico
controle_darj.py             # Planejamento, grupos, datas, valores, PDF e status
AppsScript_RJ.gs             # Menu da planilha e disparo do workflow
requirements.txt            # Dependências fixadas
credenciais.example.json    # Modelo sem chave real
testar_acesso.py             # Verificação básica de acesso Google
.github/workflows/darj-rj.yml
tests/
    test_controle.py
    test_grupos_nf.py
    test_planilha_modelo.py
    test_portal.py
    test_periodo.py
    test_datas_entrada.py
    test_appscript.cjs
```

Os testes Python precisam terminar em `.py`. Um arquivo chamado apenas `test_periodo` fica fora da descoberta automática.

## Manutenção e validação das alterações

Antes de publicar alterações de código, execute compilação e testes, revise o diff e valide a planilha sem emitir. Inclua testes para mudanças no agrupamento, datas, extração do PDF ou transições de status. Não remova verificações monetárias nem libere uma emissão incerta como solução para um erro.

Evidências da revisão de 27/10/2026:

- 85 testes Python e 9 cenários do Apps Script passaram localmente.
- A simulação de integração processou 9 guias em 13 linhas; a segunda execução simulada não repetiu emissões.
- A execução operacional posterior foi confirmada pelo responsável.

Os testes locais simulam serviços e não garantem disponibilidade permanente do portal, permissões ou infraestrutura. Arquivos de credenciais, tokens, PDFs e diagnósticos devem permanecer fora do Git, conforme `.gitignore`.
