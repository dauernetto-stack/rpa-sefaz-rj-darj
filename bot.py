import os
import re
import time
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

try:
    import holidays
except ImportError:
    raise ImportError(
        "O pacote 'holidays' não está instalado. Rode: pip install holidays "
        "(ou: pip install --break-system-packages holidays)"
    )

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ==============================================================================
# PREMISSAS ASSUMIDAS NESTE SCRIPT (confirmadas ou inferidas na conversa)
# ==============================================================================
# - CNPJ fixo da Cobra Rolamentos: 58248352001201. O site preenche sozinho
#   Inscrição Estadual-RJ e Razão Social a partir do CNPJ (botão "Confirmar").
# - Produto = "Peças, Partes e Acessórios para Veículos Automotores" (value 442).
# - Natureza = "Substituição Tributária por Operação / Outros" (value 4).
# - ICMS Informado  = coluna "DARJ Normal" da planilha.
# - FECP Informado  = coluna "FECP" da planilha.
# - Período de Referência (mm/aaaa) = mês/ano da coluna "Data entrada" (regra
#   não alterada pelo seu último pedido).
# - Data de Pagamento = D+2 (corridos, a partir de hoje), ajustado para a
#   frente até cair em dia útil (não sábado/domingo e não feriado nacional ou
#   do RJ, via pacote `holidays`).
# - Data de Vencimento = mesma regra de D+2 dia útil acima, MAS com uma
#   restrição adicional que você pediu: se esse D+2 cair em mês diferente do
#   mês da "Data entrada", o vencimento é puxado para dentro do mês da entrada
#   (uso o último dia útil daquele mês); se isso for impossível (o mês da
#   entrada já ficou inteiramente no passado em relação a hoje), uso a data
#   atual como vencimento. Ver calcular_datas_pagamento_vencimento() abaixo -
#   é minha interpretação da regra que você descreveu; revise com atenção.
# - PDF da guia gerada é enviado para a pasta do Google Drive:
#   https://drive.google.com/drive/folders/1UApSGUMncRgU15q7UH1MGT6EKrEskYim
#   (mesma pasta onde está a planilha de controle).
# - A etapa final (clicar em "Gerar DARJ" e extrair Nº/Vencimento/Valor/Link da
#   guia gerada) foi escrita de forma defensiva: eu NÃO cheguei a clicar em
#   "Gerar DARJ" de verdade durante a exploração (para não emitir uma guia real
#   com dados de teste), então essa extração pode precisar de ajuste fino na
#   primeira execução real. Ela já salva screenshot/HTML de debug em caso de
#   erro para facilitarmos o ajuste.
# ==============================================================================


def extrair_float_limpo(val_raw):
    """Converte qualquer representação vinda da planilha (float, int, string BRL) para float."""
    if val_raw is None or val_raw == '':
        return 0.0
    if isinstance(val_raw, (int, float)):
        return float(val_raw)
    s = str(val_raw).strip().replace("R$", "").replace(" ", "")
    if not s:
        return 0.0
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    elif '.' in s:
        partes = s.split('.')
        if not (len(partes) == 2 and len(partes[1]) in (1, 2)):
            s = s.replace('.', '')
    try:
        return float(s)
    except ValueError:
        return 0.0


def formatar_valor_virgula(valor_float):
    """Formata float como string BR sem separador de milhar, ex: 146.85 -> '146,85'."""
    return f"{valor_float:.2f}".replace('.', ',')


def parse_data_entrada(data_str):
    """A coluna 'Data entrada' vem no formato dd.mm.aaaa (ex: 16.10.2026)."""
    return pd.to_datetime(str(data_str).strip(), format='%d.%m.%Y')


def ajustar_para_dia_util(data, feriados):
    """Avança a data dia a dia até cair em dia útil (não fim de semana, não feriado)."""
    while data.weekday() >= 5 or data.date() in feriados:
        data += pd.Timedelta(days=1)
    return data


