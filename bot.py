"""DARJ RJ em lote. Veja README.md antes de colocar a revisão em produção."""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
import uuid
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.common.exceptions import NoAlertPresentException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException

from controle_darj import brl, dinheiro, executar_lote, extrair_dados_pdf, resolver_colunas

ID_PLANILHA = os.getenv('ID_PLANILHA', '1U0HgRTfVIoGo3Jrr9-62ItBZumgJP77QH4SGa_lZ9jI')
ID_PASTA_DRIVE = os.getenv('ID_PASTA_DRIVE', '1UApSGUMncRgU15q7UH1MGT6EKrEskYim')
ABA_CONTROLE = os.getenv('ABA_CONTROLE', 'Página1')
LINHA_CABECALHO = 2
CNPJ_RESPONSAVEL = '58248352001201'
URL_PORTAL = 'https://www1.fazenda.rj.gov.br/portaldepagamentos/'
BASE = Path(__file__).resolve().parent


def verificar_mensagens(driver):
    try:
        texto = driver.switch_to.alert.text
    except NoAlertPresentException:
        pass
    else:
        raise RuntimeError(f'Alerta do portal, sem aceitar automaticamente: {texto}')
    for elemento in driver.find_elements(By.CSS_SELECTOR, '#dialog-message, .ui-dialog-content'):
        if elemento.is_displayed() and elemento.text.strip():
            raise RuntimeError(f'Mensagem do portal: {elemento.text.strip()}')


def esperar(driver, wait, condicao):
    def consultar(d):
        try:
            try:
                verificar_mensagens(d)
            except WebDriverException as exc:
                if (
                    "Node with given id does not belong to the document"
                    in str(exc)
                ):
                    # A tela mudou durante a leitura.
                    # Reconsulta sem repetir cliques.
                    return False
                raise

            return condicao(d)

        except (
            NoSuchElementException,
            StaleElementReferenceException,
        ):
            return False

    return wait.until(consultar)


def esperar_elemento(driver, wait, campo_id):
    return esperar(driver, wait, EC.element_to_be_clickable((By.ID, campo_id)))


def preencher(driver, wait, campo_id, texto):
    campo = esperar_elemento(driver, wait, campo_id)
    if campo.get_property('readOnly'):
        raise RuntimeError(f'Campo {campo_id} permanece somente leitura')
    campo.clear()
    campo.send_keys(texto)
    # Dispara change/blur sem focar o vencimento readonly: TAB nesse campo
    # provoca outro onblur que pode calcular valores enquanto a data é limpa.
    driver.execute_script('arguments[0].blur();', campo)
    aguardar_ajax(driver, wait)


def aguardar_ajax(driver, wait):
    return esperar(driver, wait, lambda d: d.execute_script("""
        const engine = window.dwr && dwr.engine ? dwr.engine : window.DWREngine;
        const pendentes = engine && engine._batches
          ? Object.values(engine._batches).filter(Boolean).length : 0;
        return document.readyState === 'complete'
          && (!window.jQuery || jQuery.active === 0)
          && pendentes === 0;
    """))


def confirmar_data_pagamento(driver, wait, data):
    botao = driver.find_element(By.ID, 'btnAlterarDataPagamento')
    if botao.get_attribute('value').strip() == 'Alterar':
        botao.click()
    esperar(driver, wait, lambda d: not d.find_element(By.ID, 'txtDataPagamento').get_property('readOnly'))
    preencher(driver, wait, 'txtDataPagamento', data)
    botao = driver.find_element(By.ID, 'btnAlterarDataPagamento')
    if botao.get_attribute('value').strip() != 'Confirmar!':
        raise RuntimeError('Portal nao ofereceu a confirmacao da Data de Pagamento')
    botao.click()
    esperar(driver, wait, lambda d: (
        d.find_element(By.ID, 'txtDataPagamento').get_property('readOnly')
        and d.find_element(By.ID, 'txtDataPagamento').get_attribute('value').strip() == data
        and d.find_element(By.ID, 'btnAlterarDataPagamento').get_attribute('value').strip() == 'Alterar'
    ))


