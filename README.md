# RPA SEFAZ-RJ — Emissão automática de DARJ (ICMS-ST)

Robô em Python/Selenium que lê a planilha de controle `DARJ-RJ - Control_List`
no Google Sheets, identifica a nota fiscal do dia anterior (D-1) ainda não
processada, preenche o formulário de emissão de DARJ no Portal de Pagamentos
da SEFAZ-RJ (`https://www1.fazenda.rj.gov.br/portaldepagamentos/`), gera a
guia, salva o PDF na pasta do Google Drive da equipe e grava os dados da guia
de volta na planilha.

**Este robô roda de forma 100% automática no GitHub Actions** (serverless,
sem precisar de nenhuma estação/computador ligado) — veja a seção
[Rodando no GitHub Actions](#rodando-no-github-actions-recomendado--serverless)
abaixo. Também é possível rodar localmente (seção
[Rodando manualmente](#rodando-manualmente)), por exemplo para depurar
visualmente a primeira execução.

## Pré-requisitos

- Python 3.10+
- Google Chrome instalado na máquina que vai rodar o robô
- Uma conta de serviço (service account) do Google Cloud com acesso à API do
  Google Sheets e do Google Drive, **compartilhada** com:
  - a planilha `DARJ-RJ - Control_List`
  - a pasta do Drive onde o PDF da guia deve ser salvo

## Instalação

```bash
git clone https://github.com/dauernetto-stack/rpa-sefaz-rj-darj.git
cd rpa-sefaz-rj-darj
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
```

## Configuração das credenciais do Google

1. No [Google Cloud Console](https://console.cloud.google.com/), crie (ou
   reaproveite) um projeto e ative as APIs **Google Sheets API** e
   **Google Drive API**.
2. Crie uma **Service Account** e gere uma chave no formato JSON.
3. Copie o arquivo `credenciais.example.json` deste repositório para
   `credenciais.json` (este nome é obrigatório e já está no `.gitignore` —
   **nunca** suba esse arquivo pro GitHub) e cole o conteúdo da chave gerada.
4. Na planilha e na pasta do Drive, clique em "Compartilhar" e adicione o
   e-mail da service account (campo `client_email` dentro do JSON) com
   permissão de **Editor**.

## Verificando o acesso antes de rodar

Depois de colocar o `credenciais.json` real na pasta, rode primeiro:

```bash
python testar_acesso.py
```

Esse script não abre navegador nem mexe em nada na SEFAZ - ele só confirma
que a service account consegue ler a planilha e enxergar a pasta do Drive,
e aponta exatamente qual compartilhamento está faltando caso dê erro.

## Rodando manualmente

```bash
python bot.py
```

Na primeira execução real, recomendo rodar **sem headless** (o script já
abre o Chrome visível por padrão) para acompanhar visualmente o preenchimento
e a geração da guia, já que a etapa final (clique em "Gerar DARJ" e extração
dos dados da guia) foi escrita de forma defensiva e pode precisar de ajuste
fino nos seletores/regex — veja os comentários no topo de `bot.py`.

Em caso de erro, o script salva automaticamente `debug_<etapa>.png` e
`debug_<etapa>.html` na pasta do projeto, com um retrato exato da tela no
momento da falha — isso é o primeiro lugar a olhar para diagnosticar.

## Rodando no GitHub Actions (recomendado — serverless)

O repositório já inclui o workflow `.github/workflows/darj-rj.yml`, que roda
o robô automaticamente todo dia útil às 08:00 (horário de Brasília), direto
num runner do GitHub — sem precisar de computador nenhum ligado. Ele também
pode ser disparado manualmente a qualquer momento.

### 1. Gerar o secret da credencial do Google (uma vez só)

O `credenciais.json` real **nunca** vai para o repositório (ele está no
`.gitignore`). Em vez disso, ele é guardado como um *Secret* criptografado do
GitHub e escrito em disco só durante a execução do workflow, dentro do
runner descartável.

Com o arquivo `credenciais.json` (a chave da service account
`guias-dare-dae@rpa-guias-dare-dae.iam.gserviceaccount.com`) em mãos, gere a
versão em base64 (isso evita problemas do GitHub em mascarar segredos com
múltiplas linhas):

```bash
# Linux/Mac:
base64 -w0 credenciais.json

# Windows (PowerShell):
[Convert]::ToBase64String([IO.File]::ReadAllBytes("credenciais.json"))
```

Copie a string gigante que isso gerar (sem quebras de linha).

### 2. Cadastrar o secret no repositório

No GitHub: **Settings → Secrets and variables → Actions → New repository
secret**.

- Nome: `GOOGLE_CREDENTIALS_B64`
- Valor: cole a string em base64 gerada no passo anterior

### 3. Pronto

O workflow já está agendado (`cron: '0 11 * * 1-5'` = 08:00 em Brasília, seg
a sex). Para rodar manualmente a qualquer momento: aba **Actions** do
repositório → workflow "RPA DARJ-RJ (emissão automática)" → **Run workflow**.

Se alguma etapa falhar, o workflow salva automaticamente um artefato
(`debug-<id do run>`) com os screenshots/HTML de debug daquele momento —
baixe esse artefato na própria página do run, em "Actions", pra diagnosticar.

> **Atenção:** o GitHub desativa automaticamente workflows agendados
> (`schedule`) em repositórios sem nenhuma atividade (commits, etc.) por
> 60 dias. Se isso acontecer, basta reativar manualmente na aba Actions.

### Observação sobre downloads em modo headless

O `bot.py` já detecta sozinho quando está rodando dentro do GitHub Actions
(variável de ambiente `GITHUB_ACTIONS`) e liga automaticamente o modo
`--headless=new` do Chrome, incluindo a configuração necessária para permitir
downloads de PDF nesse modo. Rodando localmente, continua abrindo o Chrome
normalmente (com tela), o que ajuda a depurar visualmente.

## Agendamento automático em uma estação local (alternativa)

Se preferir rodar numa máquina própria em vez do GitHub Actions:

### Windows (Agendador de Tarefas)

1. Abra o **Agendador de Tarefas** → "Criar Tarefa Básica".
2. Defina o gatilho para rodar diariamente (ou apenas em dias úteis) no
   horário desejado.
3. Ação: "Iniciar um programa".
   - Programa/script: caminho completo do `python.exe` dentro do `.venv`
     (ex: `C:\caminho\rpa-sefaz-rj-darj\.venv\Scripts\python.exe`)
   - Argumentos: `bot.py`
   - Iniciar em: caminho da pasta do projeto
     (ex: `C:\caminho\rpa-sefaz-rj-darj`)

### Linux/Mac (cron)

```cron
# Roda às 8h, de segunda a sexta
0 8 * * 1-5 cd /caminho/rpa-sefaz-rj-darj && .venv/bin/python bot.py >> log.txt 2>&1
```

## Estrutura da planilha esperada

A aba principal (`Página1`) deve ter, entre outras, as colunas:
`Data entrada`, `Nº Nota Fiscal`, `DARJ Normal`, `FECP`,
`TOTAL DA GUIA DE ICMS ST`, `PROC DARJ`, `Nº DARJ`, `Vcto DARJ`,
`Valor DARJ`, `Link DARJ`.

O robô só processa uma linha quando `Data entrada` é o dia útil anterior
(D-1) e a coluna `PROC DARJ` está vazia — isso evita reprocessar a mesma nota
duas vezes.

## Premissas de negócio assumidas (revisar!)

As regras de datas, CNPJ fixo, Natureza/Produto do formulário e o mapeamento
de colunas da planilha para os campos do site estão documentados nos
comentários no topo do arquivo `bot.py`. Vale revisar com atenção antes de
colocar em produção, especialmente a regra de "Data de Vencimento" quando o
D+2 cai em mês diferente do mês da nota.

## Segurança

- `credenciais.json` nunca deve ir para o controle de versão.
- O script tem travas de auditoria (`BLINDAGEM`) que abortam a execução se
  os valores de ICMS/FECP preenchidos no site não baterem com os valores da
  planilha, para evitar gerar uma guia com valor incorreto.