def ultimo_dia_util_do_mes(ano, mes, feriados):
    """Retorna o último dia útil (não fim de semana, não feriado) de um mês/ano."""
    ultimo_dia_calendario = pd.Timestamp(year=ano, month=mes, day=1) + pd.offsets.MonthEnd(0)
    d = ultimo_dia_calendario
    while d.weekday() >= 5 or d.date() in feriados:
        d -= pd.Timedelta(days=1)
    return d


def calcular_datas_pagamento_vencimento(dt_entrada, hoje, feriados):
    """
    Data de Pagamento = D+2 (corridos a partir de hoje), ajustado para a frente
    até cair em dia útil.

    Data de Vencimento = o mesmo D+2 dia útil acima, MAS se esse resultado cair
    em um mês diferente do mês da "Data entrada", é puxado de volta para dentro
    do mês da entrada (último dia útil daquele mês). Se nem isso for possível
    (o mês da entrada já ficou totalmente no passado), usa a data atual (hoje)
    como vencimento.
    """
    candidato_d_mais_2 = ajustar_para_dia_util(hoje.normalize() + pd.Timedelta(days=2), feriados)

    data_pagamento = candidato_d_mais_2

    if (candidato_d_mais_2.year, candidato_d_mais_2.month) == (dt_entrada.year, dt_entrada.month):
        data_vencimento = candidato_d_mais_2
    else:
        venc_dentro_mes_entrada = ultimo_dia_util_do_mes(dt_entrada.year, dt_entrada.month, feriados)
        if venc_dentro_mes_entrada.normalize() >= hoje.normalize():
            data_vencimento = venc_dentro_mes_entrada
        else:
            # Mês da entrada já passou inteiramente - usa a data atual como fallback.
            data_vencimento = hoje.normalize()

    return data_pagamento, data_vencimento


def dump_debug(driver, tag):
    """Salva screenshot + HTML da página no momento da falha, para diagnóstico."""
    driver.save_screenshot(f"debug_{tag}.png")
    with open(f"debug_{tag}.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print(f"   -> Screenshot e HTML salvos como debug_{tag}.png / debug_{tag}.html")


def enviar_pdf_para_drive(caminho_arquivo, folder_id, credenciais):
    """Realiza o upload do PDF gerado para a pasta do Google Drive."""
    try:
        drive_service = build('drive', 'v3', credentials=credenciais)
        file_metadata = {
            'name': os.path.basename(caminho_arquivo),
            'parents': [folder_id]
        }
        media = MediaFileUpload(caminho_arquivo, mimetype='application/pdf')
        arquivo_criado = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True,
            supportsTeamDrives=True
        ).execute()
        print(f"PDF enviado com sucesso para o Google Drive! ID: {arquivo_criado.get('id')}")
        return True
    except Exception as e:
        print(f"Erro ao enviar o PDF para o Google Drive: {e}")
        return False


def fechar_modal_informacao_se_existir(driver, timeout=2):
    """Fecha o modal customizado 'Informação' (não é um alert nativo do browser)."""
    try:
        btn_ok = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'dialog') or contains(.,'Informação')]//button[normalize-space(.)='Ok']"))
        )
        btn_ok.click()
        time.sleep(0.3)
    except Exception:
        pass


# ==============================================================================
# CONSTANTES FIXAS
# ==============================================================================

ID_PLANILHA = "1U0HgRTfVIoGo3Jrr9-62ItBZumgJP77QH4SGa_lZ9jI"
ID_PASTA_DRIVE = "1UApSGUMncRgU15q7UH1MGT6EKrEskYim"
CNPJ_RESPONSAVEL = "58248352001201"
PRODUTO_TEXTO = "Peças, Partes e Acessórios para Veículos Automotores"
NATUREZA_TEXTO = "Substituição Tributária por Operação / Outros"

# ==============================================================================
# FASE 1: LEITURA E VALIDAÇÃO DE DADOS DA PLANILHA GOOGLE
# ==============================================================================

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", scope)
client = gspread.authorize(creds)

planilha = client.open_by_key(ID_PLANILHA).sheet1