def selecionar(driver, wait, campo_id, valor):
    def pronto(d):
        campo = d.find_element(By.ID, campo_id)
        return (campo.is_displayed() and campo.is_enabled()
                and any(o.get_attribute('value') == valor for o in Select(campo).options))
    esperar(driver, wait, pronto)
    Select(driver.find_element(By.ID, campo_id)).select_by_value(valor)
    aguardar_ajax(driver, wait)


def criar_driver(diretorio):
    opcoes = Options()
    if os.getenv('HEADLESS', '').lower() == 'true' or os.getenv('GITHUB_ACTIONS') == 'true':
        opcoes.add_argument('--headless=new')
        opcoes.add_argument('--no-sandbox')
        opcoes.add_argument('--disable-dev-shm-usage')
    opcoes.add_argument('--window-size=1920,1080')
    opcoes.set_capability('unhandledPromptBehavior', 'ignore')
    opcoes.add_experimental_option('prefs', {
        'download.default_directory': str(diretorio),
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'plugins.always_open_pdf_externally': True,
    })
    # Usa o Chrome instalado pelo workflow quando houver caminho explícito.
    if os.getenv('CHROME_BINARY'):
        opcoes.binary_location = os.environ['CHROME_BINARY']
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opcoes)
    driver.set_page_load_timeout(60)
    driver.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(diretorio)})
    return driver, WebDriverWait(driver, 45, poll_frequency=0.5)


def dump_debug(driver, linha, etapa):
    pasta = BASE / 'diagnosticos' / f'linha_{linha}_{etapa}_{uuid.uuid4().hex[:8]}'
    pasta.mkdir(parents=True, exist_ok=True)
    dados = {'linha': linha, 'etapa': etapa, 'hora': datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(), 'abas': [], 'falhas': []}
    if driver is None:
        dados['falhas'].append('Navegador nao inicializado')
    else:
        original = None
        try:
            dados['alerta'] = driver.switch_to.alert.text
        except Exception:
            pass
        try:
            original = driver.current_window_handle
            handles = list(driver.window_handles)
        except Exception as exc:
            dados['falhas'].append(str(exc))
            handles = []
        for i, handle in enumerate(handles):
            try:
                driver.switch_to.window(handle)
                driver.switch_to.default_content()
            except Exception as exc:
                dados['falhas'].append(f'aba {i}: {exc}')
                continue
            item = {'handle': handle}
            for campo in ('current_url', 'title'):
                try:
                    item[campo] = getattr(driver, campo)
                except Exception as exc:
                    item[campo] = str(exc)
            try:
                driver.save_screenshot(str(pasta / f'aba_{i}.png'))
            except Exception as exc:
                dados['falhas'].append(f'PNG aba {i}: {exc}')
            try:
                (pasta / f'aba_{i}.html').write_text(driver.page_source, encoding='utf-8')
            except Exception as exc:
                dados['falhas'].append(f'HTML aba {i}: {exc}')
            try:
                item['campos'] = driver.execute_script("""
                    return Array.from(document.querySelectorAll('input,select,textarea'))
                      .filter(e=>e.type!=='hidden' && (e.offsetWidth||e.offsetHeight))
                      .map(e=>({id:e.id,value:e.value,readOnly:e.readOnly,disabled:e.disabled}));
                """)
            except Exception as exc:
                dados['falhas'].append(f'campos aba {i}: {exc}')
            dados['abas'].append(item)
        if original:
            try:
                driver.switch_to.window(original)
            except Exception:
                pass
    (pasta / 'contexto.json').write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Diagnostico salvo: {pasta}')