# Lemos os valores "crus" (em vez de usar get_all_records) por dois motivos:
# 1) a planilha tem uma linha de TÍTULO na linha 1 ("Pagamento Antecipado
#    pela COBRA" + "Cod. 023-0"/"Cod. 750-1") e os cabeçalhos de coluna de
#    verdade ("Data entrada", "Nº Nota Fiscal", ...) só aparecem na linha 2;
# 2) além disso há colunas extras sem cabeçalho (células em branco) à
#    direita dos dados reais - o gspread trava com "header row contains
#    duplicates: ['']" quando há mais de uma coluna com cabeçalho vazio.
_todos_valores = planilha.get_all_values(value_render_option='FORMATTED_VALUE')
_LINHA_CABECALHO = 2  # cabeçalhos reais das colunas ficam na linha 2 da planilha
_cabecalhos_brutos = _todos_valores[_LINHA_CABECALHO - 1] if len(_todos_valores) >= _LINHA_CABECALHO else []

# Deduplica/preenche cabeçalhos vazios ou repetidos para podermos montar os
# registros como dicionários sem conflito de chave.
_cabecalhos_unicos = []
_vistos = {}
for _idx, _h in enumerate(_cabecalhos_brutos):
    _h = str(_h).strip()
    if _h == '':
        _h = f'_coluna_vazia_{_idx + 1}'
    if _h in _vistos:
        _vistos[_h] += 1
        _h = f'{_h}_{_vistos[_h]}'
    else:
        _vistos[_h] = 0
    _cabecalhos_unicos.append(_h)

registros = []
for _linha in _todos_valores[_LINHA_CABECALHO:]:
    # ignora linhas totalmente em branco
    if not any(str(v).strip() for v in _linha):
        continue
    _linha_completa = _linha + [''] * (len(_cabecalhos_unicos) - len(_linha))
    registros.append(dict(zip(_cabecalhos_unicos, _linha_completa)))

hoje = pd.Timestamp.today()
d_menos_1 = hoje - pd.offsets.BDay(1)

linha_alvo_index = None
dados_alvo = None
dt_entrada_alvo = None

for i, registro in enumerate(registros):
    data_entrada_raw = registro.get('Data entrada')
    if not data_entrada_raw:
        continue
    try:
        dt_entrada = parse_data_entrada(data_entrada_raw)
    except Exception:
        continue
    if dt_entrada.date() == d_menos_1.date() and str(registro.get('PROC DARJ', '')).strip() == '':
        linha_alvo_index = i + _LINHA_CABECALHO + 1
        dados_alvo = registro
        dt_entrada_alvo = dt_entrada
        break

if not dados_alvo:
    print(f"Nenhum registro pendente para a data {d_menos_1.strftime('%d.%m.%Y')}. Encerrando.")
    exit()

print(f"Registro encontrado na linha {linha_alvo_index}. Nota Fiscal: {dados_alvo.get('Nº Nota Fiscal')}")

cabecalhos = [str(v).strip() for v in planilha.row_values(_LINHA_CABECALHO)]


def encontrar_coluna(termos_possiveis, nome_padrao):
    for termo in termos_possiveis:
        for idx, col_head in enumerate(cabecalhos):
            if termo.strip().upper() == col_head.strip().upper():
                return idx + 1
    raise Exception(f"Coluna '{nome_padrao}' não encontrada. Cabeçalhos disponíveis: {cabecalhos}")


col_proc_darj = encontrar_coluna(['PROC DARJ'], 'PROC DARJ')
planilha.update_cell(linha_alvo_index, col_proc_darj, 'X')
print("Linha marcada com 'X' em PROC DARJ. Iniciando o processamento...")

# BLINDAGEM: valores de ICMS e FECP vindos da planilha
nota_fiscal_raw = str(dados_alvo.get('Nº Nota Fiscal', ''))
nota_fiscal = nota_fiscal_raw.split('-')[0].strip()

darj_normal_float = extrair_float_limpo(dados_alvo.get('DARJ Normal'))
fecp_float = extrair_float_limpo(dados_alvo.get('FECP'))
total_guia_float = extrair_float_limpo(dados_alvo.get('TOTAL DA GUIA DE ICMS ST'))

if darj_normal_float <= 0 and fecp_float <= 0:
    raise ValueError("❌ ERRO CRÍTICO: DARJ Normal e FECP vieram zerados/ inválidos. Abortando!")

# Cross-check: soma deve bater com o total da guia (com tolerância de 1 centavo)
soma_calculada = round(darj_normal_float + fecp_float, 2)
if total_guia_float > 0 and abs(soma_calculada - total_guia_float) > 0.01:
    raise ValueError(
        f"❌ ERRO CRÍTICO: DARJ Normal ({darj_normal_float:.2f}) + FECP ({fecp_float:.2f}) = "
        f"{soma_calculada:.2f}, que não bate com TOTAL DA GUIA DE ICMS ST ({total_guia_float:.2f}). "
        f"Operação abortada por segurança!"
    )

icms_informado_str = formatar_valor_virgula(darj_normal_float)
fecp_informado_str = formatar_valor_virgula(fecp_float)

periodo_referencia_str = dt_entrada_alvo.strftime('%m/%Y')

anos_feriados = sorted({hoje.year, dt_entrada_alvo.year, hoje.year + 1})
feriados_rj = holidays.Brazil(subdiv='RJ', years=anos_feriados)

dt_pagamento, dt_vencimento = calcular_datas_pagamento_vencimento(dt_entrada_alvo, hoje, feriados_rj)
dt_pagamento_str = dt_pagamento.strftime('%d/%m/%Y')
dt_vencimento_str = dt_vencimento.strftime('%d/%m/%Y')

print(f"-> Nota Fiscal: {nota_fiscal}")
print(f"-> ICMS Informado (DARJ Normal): R$ {icms_informado_str}")
print(f"-> FECP Informado: R$ {fecp_informado_str}")
print(f"-> Período de Referência: {periodo_referencia_str}")
print(f"-> Data de Pagamento calculada (D+2 dia útil): {dt_pagamento_str}")
print(f"-> Data de Vencimento calculada: {dt_vencimento_str}")

# ==============================================================================
# FASE 2: CONFIGURAÇÃO DO NAVEGADOR
# ==============================================================================

diretorio_download = os.path.abspath("downloads_darj")
if not os.path.exists(diretorio_download):
    os.makedirs(diretorio_download)

# Roda headless automaticamente dentro do GitHub Actions (ou se HEADLESS=true
# for setado manualmente), e com tela visível em execução local normal.
RODANDO_HEADLESS = os.getenv("HEADLESS", "").lower() == "true" or os.getenv("GITHUB_ACTIONS") == "true"

opcoes = Options()
opcoes.add_argument("--disable-blink-features=AutomationControlled")
opcoes.add_experimental_option("excludeSwitches", ["enable-automation"])
opcoes.add_experimental_option('useAutomationExtension', False)
opcoes.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

if RODANDO_HEADLESS:
    print("   (Executando em modo headless - sem interface gráfica, como no GitHub Actions)")
    opcoes.add_argument("--headless=new")
    opcoes.add_argument("--no-sandbox")
    opcoes.add_argument("--disable-dev-shm-usage")
    opcoes.add_argument("--window-size=1920,1080")
else:
    opcoes.add_argument("--start-maximized")

prefs = {
    "download.default_directory": diretorio_download,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "plugins.always_open_pdf_externally": True
}
opcoes.add_experimental_option("prefs", prefs)

servico = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=servico, options=opcoes)

driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
    'source': "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
})

# Necessário para habilitar downloads em modo --headless=new (bloqueados por padrão).
driver.execute_cdp_cmd("Page.setDownloadBehavior", {
    "behavior": "allow",
    "downloadPath": diretorio_download
})

wait = WebDriverWait(driver, 20)

# ==============================================================================
# FASE 3: NAVEGAÇÃO E PREENCHIMENTO DO FORMULÁRIO
# ==============================================================================