def auditar_formulario(driver, wait, alvo):
    def confere(d):
        ids = ('txtIcmsInformado', 'txtFecpInformado', 'txtTotalIcms', 'txtTotalFecp')
        try:
            valores = [dinheiro(d.find_element(By.ID, campo).get_attribute('value')) for campo in ids]
        except ValueError:
            return False
        return (valores == [alvo.icms, alvo.fecp, alvo.icms, alvo.fecp]
                and valores[2] + valores[3] == alvo.total)
    aguardar_ajax(driver, wait)
    esperar(driver, wait, confere)
    if driver.find_element(By.ID, 'btnAlterarDataPagamento').get_attribute('value').strip() != 'Alterar':
        raise RuntimeError('Data de Pagamento ainda aguarda confirmacao')
    for campo, esperado in [('txtDataPagamento', alvo.pagamento.strftime('%d/%m/%Y')),
                            ('txtDataVencimento', alvo.vencimento.strftime('%d/%m/%Y')),
                            ('txtPeriodo', alvo.periodo)]:
        if driver.find_element(By.ID, campo).get_attribute('value').strip() != esperado:
            raise RuntimeError(f'Campo {campo} divergiu do previsto')
    if driver.find_element(By.ID, 'txtJustificativa').get_attribute('value').strip() != f'NF {alvo.nota_raw}':
        raise RuntimeError('Nota fiscal nas informacoes complementares divergiu')
    if (driver.find_element(By.ID, 'slcNaturezaLista').get_attribute('value') != '4'
            or driver.find_element(By.ID, 'slcListaProduto').get_attribute('value') != '442'):
        raise RuntimeError('Natureza ou produto mudou durante o preenchimento')
    print(f'Auditoria aprovada: ICMS {brl(alvo.icms)} + FECP {brl(alvo.fecp)} = {brl(alvo.total)}')


def preencher_formulario(driver, wait, alvo):
    driver.get(URL_PORTAL)
    selecionar(driver, wait, 'tipoPagamentoLista', '1')
    radio = esperar_elemento(driver, wait, 'rdgDarj')
    if not radio.is_selected():
        radio.click()
        aguardar_ajax(driver, wait)
    confirmar_data_pagamento(driver, wait, alvo.pagamento.strftime('%d/%m/%Y'))
    # Confirmar a data recarrega o formulário; natureza/produto vêm depois.
    aguardar_ajax(driver, wait)
    selecionar(driver, wait, 'slcNaturezaLista', '4')
    selecionar(driver, wait, 'slcListaProduto', '442')
    preencher(driver, wait, 'txtCnpjCpf', CNPJ_RESPONSAVEL)
    esperar_elemento(driver, wait, 'btnConfirmar').click()
    esperar(driver, wait, lambda d: (
        d.find_element(By.ID, 'txtInscEstadual').get_attribute('value').strip() not in ('', '0')
        and d.find_element(By.ID, 'txtNomeRazaoSocial').get_attribute('value').strip()
        and d.find_element(By.ID, 'btnConfirmar').get_attribute('value').strip() == 'Alterar'
    ))
    if re.sub(r'\D', '', driver.find_element(By.ID, 'txtCnpjCpf').get_attribute('value')) != CNPJ_RESPONSAVEL:
        raise RuntimeError('CNPJ do formulario divergiu do configurado')
    selecionar(driver, wait, 'slcTipoPeriodo', 'M')
    preencher(driver, wait, 'txtPeriodo', alvo.periodo)
    esperar_elemento(driver, wait, 'btnAlterarData').click()
    esperar(driver, wait, lambda d: not d.find_element(By.ID, 'txtDataVencimento').get_property('readOnly'))
    preencher(driver, wait, 'txtDataVencimento', alvo.vencimento.strftime('%d/%m/%Y'))
    preencher(driver, wait, 'txtJustificativa', f'NF {alvo.nota_raw}')
    preencher(driver, wait, 'txtIcmsInformado', brl(alvo.icms))
    preencher(driver, wait, 'txtFecpInformado', brl(alvo.fecp))
    esperar_elemento(driver, wait, 'okIcms').click()
    aguardar_ajax(driver, wait)
    esperar_elemento(driver, wait, 'okFecp').click()
    auditar_formulario(driver, wait, alvo)