try:
    print("1. Acessando o Portal de Pagamentos da SEFAZ-RJ...")
    driver.get("https://www1.fazenda.rj.gov.br/portaldepagamentos/")

    print("2. Selecionando Tipo de Pagamento = ICMS/FECP...")
    select_tipo_pagamento = Select(wait.until(EC.element_to_be_clickable((By.ID, "tipoPagamentoLista"))))
    select_tipo_pagamento.select_by_value("1")
    time.sleep(1)

    # Tipo de Documento = DARJ já vem selecionado por padrão, mas garantimos:
    radio_darj = wait.until(EC.element_to_be_clickable((By.ID, "rdgDarj")))
    if not radio_darj.is_selected():
        radio_darj.click()

    print(f"2.1. Ajustando Data de Pagamento para {dt_pagamento_str} (D+2 dia útil)...")
    driver.find_element(By.ID, "btnAlterarDataPagamento").click()
    fechar_modal_informacao_se_existir(driver)
    campo_data_pagamento = wait.until(EC.element_to_be_clickable((By.ID, "txtDataPagamento")))
    campo_data_pagamento.clear()
    campo_data_pagamento.send_keys(dt_pagamento_str)
    time.sleep(0.3)

    print("3. Selecionando Natureza = 'Substituição Tributária por Operação / Outros'...")
    select_natureza = Select(wait.until(EC.element_to_be_clickable((By.ID, "slcNaturezaLista"))))
    select_natureza.select_by_visible_text(NATUREZA_TEXTO)
    time.sleep(1)

    print("4. Selecionando Produto...")
    select_produto = Select(wait.until(EC.element_to_be_clickable((By.ID, "slcListaProduto"))))
    select_produto.select_by_visible_text(PRODUTO_TEXTO)
    time.sleep(0.5)

    print("5. Preenchendo CNPJ e confirmando dados cadastrais...")
    campo_cnpj = wait.until(EC.element_to_be_clickable((By.ID, "txtCnpjCpf")))
    campo_cnpj.clear()
    campo_cnpj.send_keys(CNPJ_RESPONSAVEL)
    driver.find_element(By.ID, "btnConfirmar").click()

    # Auditoria: confirma que o lookup por CNPJ realmente trouxe Inscrição Estadual/Razão Social
    wait.until(lambda d: d.find_element(By.ID, "txtInscEstadual").get_attribute("value").strip() != "")
    insc_estadual_lida = driver.find_element(By.ID, "txtInscEstadual").get_attribute("value").strip()
    razao_social_lida = driver.find_element(By.ID, "txtNomeRazaoSocial").get_attribute("value").strip()
    print(f"   -> Inscrição Estadual-RJ: {insc_estadual_lida} | Razão Social: {razao_social_lida}")

    if not insc_estadual_lida or not razao_social_lida:
        dump_debug(driver, "erro_lookup_cnpj")
        raise Exception("❌ ERRO CRÍTICO: O CNPJ não retornou Inscrição Estadual/Razão Social. Abortando!")

    print("6. Preenchendo Período de Referência...")
    campo_periodo = wait.until(EC.element_to_be_clickable((By.ID, "txtPeriodo")))
    campo_periodo.clear()
    campo_periodo.send_keys(periodo_referencia_str)
    time.sleep(0.3)

    print("7. Habilitando e preenchendo Data de Vencimento...")
    driver.find_element(By.ID, "btnAlterarData").click()
    fechar_modal_informacao_se_existir(driver)

    campo_vencimento = wait.until(EC.element_to_be_clickable((By.ID, "txtDataVencimento")))
    campo_vencimento.clear()
    campo_vencimento.send_keys(dt_vencimento_str)
    time.sleep(0.3)

    print("8. Preenchendo Informações Complementares...")
    campo_info = driver.find_element(By.ID, "txtJustificativa")
    campo_info.clear()
    campo_info.send_keys(f"NF {nota_fiscal_raw}")

    print("9. Preenchendo ICMS Informado...")
    campo_icms = wait.until(EC.element_to_be_clickable((By.ID, "txtIcmsInformado")))
    campo_icms.clear()
    campo_icms.send_keys(icms_informado_str)
    driver.find_element(By.ID, "okIcms").click()

    wait.until(lambda d: d.find_element(By.ID, "txtTotalIcms").get_attribute("value").strip() != "")

    print("10. Preenchendo FECP Informado...")
    campo_fecp = wait.until(EC.element_to_be_clickable((By.ID, "txtFecpInformado")))
    campo_fecp.clear()
    campo_fecp.send_keys(fecp_informado_str)
    driver.find_element(By.ID, "okFecp").click()

    wait.until(lambda d: d.find_element(By.ID, "txtTotalFecp").get_attribute("value").strip() != "")

    # ==========================================================================
    # BLINDAGEM: AUDITORIA PÓS-PREENCHIMENTO
    # ==========================================================================
    total_icms_dom = extrair_float_limpo(driver.find_element(By.ID, "txtTotalIcms").get_attribute("value"))
    total_fecp_dom = extrair_float_limpo(driver.find_element(By.ID, "txtTotalFecp").get_attribute("value"))

    print("🔒 AUDITORIA DE SEGURANÇA PRÉ-CONFIRMAÇÃO:")
    print(f"   -> ICMS (DARJ Normal) planilha: R$ {darj_normal_float:.2f} | Total ICMS no portal: R$ {total_icms_dom:.2f}")
    print(f"   -> FECP planilha: R$ {fecp_float:.2f} | Total FECP no portal: R$ {total_fecp_dom:.2f}")

    if abs(total_icms_dom - darj_normal_float) > 0.01 or abs(total_fecp_dom - fecp_float) > 0.01:
        dump_debug(driver, "erro_divergencia_valor")
        raise ValueError(
            "❌ BLOQUEIO CRÍTICO DE SEGURANÇA: Os valores calculados pelo portal não conferem com a planilha! "
            "A emissão da guia foi INTERROMPIDA para evitar prejuízos financeiros!"
        )

    print("✅ VALIDAÇÃO DE SEGURANÇA CONCLUÍDA: Valores aprovados!")

    print("11. Clicando em 'Confirmar item'...")
    btn_confirmar_item = wait.until(EC.element_to_be_clickable((
        By.XPATH, "//input[@type='button' and contains(@value,'Confirmar item')]"
    )))
    btn_confirmar_item.click()
    time.sleep(1.5)
    fechar_modal_informacao_se_existir(driver)

    # ==========================================================================
    # FASE 4: RESUMO DE PAGAMENTO E GERAÇÃO DO DARJ
    # ==========================================================================
    print("12. Aguardando tela de Resumo de pagamento...")
    wait.until(EC.presence_of_element_located((
        By.XPATH, "//*[contains(text(),'Resumo de pagamento') or contains(text(),'Gerar DARJ')]"
    )))

    # Marca a checkbox do item, se existir
    try:
        checkboxes = driver.find_elements(By.XPATH, "//table//input[@type='checkbox']")
        for cb in checkboxes:
            if not cb.is_selected():
                driver.execute_script("arguments[0].click();", cb)
    except Exception:
        pass

    dump_debug(driver, "resumo_pagamento_pre_geracao")  # registro para auditoria, sempre salvo

    print("13. Clicando em 'Gerar DARJ'...")
    btn_gerar_darj = wait.until(EC.element_to_be_clickable((
        By.XPATH, "//input[@type='button' and contains(@value,'Gerar DARJ')] | //a[contains(.,'Gerar DARJ')]"
    )))
    btn_gerar_darj.click()
    time.sleep(3)

    # ==========================================================================
    # FASE 5: EXTRAÇÃO DOS DADOS DA GUIA GERADA
    # ==========================================================================
    print("14. Extraindo dados da guia DARJ gerada...")

    # Pode abrir em nova aba/janela - trata ambos os casos
    if len(driver.window_handles) > 1:
        driver.switch_to.window(driver.window_handles[-1])

    time.sleep(2)

    dados_darj = driver.execute_script("""
        var textoPagina = document.body.innerText;
        var matchNum = textoPagina.match(/N[úu]mero (?:do )?(?:Documento|DARJ):?\\s*([\\w\\-\\.\\/]+)/i);
        var matchVcto = textoPagina.match(/(?:Vencimento|Validade):?\\s*([\\d\\/]+)/i);
        var matchValor = textoPagina.match(/Valor(?: Total)?:?\\s*(?:do Documento)?:?\\s*(R\\$)?\\s*([\\d\\.,]+)/i);
        return {
            numDarj: matchNum ? matchNum[1].trim() : '',
            vencimento: matchVcto ? matchVcto[1].trim() : '',
            valor: matchValor ? matchValor[2].trim() : ''
        };
    """)

    link_darj_atual = driver.current_url
    print(f"Dados extraídos -> Nº DARJ: {dados_darj['numDarj']}, Vencimento: {dados_darj['vencimento']}, Valor: {dados_darj['valor']}")

    if not dados_darj['numDarj']:
        dump_debug(driver, "extracao_numero_darj_falhou")
        print("⚠️ Não foi possível localizar automaticamente o Nº do DARJ na página. "
              "Verifique debug_extracao_numero_darj_falhou.png/html e ajuste os seletores/regex acima.")

    # Tenta localizar um link/botão de download do PDF do boleto
    try:
        link_pdf = driver.find_element(
            By.XPATH,
            "//a[contains(@href,'.pdf') or contains(@onclick,'pdf') or contains(.,'Imprimir') or contains(.,'Download')] "
            "| //img[contains(@src,'barcode') or contains(@alt,'Imprimir')]"
        )
        driver.execute_script("arguments[0].click();", link_pdf)
        time.sleep(4)
    except Exception:
        print("⚠️ Não encontrei automaticamente um botão/link de download do PDF. "
              "Pode ser necessário desativar bloqueador de pop-up ou ajustar o seletor.")
        dump_debug(driver, "pdf_nao_encontrado")

    arquivos_pdf = [os.path.join(diretorio_download, f) for f in os.listdir(diretorio_download) if f.endswith('.pdf')]
    if arquivos_pdf:
        pdf_recente = max(arquivos_pdf, key=os.path.getctime)
        num_darj_limpo = re.sub(r'[^0-9A-Za-z]', '', dados_darj['numDarj']) or 'SEMNUMERO'
        nome_personalizado = f"DARJ_NF_{nota_fiscal}_{num_darj_limpo}.pdf"
        caminho_renomeado = os.path.join(diretorio_download, nome_personalizado)
        if os.path.exists(caminho_renomeado):
            os.remove(caminho_renomeado)
        os.rename(pdf_recente, caminho_renomeado)
        print(f"PDF local salvo e renomeado para: {nome_personalizado}")

        print("14.1. Enviando PDF para a pasta do Google Drive...")
        enviar_pdf_para_drive(caminho_renomeado, ID_PASTA_DRIVE, creds)
    else:
        print("Aviso: Nenhum PDF foi localizado na pasta de downloads.")

    # ==========================================================================
    # FASE 6: GRAVAÇÃO DOS RESULTADOS NA PLANILHA
    # ==========================================================================
    print("15. Gravando informações na planilha Google...")

    col_num_darj = encontrar_coluna(['Nº DARJ'], 'Nº DARJ')
    col_vcto_darj = encontrar_coluna(['Vcto DARJ'], 'Vcto DARJ')
    col_valor_darj = encontrar_coluna(['Valor DARJ'], 'Valor DARJ')
    col_link_darj = encontrar_coluna(['Link DARJ'], 'Link DARJ')

    planilha.update_cell(linha_alvo_index, col_num_darj, dados_darj['numDarj'])
    planilha.update_cell(linha_alvo_index, col_vcto_darj, dados_darj['vencimento'] or dt_vencimento_str)
    planilha.update_cell(linha_alvo_index, col_valor_darj, dados_darj['valor'] or f"{darj_normal_float + fecp_float:.2f}".replace('.', ','))
    planilha.update_cell(linha_alvo_index, col_link_darj, link_darj_atual)

    print("Planilha atualizada com sucesso!")
    print("Processo concluído!")

except Exception as erro:
    print(f"Ocorreu um erro na automação: {type(erro).__name__}: {erro}")
    dump_debug(driver, "erro_execucao")

finally:
    driver.quit()