XPATH_GERAR = "//input[@type='button' and contains(@value,'Gerar DARJ')] | //button[normalize-space(.)='Gerar DARJ'] | //a[normalize-space(.)='Gerar DARJ']"


def botao_gerar_unico(driver):
    candidatos = [e for e in driver.find_elements(By.XPATH, XPATH_GERAR) if e.is_displayed() and e.is_enabled()]
    if len(candidatos) > 1:
        raise RuntimeError('Mais de um botao Gerar DARJ; nenhuma emissao solicitada')
    return candidatos[0] if candidatos else False


def auditar_resumo(driver, wait, alvo):
    botao = esperar(driver, wait, botao_gerar_unico)
    quantidade = driver.find_element(By.ID, 'hdnQuantidadeDocs').get_attribute('value').strip()
    if quantidade != '1':
        raise RuntimeError(f'Resumo contem {quantidade!r} documentos; esperado somente um por linha')
    itens = [e for e in driver.find_elements(By.CSS_SELECTOR, 'input[type=checkbox][id^=chkItens]')
             if e.is_displayed() and e.is_enabled()]
    if len(itens) > 1:
        raise RuntimeError('Resumo contem varios itens selecionaveis')
    if itens and not itens[0].is_selected():
        itens[0].click()
    aguardar_ajax(driver, wait)
    if dinheiro(driver.find_element(By.ID, 'hdnValorTotal').get_attribute('value')) != alvo.total:
        raise RuntimeError('Valor total do resumo diverge da planilha')
    return botao


def aguardar_pdf(driver, diretorio, anteriores, alvo, timeout=90):
    limite = time.monotonic() + timeout
    anterior = None
    while time.monotonic() < limite:
        verificar_mensagens(driver)
        arquivos = [p for p in diretorio.glob('*.pdf') if p.name not in anteriores]
        if len(arquivos) > 1:
            raise RuntimeError('Mais de um PDF novo; conferir sem escolher o mais recente')
        if arquivos and not list(diretorio.glob('*.crdownload')) and not list(diretorio.glob('*.part')):
            arquivo = arquivos[0]
            tamanho = arquivo.stat().st_size
            if tamanho > 0 and anterior == (arquivo.name, tamanho):
                return arquivo
            anterior = (arquivo.name, tamanho)
        # Algumas respostas são HTML imprimível numa aba nova. Imprimir localmente
        # não solicita outro DARJ. Exigimos identidade/valor e código de barras.
        original = driver.current_window_handle
        for handle in list(driver.window_handles):
            driver.switch_to.window(handle)
            try:
                conteudo = driver.execute_script("""
                    return {texto:document.body ? document.body.innerText : '',
                      pronto:document.readyState==='complete' && Array.from(document.images).every(i=>i.complete),
                      barras:!!document.querySelector('img[src*=barcode i],img[src*=barras i],img[alt*=barras i]')};
                """)
                if not conteudo or not conteudo['pronto']:
                    continue
                try:
                    extrair_dados_pdf(conteudo['texto'], alvo, CNPJ_RESPONSAVEL)
                except ValueError:
                    continue
                linha_digitavel = any(44 <= len(re.sub(r'\D', '', linha)) <= 48
                                      for linha in conteudo['texto'].splitlines()
                                      if re.fullmatch(r'[\d .-]+', linha.strip()))
                if not (conteudo['barras'] or linha_digitavel):
                    continue
                pdf = driver.execute_cdp_cmd('Page.printToPDF', {'printBackground': True, 'preferCSSPageSize': True})
                caminho = diretorio / 'darj_renderizado.pdf'
                caminho.write_bytes(base64.b64decode(pdf['data']))
                return caminho
            finally:
                driver.switch_to.window(original)
        time.sleep(0.5)
    raise TimeoutError('PDF novo nao confirmado. Conferir diagnosticos; nao clicar em Gerar DARJ novamente')


def emitir_portal(alvo, antes_envio):
    diretorio = BASE / 'downloads_darj' / f'linha_{alvo.linha}_{uuid.uuid4().hex[:10]}'
    diretorio.mkdir(parents=True)
    driver = None
    try:
        driver, wait = criar_driver(diretorio)
        preencher_formulario(driver, wait, alvo)
        dump_debug(driver, alvo.linha, 'antes_confirmar_item')
        confirmar = esperar(driver, wait, EC.element_to_be_clickable((
            By.XPATH, "//input[@type='button' and contains(@value,'Confirmar item')]"
        )))
        antes_envio()
        confirmar.click()  # Tentativa única, inclusive nesta inclusão no resumo.
        botao = auditar_resumo(driver, wait, alvo)
        dump_debug(driver, alvo.linha, 'antes_gerar')
        anteriores = {p.name for p in diretorio.glob('*.pdf')}
        antes_envio()  # Nova conferência da planilha imediatamente antes de emitir.
        botao.click()  # Tentativa única de geração.
        caminho = aguardar_pdf(driver, diretorio, anteriores, alvo)
        dump_debug(driver, alvo.linha, 'retorno_geracao')
        return caminho
    except Exception:
        try:
            dump_debug(driver, alvo.linha, 'erro')
        except Exception as diagnostico:
            print(f'Falha adicional no diagnostico: {diagnostico}')
        raise
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def selecionar_aba(pasta):
    candidatas = []
    for aba in pasta.worksheets():
        try:
            resolver_colunas(aba.row_values(LINHA_CABECALHO))
        except ValueError:
            continue
        if aba.title == ABA_CONTROLE:
            return aba
        candidatas.append(aba)
    if len(candidatas) == 1:
        return candidatas[0]
    raise RuntimeError(f'Aba {ABA_CONTROLE!r} nao identificada de forma unica pelos cabecalhos')


@contextmanager
def exclusao_local():
    arquivo = (BASE / '.darj-rj.lock').open('a+b')
    try:
        arquivo.seek(0)
        if os.name == 'nt':
            import msvcrt
            if arquivo.read(1) == b'':
                arquivo.write(b'0'); arquivo.flush()
            arquivo.seek(0)
            msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        arquivo.close()
        raise RuntimeError('Outro processo DARJ-RJ ja esta executando nesta pasta') from exc
    try:
        yield
    finally:
        arquivo.close()  # O sistema operacional libera o bloqueio, inclusive em falhas.


def main():
    import holidays
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    parser = argparse.ArgumentParser()
    parser.add_argument('--validar', action='store_true', help='Somente validar a planilha, sem emitir ou mudar status')
    args = parser.parse_args()
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    with exclusao_local():
        credenciais = ServiceAccountCredentials.from_json_keyfile_name(str(BASE / 'credenciais.json'), scope)
        planilha = selecionar_aba(gspread.authorize(credenciais).open_by_key(ID_PLANILHA))
        valores = planilha.get_all_values(value_render_option='FORMATTED_VALUE')
        hoje = datetime.now(ZoneInfo('America/Sao_Paulo')).date()
        anos = {hoje.year - 1, hoje.year, hoje.year + 1}
        feriados = holidays.Brazil(subdiv='RJ', years=sorted(anos))
        drive = build('drive', 'v3', credentials=credenciais)

        def subir_pdf(caminho):
            arquivo = drive.files().create(
                body={'name': caminho.name, 'parents': [ID_PASTA_DRIVE]},
                media_body=MediaFileUpload(str(caminho), mimetype='application/pdf'),
                fields='id', supportsAllDrives=True,
            ).execute()
            file_id = arquivo.get('id')
            if not file_id:
                raise RuntimeError('Upload sem identificador de arquivo no Drive')
            return file_id

        resultado = executar_lote(valores, planilha, emitir_portal, subir_pdf, hoje, feriados,
                                   CNPJ_RESPONSAVEL, apenas_validar=args.validar,
                                   linha_cabecalho=LINHA_CABECALHO)
        print(f'Lote finalizado: {resultado}')


if __name__ == '__main__':
    try:
        main()
    except Exception as erro:
        print(f'EXECUCAO INTERROMPIDA: {type(erro).__name__}: {erro}', file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
