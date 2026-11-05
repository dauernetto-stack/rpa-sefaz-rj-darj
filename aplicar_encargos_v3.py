"""Versao 3: preserva o nome CE12_DARJ_NF personalizado e compara no Python local.
Aplica somente suporte auditado a encargos. Nao acessa rede nem emite guias.
Uso, na raiz do projeto: python aplicar_encargos_v3.py --verificar
Depois: python aplicar_encargos_v3.py --aplicar
"""
import argparse
import ast
from datetime import datetime
import hashlib
from pathlib import Path
import uuid

FUNCOES = {
    'bot.py': {
        'functions': {
            'auditar_formulario': {
                'source': r'''def auditar_formulario(driver, wait, alvo):
    from controle_darj import conferir_calculo_portal
    from selenium.common.exceptions import TimeoutException
    ids = (
        'txtIcmsInformado', 'txtFecpInformado',
        'txtIcmsAtualizado', 'txtFecpAtualizado',
        'txtMoraIcms', 'txtMultaMoraIcms', 'txtTotalIcms',
        'txtMoraFecp', 'txtMultaMoraFecp', 'txtTotalFecp',
    )
    ultimo = {'campos': {}, 'motivo': 'Calculo ainda nao carregado'}

    def confere(d):
        campos = {campo: d.find_element(By.ID, campo).get_attribute('value') for campo in ids}
        ultimo['campos'] = campos
        try:
            return conferir_calculo_portal(alvo, campos)
        except ValueError as exc:
            ultimo['motivo'] = str(exc)
            return False

    aguardar_ajax(driver, wait)
    try:
        calculo = esperar(driver, wait, confere)
    except TimeoutException as exc:
        detalhes = dict(ultimo['campos'])
        for campo in ('txtDataPagamento', 'txtDataVencimento', 'txtPeriodo'):
            try:
                detalhes[campo] = driver.find_element(By.ID, campo).get_attribute('value')
            except Exception:
                detalhes[campo] = 'indisponivel'
        raise RuntimeError(
            f'Auditoria bloqueada: {ultimo["motivo"]}. '
            f'Principal esperado: ICMS {brl(alvo.icms)} + FECP {brl(alvo.fecp)} '
            f'= {brl(alvo.total)}. Campos: {detalhes}. Nenhum item confirmado nesta tentativa.'
        ) from exc
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
    print(f'Auditoria aprovada: principal {brl(alvo.total)} + encargos '
          f'{brl(calculo.encargos)} = total final {brl(calculo.total)}')
    print(f'Encargos do portal: ICMS mora {brl(calculo.mora_icms)}, multa {brl(calculo.multa_icms)}; '
          f'FECP mora {brl(calculo.mora_fecp)}, multa {brl(calculo.multa_fecp)}')
    return calculo
''',
                'references': [r'''def auditar_formulario(driver, wait, alvo):
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
''', r'''def auditar_formulario(driver, wait, alvo):
    def confere(d):
        ids = ('txtIcmsInformado', 'txtFecpInformado', 'txtTotalIcms', 'txtTotalFecp')
        try:
            valores = [dinheiro(d.find_element(By.ID, campo).get_attribute('value')) for campo in ids]
        except ValueError:
            return False
        return (valores == [alvo.icms, alvo.fecp, alvo.icms, alvo.fecp]
                and valores[2] + valores[3] == alvo.total)
    aguardar_ajax(driver, wait)
    from selenium.common.exceptions import TimeoutException
    try:
        esperar(driver, wait, confere)
    except TimeoutException as exc:
        campos = (
            'txtIcmsInformado', 'txtFecpInformado',
            'txtTotalIcms', 'txtTotalFecp',
            'txtMoraIcms', 'txtMultaMoraIcms',
            'txtMoraFecp', 'txtMultaMoraFecp',
            'txtDataPagamento', 'txtDataVencimento', 'txtPeriodo',
        )
        detalhes = []
        for campo in campos:
            try:
                valor = driver.find_element(By.ID, campo).get_attribute('value')
            except Exception:
                valor = 'indisponivel'
            detalhes.append(f'{campo}={valor!r}')
        raise RuntimeError(
            f'Auditoria bloqueada: esperado ICMS {brl(alvo.icms)} + '
            f'FECP {brl(alvo.fecp)} = {brl(alvo.total)}. '
            'Valores/datas observados no portal: ' + '; '.join(detalhes)
            + '. Nenhum item confirmado nesta tentativa; conferir divergencias.'
        ) from exc
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
'''],
            },
            'preencher_formulario': {
                'source': r'''def preencher_formulario(driver, wait, alvo):
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
    preencher_periodo(driver, wait, alvo.periodo)
    esperar_elemento(driver, wait, 'btnAlterarData').click()
    esperar(driver, wait, lambda d: not d.find_element(By.ID, 'txtDataVencimento').get_property('readOnly'))
    preencher(driver, wait, 'txtDataVencimento', alvo.vencimento.strftime('%d/%m/%Y'))
    preencher(driver, wait, 'txtJustificativa', f'NF {alvo.nota_raw}')
    preencher(driver, wait, 'txtIcmsInformado', brl(alvo.icms))
    preencher(driver, wait, 'txtFecpInformado', brl(alvo.fecp))
    esperar_elemento(driver, wait, 'okIcms').click()
    aguardar_ajax(driver, wait)
    esperar_elemento(driver, wait, 'okFecp').click()
    return auditar_formulario(driver, wait, alvo)
''',
                'references': [r'''def preencher_formulario(driver, wait, alvo):
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
    preencher_periodo(driver, wait, alvo.periodo)
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
'''],
            },
            'auditar_resumo': {
                'source': r'''def auditar_resumo(driver, wait, alvo, calculo=None):
    from controle_darj import total_esperado
    esperado = total_esperado(alvo, calculo)
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
    if dinheiro(driver.find_element(By.ID, 'hdnValorTotal').get_attribute('value')) != esperado:
        raise RuntimeError('Valor total do resumo diverge do calculo auditado')
    return botao
''',
                'references': [r'''def auditar_resumo(driver, wait, alvo):
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
'''],
            },
            'abrir_darj_emitido': {
                'source': r'''def abrir_darj_emitido(driver, wait, alvo, calculo=None):
    from controle_darj import total_esperado
    esperado = total_esperado(alvo, calculo)
    # Confirma a tela de emissão antes de abrir o boleto existente.
    esperar(
        driver,
        wait,
        lambda d: d.find_element(
            By.CSS_SELECTOR, 'h1.titulopagina'
        ).text.strip() == 'DARJ emitido'
    )

    impressora = esperar_elemento(driver, wait, 'btnGerarDocs')
    aguardar_ajax(driver, wait)

    quantidade = driver.find_element(
        By.ID, 'hdnQuantidadeDocs'
    ).get_attribute('value').strip()

    cnpj = driver.find_element(
        By.CSS_SELECTOR,
        "input[name='{pageFlow.documentoForm.cnpjCpf}']"
    ).get_attribute('value')

    total = driver.find_element(
        By.ID, 'hdnValorTotal'
    ).get_attribute('value')

    if quantidade != '1' or re.sub(r'\D', '', cnpj or '') != CNPJ_RESPONSAVEL:
        raise RuntimeError(
            'DARJ emitido: quantidade ou CNPJ divergente; '
            'conferir sem reemitir'
        )

    if dinheiro(total) != esperado:
        raise RuntimeError(
            'DARJ emitido: valor divergente; conferir sem reemitir'
        )

    print('Portal confirmou DARJ emitido. Abrindo o boleto existente...')
    impressora.click()  # Uma tentativa; sem repetir o clique.
''',
                'references': [r'''def abrir_darj_emitido(driver, wait, alvo):
    # Confirma a tela de emissão antes de abrir o boleto existente.
    esperar(
        driver,
        wait,
        lambda d: d.find_element(
            By.CSS_SELECTOR, 'h1.titulopagina'
        ).text.strip() == 'DARJ emitido'
    )

    impressora = esperar_elemento(driver, wait, 'btnGerarDocs')
    aguardar_ajax(driver, wait)

    quantidade = driver.find_element(
        By.ID, 'hdnQuantidadeDocs'
    ).get_attribute('value').strip()

    cnpj = driver.find_element(
        By.CSS_SELECTOR,
        "input[name='{pageFlow.documentoForm.cnpjCpf}']"
    ).get_attribute('value')

    total = driver.find_element(
        By.ID, 'hdnValorTotal'
    ).get_attribute('value')

    if quantidade != '1' or re.sub(r'\D', '', cnpj or '') != CNPJ_RESPONSAVEL:
        raise RuntimeError(
            'DARJ emitido: quantidade ou CNPJ divergente; '
            'conferir sem reemitir'
        )

    if dinheiro(total) != alvo.total:
        raise RuntimeError(
            'DARJ emitido: valor divergente; conferir sem reemitir'
        )

    print('Portal confirmou DARJ emitido. Abrindo o boleto existente...')
    impressora.click()  # Uma tentativa; sem repetir o clique.
'''],
            },
            'aguardar_pdf': {
                'source': r'''def aguardar_pdf(driver, diretorio, anteriores, alvo, timeout=90, calculo=None):
    limite = time.monotonic() + timeout
    anterior = None
    while time.monotonic() < limite:
        verificar_mensagens(driver)
        arquivos = [p for p in diretorio.glob('*.pdf') if p.name not in anteriores]
        if len(arquivos) > 1:
            raise RuntimeError('Mais de um PDF novo; conferir sem escolher o mais recente')
        if arquivos and not any(
            arquivos[0].with_name(arquivos[0].name + sufixo).exists()
            for sufixo in ('.crdownload', '.part')
        ):
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
                    extrair_dados_pdf(conteudo['texto'], alvo, CNPJ_RESPONSAVEL, calculo)
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
''',
                'references': [r'''def aguardar_pdf(driver, diretorio, anteriores, alvo, timeout=90):
    limite = time.monotonic() + timeout
    anterior = None
    while time.monotonic() < limite:
        verificar_mensagens(driver)
        arquivos = [p for p in diretorio.glob('*.pdf') if p.name not in anteriores]
        if len(arquivos) > 1:
            raise RuntimeError('Mais de um PDF novo; conferir sem escolher o mais recente')
        if arquivos and not any(
            arquivos[0].with_name(arquivos[0].name + sufixo).exists()
            for sufixo in ('.crdownload', '.part')
        ):
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
'''],
            },
            'emitir_portal': {
                'source': r'''def emitir_portal(alvo, antes_envio):
    from controle_darj import EmissaoPortal, CalculoPortal
    diretorio = BASE / 'downloads_darj' / f'linha_{alvo.linha}_{uuid.uuid4().hex[:10]}'
    diretorio.mkdir(parents=True)
    driver = None
    try:
        driver, wait = criar_driver(diretorio)
        calculo = preencher_formulario(driver, wait, alvo)
        if not isinstance(calculo, CalculoPortal):
            raise RuntimeError('Formulario nao retornou calculo auditado; nenhum item confirmado')
        calculo.validar(alvo)
        dump_debug(driver, alvo.linha, 'antes_confirmar_item')
        confirmar = esperar(driver, wait, EC.element_to_be_clickable((
            By.XPATH, "//input[@type='button' and contains(@value,'Confirmar item')]"
        )))
        antes_envio()
        confirmar.click()  # Tentativa única, inclusive nesta inclusão no resumo.
        botao = auditar_resumo(driver, wait, alvo, calculo)
        dump_debug(driver, alvo.linha, 'antes_gerar')
        anteriores = {p.name for p in diretorio.glob('*.pdf')}
        antes_envio()  # Nova conferência da planilha imediatamente antes de emitir.
        botao.click()  # Tentativa única de geração.

        abrir_darj_emitido(driver, wait, alvo, calculo)
        dump_debug(driver, alvo.linha, 'apos_abrir_boleto')

        caminho = aguardar_pdf(driver, diretorio, anteriores, alvo, calculo=calculo)
        dump_debug(driver, alvo.linha, 'retorno_geracao')
        return EmissaoPortal(caminho, calculo)
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
''',
                'references': [r'''def emitir_portal(alvo, antes_envio):
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

        abrir_darj_emitido(driver, wait, alvo)
        dump_debug(driver, alvo.linha, 'apos_abrir_boleto')

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
'''],
            },
        },
    },
    'controle_darj.py': {
        'functions': {
            'extrair_dados_pdf': {
                'source': r'''def extrair_dados_pdf(texto, alvo, cnpj, calculo=None):
    esperado = total_esperado(alvo, calculo)
    texto = normalizar(texto)
    if 'darj' not in texto:
        raise ValueError('O PDF nao foi identificado como DARJ')
    cnpjs = {re.sub(r'\D', '', n) for n in re.findall(
        r'\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b', texto)}
    if cnpj not in cnpjs:
        raise ValueError('CNPJ esperado nao encontrado no PDF')
    if not re.search(r'\bnf\s*[:#]?\s*' + re.escape(alvo.nota_raw) + r'(?![\d-])', texto):
        raise ValueError('Nota fiscal esperada nao encontrada nas informacoes do PDF')

    linhas = [linha for linha in texto.splitlines() if linha.strip()]

    def ler_campo(rotulo, padrao):
        valores = []
        for indice, linha in enumerate(linhas):
            for campo in re.finditer(rotulo, linha):
                trecho = linha[campo.end():].strip(' \t:')
                if not trecho and indice + 1 < len(linhas):
                    trecho = linhas[indice + 1]
                encontrados = re.findall(padrao, trecho)
                if len(encontrados) != 1:
                    raise ValueError(f'Campo {campo.group()!r} ausente ou ambiguo no PDF; manter REVISAR')
                valores.append(encontrados[0])
        return valores

    # Nosso Numero identifica o DARJ. O campo No Documento tem outro significado.
    if re.search(r'nosso\s+numero', texto):
        numeros = set(ler_campo(r'nosso\s+numero', r'(?<!\d)\d{25}(?!\d)'))
    else:
        numeros = set(ler_campo(
            r'(?:numero\s+(?:do\s+)?(?:documento|darj)|n[º°o]\s*(?:do\s+)?(?:documento|darj))',
            r'(?<![\d.,/])\d{6,25}(?![\d.,/])'))
    if len(numeros) != 1:
        raise ValueError('Numero do DARJ ausente ou diferente entre as vias/DIP; manter REVISAR')

    padrao_data = r'(?<!\d)\d{2}/\d{2}/\d{4}(?!\d)'
    datas = {parse_data(v) for v in ler_campo(
        r'(?:data\s+(?:de\s+)?)?vencimento', padrao_data)}
    if datas != {alvo.vencimento}:
        raise ValueError('Vencimento do PDF ausente, ambiguo ou diferente do previsto')

    # A validade do DARJ e a data de pagamento podem diferir do vencimento do DIP.
    pagamentos = {parse_data(v) for v in ler_campo(
        r'data\s+(?:validade|(?:de\s+)?pagamento)', padrao_data)}
    if pagamentos and pagamentos != {alvo.pagamento}:
        raise ValueError('Pagamento/validade do PDF diferente do previsto')

    padrao_valor = r'(?<![\d.,/])(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?![\d.,/])'
    valores = {dinheiro(v) for v in ler_campo(
        r'(?:valor\s+total|total\s+a\s+pagar)', padrao_valor)}
    if valores != {esperado}:
        raise ValueError('Valor total do PDF ausente, ambiguo ou divergente')
    return {'numero': numeros.pop(), 'vencimento': alvo.vencimento.strftime('%d/%m/%Y'),
            'valor': brl(esperado)}
''',
                'references': [r'''def extrair_dados_pdf(texto, alvo, cnpj):
    texto = normalizar(texto)
    if 'darj' not in texto:
        raise ValueError('O PDF nao foi identificado como DARJ')
    cnpjs = {re.sub(r'\D', '', n) for n in re.findall(
        r'\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b', texto)}
    if cnpj not in cnpjs:
        raise ValueError('CNPJ esperado nao encontrado no PDF')
    if not re.search(r'\bnf\s*[:#]?\s*' + re.escape(alvo.nota_raw) + r'(?![\d-])', texto):
        raise ValueError('Nota fiscal esperada nao encontrada nas informacoes do PDF')

    linhas = [linha for linha in texto.splitlines() if linha.strip()]

    def ler_campo(rotulo, padrao):
        valores = []
        for indice, linha in enumerate(linhas):
            for campo in re.finditer(rotulo, linha):
                trecho = linha[campo.end():].strip(' \t:')
                if not trecho and indice + 1 < len(linhas):
                    trecho = linhas[indice + 1]
                encontrados = re.findall(padrao, trecho)
                if len(encontrados) != 1:
                    raise ValueError(f'Campo {campo.group()!r} ausente ou ambiguo no PDF; manter REVISAR')
                valores.append(encontrados[0])
        return valores

    # Nosso Numero identifica o DARJ. O campo No Documento tem outro significado.
    if re.search(r'nosso\s+numero', texto):
        numeros = set(ler_campo(r'nosso\s+numero', r'(?<!\d)\d{25}(?!\d)'))
    else:
        numeros = set(ler_campo(
            r'(?:numero\s+(?:do\s+)?(?:documento|darj)|n[º°o]\s*(?:do\s+)?(?:documento|darj))',
            r'(?<![\d.,/])\d{6,25}(?![\d.,/])'))
    if len(numeros) != 1:
        raise ValueError('Numero do DARJ ausente ou diferente entre as vias/DIP; manter REVISAR')

    padrao_data = r'(?<!\d)\d{2}/\d{2}/\d{4}(?!\d)'
    datas = {parse_data(v) for v in ler_campo(
        r'(?:data\s+(?:de\s+)?)?vencimento', padrao_data)}
    if datas != {alvo.vencimento}:
        raise ValueError('Vencimento do PDF ausente, ambiguo ou diferente do previsto')

    # A validade do DARJ e a data de pagamento podem diferir do vencimento do DIP.
    pagamentos = {parse_data(v) for v in ler_campo(
        r'data\s+(?:validade|(?:de\s+)?pagamento)', padrao_data)}
    if pagamentos and pagamentos != {alvo.pagamento}:
        raise ValueError('Pagamento/validade do PDF diferente do previsto')

    padrao_valor = r'(?<![\d.,/])(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?![\d.,/])'
    valores = {dinheiro(v) for v in ler_campo(
        r'(?:valor\s+total|total\s+a\s+pagar)', padrao_valor)}
    if valores != {alvo.total}:
        raise ValueError('Valor total do PDF ausente, ambiguo ou divergente')
    return {'numero': numeros.pop(), 'vencimento': alvo.vencimento.strftime('%d/%m/%Y'),
            'valor': brl(alvo.total)}
'''],
            },
            'validar_pdf': {
                'source': r'''def validar_pdf(caminho, alvo, cnpj, calculo=None):
    from pypdf import PdfReader
    caminho = Path(caminho)
    with caminho.open('rb') as arquivo:
        if arquivo.read(5) != b'%PDF-':
            raise ValueError('Download nao e um arquivo PDF')
    leitor = PdfReader(caminho, strict=True)
    if leitor.is_encrypted:
        raise ValueError('PDF protegido; conferir manualmente')
    texto = '\n'.join(p.extract_text(extraction_mode='layout') or '' for p in leitor.pages)
    dados = extrair_dados_pdf(texto, alvo, cnpj, calculo)
    prefixo = re.sub(r'[^\w-]', '_', alvo.centro) + '_' if alvo.centro else ''
    nome = f"{prefixo}DARJ_NF_{alvo.nota}_{dados['numero']}.pdf"
    destino = caminho.with_name(nome)
    if destino != caminho:
        if destino.exists():
            raise FileExistsError(f'Ja existe um PDF com o nome final: {destino}')
        caminho.rename(destino)
    return destino, dados
''',
                'references': [r'''def validar_pdf(caminho, alvo, cnpj):
    from pypdf import PdfReader
    caminho = Path(caminho)
    with caminho.open('rb') as arquivo:
        if arquivo.read(5) != b'%PDF-':
            raise ValueError('Download nao e um arquivo PDF')
    leitor = PdfReader(caminho, strict=True)
    if leitor.is_encrypted:
        raise ValueError('PDF protegido; conferir manualmente')
    texto = '\n'.join(p.extract_text(extraction_mode='layout') or '' for p in leitor.pages)
    dados = extrair_dados_pdf(texto, alvo, cnpj)
    prefixo = re.sub(r'[^\w-]', '_', alvo.centro) + '_' if alvo.centro else ''
    nome = f"{prefixo}DARJ_NF_{alvo.nota}_{dados['numero']}.pdf"
    destino = caminho.with_name(nome)
    if destino != caminho:
        if destino.exists():
            raise FileExistsError(f'Ja existe um PDF com o nome final: {destino}')
        caminho.rename(destino)
    return destino, dados
''', r'''def validar_pdf(caminho, alvo, cnpj):
    from pypdf import PdfReader
    caminho = Path(caminho)
    with caminho.open('rb') as arquivo:
        if arquivo.read(5) != b'%PDF-':
            raise ValueError('Download nao e um arquivo PDF')
    leitor = PdfReader(caminho, strict=True)
    if leitor.is_encrypted:
        raise ValueError('PDF protegido; conferir manualmente')
    texto = '\n'.join(p.extract_text(extraction_mode='layout') or '' for p in leitor.pages)
    dados = extrair_dados_pdf(texto, alvo, cnpj)
    prefixo = re.sub(r'[^\w-]', '_', alvo.centro) + '_' if alvo.centro else ''
    nome = f"{prefixo}CE12_DARJ_NF_{alvo.nota_raw}.pdf"
    destino = caminho.with_name(nome)
    if destino != caminho:
        if destino.exists():
            raise FileExistsError(f'Ja existe um PDF com o nome final: {destino}')
        caminho.rename(destino)
    return destino, dados
''', r'''def validar_pdf(caminho, alvo, cnpj, calculo=None):
    from pypdf import PdfReader
    caminho = Path(caminho)
    with caminho.open('rb') as arquivo:
        if arquivo.read(5) != b'%PDF-':
            raise ValueError('Download nao e um arquivo PDF')
    leitor = PdfReader(caminho, strict=True)
    if leitor.is_encrypted:
        raise ValueError('PDF protegido; conferir manualmente')
    texto = '\n'.join(p.extract_text(extraction_mode='layout') or '' for p in leitor.pages)
    dados = extrair_dados_pdf(texto, alvo, cnpj, calculo)
    prefixo = re.sub(r'[^\w-]', '_', alvo.centro) + '_' if alvo.centro else ''
    nome = f"{prefixo}CE12_DARJ_NF_{alvo.nota_raw}.pdf"
    destino = caminho.with_name(nome)
    if destino != caminho:
        if destino.exists():
            raise FileExistsError(f'Ja existe um PDF com o nome final: {destino}')
        caminho.rename(destino)
    return destino, dados
'''],
                'variants': [{
                    'source': r'''def validar_pdf(caminho, alvo, cnpj, calculo=None):
    from pypdf import PdfReader
    caminho = Path(caminho)
    with caminho.open('rb') as arquivo:
        if arquivo.read(5) != b'%PDF-':
            raise ValueError('Download nao e um arquivo PDF')
    leitor = PdfReader(caminho, strict=True)
    if leitor.is_encrypted:
        raise ValueError('PDF protegido; conferir manualmente')
    texto = '\n'.join(p.extract_text(extraction_mode='layout') or '' for p in leitor.pages)
    dados = extrair_dados_pdf(texto, alvo, cnpj, calculo)
    prefixo = re.sub(r'[^\w-]', '_', alvo.centro) + '_' if alvo.centro else ''
    nome = f"{prefixo}CE12_DARJ_NF_{alvo.nota_raw}.pdf"
    destino = caminho.with_name(nome)
    if destino != caminho:
        if destino.exists():
            raise FileExistsError(f'Ja existe um PDF com o nome final: {destino}')
        caminho.rename(destino)
    return destino, dados
''',
                    'references': [r'''def validar_pdf(caminho, alvo, cnpj):
    from pypdf import PdfReader
    caminho = Path(caminho)
    with caminho.open('rb') as arquivo:
        if arquivo.read(5) != b'%PDF-':
            raise ValueError('Download nao e um arquivo PDF')
    leitor = PdfReader(caminho, strict=True)
    if leitor.is_encrypted:
        raise ValueError('PDF protegido; conferir manualmente')
    texto = '\n'.join(p.extract_text(extraction_mode='layout') or '' for p in leitor.pages)
    dados = extrair_dados_pdf(texto, alvo, cnpj)
    prefixo = re.sub(r'[^\w-]', '_', alvo.centro) + '_' if alvo.centro else ''
    nome = f"{prefixo}CE12_DARJ_NF_{alvo.nota_raw}.pdf"
    destino = caminho.with_name(nome)
    if destino != caminho:
        if destino.exists():
            raise FileExistsError(f'Ja existe um PDF com o nome final: {destino}')
        caminho.rename(destino)
    return destino, dados
'''],
                }],
            },
            'executar_lote': {
                'source': r'''def executar_lote(valores, planilha, emitir, subir_pdf, hoje, feriados, cnpj,
                  apenas_validar=False, intervalo=5, linha_cabecalho=2):
    colunas, pendentes, resultado = planejar_lote(valores, hoje, feriados, linha_cabecalho)
    print(f'Lote: {len(pendentes)} guias pendentes validadas, {resultado["linhas_validadas"]} linhas; '
          f'{resultado["ignoradas"]} linhas ignoradas, {resultado["subtotais_conferidos"]} subtotais conferidos.')
    for alvo in pendentes:
        print(f'NF {alvo.nota_raw} | linhas {", ".join(str(n) for n, _ in alvo.origens)} | '
              f'Entrada {alvo.entrada:%d/%m/%Y} | Periodo {alvo.periodo} | '
              f'ICMS {brl(alvo.icms)} + FECP {brl(alvo.fecp)} = {brl(alvo.total)}')
    if apenas_validar:
        return resultado

    def ler_atual(alvo, status, dados=None, formula=None):
        # Uma leitura integral identifica parcelas inseridas/removidas e novos blocos duplicados.
        atuais = planilha.get_all_values(value_render_option='FORMATTED_VALUE')
        atuais_colunas, registros = ler_registros(atuais, linha_cabecalho)
        if atuais_colunas != colunas:
            raise RuntimeError('Cabecalhos foram alterados durante o lote')
        blocos, _ = separar_blocos(registros)
        candidatos = [b for b in blocos if b.linhas[0][0] == alvo.linha]
        if len(candidatos) != 1:
            raise RuntimeError('Grupo da NF mudou de posicao durante o lote')
        bloco = candidatos[0]
        if tuple(n for n, _ in bloco.linhas) != tuple(n for n, _ in alvo.origens):
            raise RuntimeError('Parcelas da NF foram inseridas ou removidas durante o lote')
        if bloco.subtotal != alvo.subtotal:
            raise RuntimeError('Subtotal da NF foi alterado durante o lote')
        chave = (identidade_nota(alvo.nota_raw), alvo.centro, alvo.entrada.strftime('%Y-%m'))
        if sum(chave_bloco(b) == chave for b in blocos) != 1:
            raise RuntimeError('Outra ocorrencia da NF apareceu durante o lote')
        formulas = planilha.get_all_values(value_render_option='FORMULA') if dados else None
        for (linha, atual), (_, original) in zip(bloco.linhas, alvo.origens):
            if any(atual.get(c, '') != original.get(c, '') for c in CAMPOS_ENTRADA):
                raise RuntimeError(f'Linha {linha}: dados alterados durante o processamento')
            if atual['status'] != status:
                raise RuntimeError(f'Linha {linha}: status mudou durante o processamento')
            if dados is None:
                if any(atual[c] for c in CAMPOS_RESULTADO):
                    raise RuntimeError(f'Linha {linha}: dados de guia apareceram durante o processamento')
            else:
                if any(atual[c] != dados[c] for c in ('numero', 'vencimento', 'valor')):
                    raise RuntimeError(f'Linha {linha}: gravacao dos resultados nao confirmada')
                if atual['link'] not in ('Link PDF', formula):
                    raise RuntimeError(f'Linha {linha}: Link PDF nao confirmado')
                linha_formulas = formulas[linha - 1] if len(formulas) >= linha else []
                link = str(linha_formulas[colunas['link'] - 1]) if len(linha_formulas) >= colunas['link'] else ''
                # A leitura formatada so mostra o rotulo. Conferir tambem o destino da formula.
                padrao = r'=HYPERLINK\(\s*"' + re.escape(dados['link']) + r'"\s*[;,]\s*"Link PDF"\s*\)'
                if not re.fullmatch(padrao, link, re.IGNORECASE):
                    raise RuntimeError(f'Linha {linha}: destino do Link PDF nao confirmado')

    for indice, alvo in enumerate(pendentes):
        ler_atual(alvo, '')
        estado = {'envio': False}
        reservadas = []

        def antes_envio():
            ler_atual(alvo, 'PROCESSANDO')
            estado['envio'] = True

        try:
            reservadas = [linha for linha, _ in alvo.origens]
            planilha.batch_update([
                {'range': endereco_celula(linha, colunas['status']), 'values': [['PROCESSANDO']]}
                for linha in reservadas
            ], value_input_option='RAW')
            ler_atual(alvo, 'PROCESSANDO')
            retorno = emitir(alvo, antes_envio)
            if not estado['envio']:
                raise RuntimeError('Retorno sem registro do envio ao portal')
            if isinstance(retorno, EmissaoPortal):
                caminho, calculo = retorno.caminho, retorno.calculo
                if not isinstance(calculo, CalculoPortal):
                    raise ValueError('Retorno sem calculo auditado do portal')
                calculo.validar(alvo)
            else:
                # Compatibilidade com emissores antigos: continuam sem aceitar encargos.
                caminho, calculo = retorno, None
            caminho, dados = validar_pdf(caminho, alvo, cnpj, calculo)
            file_id = subir_pdf(caminho)
            if not isinstance(file_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', file_id):
                raise RuntimeError('Drive nao confirmou o ID do PDF')
            ler_atual(alvo, 'PROCESSANDO')
            dados['link'] = f'https://drive.google.com/file/d/{file_id}/view'
            formula = f'=HYPERLINK("{dados["link"]}";"Link PDF")'
            # RAW preserva os 25 digitos do DARJ. Escritas em lote reduzem chamadas ao Sheets.
            planilha.batch_update([
                {'range': endereco_celula(linha, colunas[campo]), 'values': [[dados[campo]]]}
                for linha in reservadas for campo in ('numero', 'vencimento', 'valor')
            ], value_input_option='RAW')
            planilha.batch_update([
                {'range': endereco_celula(linha, colunas['link']), 'values': [[formula]]}
                for linha in reservadas
            ], value_input_option='USER_ENTERED')
            ler_atual(alvo, 'PROCESSANDO', dados, formula)
            planilha.batch_update([
                {'range': endereco_celula(linha, colunas['status']), 'values': [['X']]}
                for linha in reservadas
            ], value_input_option='RAW')
            ler_atual(alvo, 'X', dados, formula)
            resultado['X'] += 1  # Conta guias, nao parcelas.
            resultado['linhas_concluidas'] += len(alvo.origens)
        except Exception as exc:
            status = 'REVISAR' if estado['envio'] else 'ERRO'
            falhas_status = []
            originais = dict(alvo.origens)
            for linha in reservadas:
                try:
                    # Se linhas/colunas mudaram, nao sobrescrever o status de outra NF.
                    cabecalho = planilha.row_values(linha_cabecalho)
                    if resolver_colunas(cabecalho) != colunas:
                        raise RuntimeError('cabecalhos alterados; status preservado')
                    atual = registro_da_linha(planilha.row_values(linha), colunas)
                    original = originais[linha]
                    if (identidade_nota(atual['nota']) != identidade_nota(original['nota'])
                            or atual.get('centro', '') != original.get('centro', '')):
                        raise RuntimeError('linha pertence a outra NF/centro; status preservado')
                    planilha.update_cell(linha, colunas['status'], status)
                except Exception as erro_status:
                    falhas_status.append(f'{linha}: {erro_status}')
            if falhas_status:
                raise RuntimeError(f'NF {alvo.nota_raw}: {exc}; status nao confirmado em {falhas_status}; conferir o grupo sem reemitir') from exc
            raise RuntimeError(f'NF {alvo.nota_raw}, linha {alvo.linha}: {status}; lote interrompido sem repetir a emissao: {exc}') from exc
        if intervalo and indice + 1 < len(pendentes):
            time.sleep(intervalo)
    return resultado
''',
                'references': [r'''def executar_lote(valores, planilha, emitir, subir_pdf, hoje, feriados, cnpj,
                  apenas_validar=False, intervalo=5, linha_cabecalho=2):
    colunas, pendentes, resultado = planejar_lote(valores, hoje, feriados, linha_cabecalho)
    print(f'Lote: {len(pendentes)} guias pendentes validadas, {resultado["linhas_validadas"]} linhas; '
          f'{resultado["ignoradas"]} linhas ignoradas, {resultado["subtotais_conferidos"]} subtotais conferidos.')
    for alvo in pendentes:
        print(f'NF {alvo.nota_raw} | linhas {", ".join(str(n) for n, _ in alvo.origens)} | '
              f'Entrada {alvo.entrada:%d/%m/%Y} | Periodo {alvo.periodo} | '
              f'ICMS {brl(alvo.icms)} + FECP {brl(alvo.fecp)} = {brl(alvo.total)}')
    if apenas_validar:
        return resultado

    def ler_atual(alvo, status, dados=None, formula=None):
        # Uma leitura integral identifica parcelas inseridas/removidas e novos blocos duplicados.
        atuais = planilha.get_all_values(value_render_option='FORMATTED_VALUE')
        atuais_colunas, registros = ler_registros(atuais, linha_cabecalho)
        if atuais_colunas != colunas:
            raise RuntimeError('Cabecalhos foram alterados durante o lote')
        blocos, _ = separar_blocos(registros)
        candidatos = [b for b in blocos if b.linhas[0][0] == alvo.linha]
        if len(candidatos) != 1:
            raise RuntimeError('Grupo da NF mudou de posicao durante o lote')
        bloco = candidatos[0]
        if tuple(n for n, _ in bloco.linhas) != tuple(n for n, _ in alvo.origens):
            raise RuntimeError('Parcelas da NF foram inseridas ou removidas durante o lote')
        if bloco.subtotal != alvo.subtotal:
            raise RuntimeError('Subtotal da NF foi alterado durante o lote')
        chave = (identidade_nota(alvo.nota_raw), alvo.centro, alvo.entrada.strftime('%Y-%m'))
        if sum(chave_bloco(b) == chave for b in blocos) != 1:
            raise RuntimeError('Outra ocorrencia da NF apareceu durante o lote')
        formulas = planilha.get_all_values(value_render_option='FORMULA') if dados else None
        for (linha, atual), (_, original) in zip(bloco.linhas, alvo.origens):
            if any(atual.get(c, '') != original.get(c, '') for c in CAMPOS_ENTRADA):
                raise RuntimeError(f'Linha {linha}: dados alterados durante o processamento')
            if atual['status'] != status:
                raise RuntimeError(f'Linha {linha}: status mudou durante o processamento')
            if dados is None:
                if any(atual[c] for c in CAMPOS_RESULTADO):
                    raise RuntimeError(f'Linha {linha}: dados de guia apareceram durante o processamento')
            else:
                if any(atual[c] != dados[c] for c in ('numero', 'vencimento', 'valor')):
                    raise RuntimeError(f'Linha {linha}: gravacao dos resultados nao confirmada')
                if atual['link'] not in ('Link PDF', formula):
                    raise RuntimeError(f'Linha {linha}: Link PDF nao confirmado')
                linha_formulas = formulas[linha - 1] if len(formulas) >= linha else []
                link = str(linha_formulas[colunas['link'] - 1]) if len(linha_formulas) >= colunas['link'] else ''
                # A leitura formatada so mostra o rotulo. Conferir tambem o destino da formula.
                padrao = r'=HYPERLINK\(\s*"' + re.escape(dados['link']) + r'"\s*[;,]\s*"Link PDF"\s*\)'
                if not re.fullmatch(padrao, link, re.IGNORECASE):
                    raise RuntimeError(f'Linha {linha}: destino do Link PDF nao confirmado')

    for indice, alvo in enumerate(pendentes):
        ler_atual(alvo, '')
        estado = {'envio': False}
        reservadas = []

        def antes_envio():
            ler_atual(alvo, 'PROCESSANDO')
            estado['envio'] = True

        try:
            reservadas = [linha for linha, _ in alvo.origens]
            planilha.batch_update([
                {'range': endereco_celula(linha, colunas['status']), 'values': [['PROCESSANDO']]}
                for linha in reservadas
            ], value_input_option='RAW')
            ler_atual(alvo, 'PROCESSANDO')
            caminho = emitir(alvo, antes_envio)
            if not estado['envio']:
                raise RuntimeError('Retorno sem registro do envio ao portal')
            caminho, dados = validar_pdf(caminho, alvo, cnpj)
            file_id = subir_pdf(caminho)
            if not isinstance(file_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', file_id):
                raise RuntimeError('Drive nao confirmou o ID do PDF')
            ler_atual(alvo, 'PROCESSANDO')
            dados['link'] = f'https://drive.google.com/file/d/{file_id}/view'
            formula = f'=HYPERLINK("{dados["link"]}";"Link PDF")'
            # RAW preserva os 25 digitos do DARJ. Escritas em lote reduzem chamadas ao Sheets.
            planilha.batch_update([
                {'range': endereco_celula(linha, colunas[campo]), 'values': [[dados[campo]]]}
                for linha in reservadas for campo in ('numero', 'vencimento', 'valor')
            ], value_input_option='RAW')
            planilha.batch_update([
                {'range': endereco_celula(linha, colunas['link']), 'values': [[formula]]}
                for linha in reservadas
            ], value_input_option='USER_ENTERED')
            ler_atual(alvo, 'PROCESSANDO', dados, formula)
            planilha.batch_update([
                {'range': endereco_celula(linha, colunas['status']), 'values': [['X']]}
                for linha in reservadas
            ], value_input_option='RAW')
            ler_atual(alvo, 'X', dados, formula)
            resultado['X'] += 1  # Conta guias, nao parcelas.
            resultado['linhas_concluidas'] += len(alvo.origens)
        except Exception as exc:
            status = 'REVISAR' if estado['envio'] else 'ERRO'
            falhas_status = []
            originais = dict(alvo.origens)
            for linha in reservadas:
                try:
                    # Se linhas/colunas mudaram, nao sobrescrever o status de outra NF.
                    cabecalho = planilha.row_values(linha_cabecalho)
                    if resolver_colunas(cabecalho) != colunas:
                        raise RuntimeError('cabecalhos alterados; status preservado')
                    atual = registro_da_linha(planilha.row_values(linha), colunas)
                    original = originais[linha]
                    if (identidade_nota(atual['nota']) != identidade_nota(original['nota'])
                            or atual.get('centro', '') != original.get('centro', '')):
                        raise RuntimeError('linha pertence a outra NF/centro; status preservado')
                    planilha.update_cell(linha, colunas['status'], status)
                except Exception as erro_status:
                    falhas_status.append(f'{linha}: {erro_status}')
            if falhas_status:
                raise RuntimeError(f'NF {alvo.nota_raw}: {exc}; status nao confirmado em {falhas_status}; conferir o grupo sem reemitir') from exc
            raise RuntimeError(f'NF {alvo.nota_raw}, linha {alvo.linha}: {status}; lote interrompido sem repetir a emissao: {exc}') from exc
        if intervalo and indice + 1 < len(pendentes):
            time.sleep(intervalo)
    return resultado
'''],
            },
        },
        'helpers': {
            'CalculoPortal': {
                'source': r'''@dataclass(frozen=True)
class CalculoPortal:
    """Principal e encargos auditados; nunca substitui os dados de entrada."""
    icms: Decimal
    fecp: Decimal
    mora_icms: Decimal
    multa_icms: Decimal
    mora_fecp: Decimal
    multa_fecp: Decimal
    total_icms: Decimal
    total_fecp: Decimal

    @property
    def total(self):
        return self.total_icms + self.total_fecp

    @property
    def encargos(self):
        return self.mora_icms + self.multa_icms + self.mora_fecp + self.multa_fecp

    def validar(self, alvo):
        for nome in self.__dataclass_fields__:
            valor = getattr(self, nome)
            if not isinstance(valor, Decimal):
                raise ValueError(f'Calculo do portal: {nome} precisa ser Decimal')
            dinheiro(valor)  # Exige valor finito, nao negativo e centavos exatos.
        if alvo.icms + alvo.fecp != alvo.total or alvo.total <= 0:
            raise ValueError('Principal do alvo inconsistente')
        if self.icms != alvo.icms or self.fecp != alvo.fecp:
            raise ValueError('Principal informado no portal difere da planilha')
        if self.total_icms != self.icms + self.mora_icms + self.multa_icms:
            raise ValueError('Total ICMS nao confere com principal + mora + multa')
        if self.total_fecp != self.fecp + self.mora_fecp + self.multa_fecp:
            raise ValueError('Total FECP nao confere com principal + mora + multa')
        if self.total != alvo.total + self.encargos:
            raise ValueError('Total final do portal inconsistente')
        if self.encargos and alvo.pagamento <= alvo.vencimento:
            raise ValueError('Encargos inesperados para pagamento sem atraso')
        return self
''',
            },
            'EmissaoPortal': {
                'source': r'''@dataclass(frozen=True)
class EmissaoPortal:
    caminho: Path
    calculo: CalculoPortal
''',
            },
            'conferir_calculo_portal': {
                'source': r'''def conferir_calculo_portal(alvo, campos):
    mapeamento = {
        'icms': 'txtIcmsInformado', 'fecp': 'txtFecpInformado',
        'mora_icms': 'txtMoraIcms', 'multa_icms': 'txtMultaMoraIcms',
        'mora_fecp': 'txtMoraFecp', 'multa_fecp': 'txtMultaMoraFecp',
        'total_icms': 'txtTotalIcms', 'total_fecp': 'txtTotalFecp',
    }
    try:
        valores = {nome: dinheiro(campos[campo]) for nome, campo in mapeamento.items()}
        atualizado_icms = dinheiro(campos['txtIcmsAtualizado'])
        atualizado_fecp = dinheiro(campos['txtFecpAtualizado'])
    except KeyError as exc:
        raise ValueError(f'Campo obrigatorio do calculo ausente: {exc.args[0]}') from exc
    if atualizado_icms != alvo.icms or atualizado_fecp != alvo.fecp:
        raise ValueError('Principal atualizado divergiu; correcao monetaria exige conferencia manual')
    return CalculoPortal(**valores).validar(alvo)
''',
            },
            'total_esperado': {
                'source': r'''def total_esperado(alvo, calculo=None):
    if calculo is None:
        return alvo.total
    if not isinstance(calculo, CalculoPortal):
        raise ValueError('Calculo do portal ausente ou invalido')
    return calculo.validar(alvo).total
''',
            },
        },
        'before': 'extrair_dados_pdf',
    },
}

ARQUIVOS_TESTE = {
    'tests/test_portal.py': {
        'source': r'''"""Testa a sequência de confirmação observada no portal, sem usar a rede."""
import ast
from pathlib import Path
import types
import unittest
from datetime import date
from decimal import Decimal
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controle_darj import dinheiro, brl

BOT = Path(__file__).resolve().parents[1] / 'bot.py'

class Campo:
    def __init__(self, value='', readonly=False):
        self.value, self.readonly = value, readonly
    def get_attribute(self, name):
        return self.value if name == 'value' else None
    def get_property(self, name):
        return self.readonly if name == 'readOnly' else None
    def clear(self): self.value=''
    def send_keys(self, value): self.value=value

class Driver:
    def __init__(self):
        self.campo = Campo('20/10/2026', True)
        self.botao = Campo('Alterar')
        self.clicks = 0
        self.botao.click = self.click
    def click(self):
        self.clicks += 1
        if self.botao.value == 'Alterar':
            self.campo.value = ''
            self.campo.readonly = False
            self.botao.value = 'Confirmar!'
        else:
            self.campo.readonly = True
            self.botao.value = 'Alterar'
    def find_element(self, by, selector):
        return self.campo if selector == 'txtDataPagamento' else self.botao

class DataPagamento(unittest.TestCase):
    def test_confirmacao_real_da_data_e_obrigatoria(self):
        ns={}
        if BOT.exists():
            tree=ast.parse(BOT.read_text(encoding='utf-8-sig'))
            defs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='confirmar_data_pagamento']
            exec(compile(ast.Module(body=defs,type_ignores=[]),str(BOT),'exec'),ns)
        self.assertIn('confirmar_data_pagamento',ns,'A data ainda nao possui confirmacao explicita')
        driver=Driver()
        def esperar(driver, wait, condicao):
            if not condicao(driver): raise TimeoutError('condicao nao satisfeita')
            return True
        def preencher(driver, wait, campo_id, texto):
            campo=driver.find_element('id',campo_id); campo.clear(); campo.send_keys(texto)
        ns.update(By=types.SimpleNamespace(ID='id'),esperar=esperar,preencher=preencher)
        ns['confirmar_data_pagamento'](driver,object(),'22/10/2026')
        self.assertEqual(driver.campo.value,'22/10/2026')
        self.assertTrue(driver.campo.readonly)
        self.assertEqual(driver.botao.value,'Alterar')
        self.assertEqual(driver.clicks,2)

    def test_total_de_itens_anteriores_nao_bloqueia_auditoria_do_item_atual(self):
        tree=ast.parse(BOT.read_text(encoding='utf-8-sig'))
        defs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='auditar_formulario']
        valores={
            'txtIcmsInformado':'100,00','txtFecpInformado':'20,00',
            'txtTotalIcms':'100,00','txtTotalFecp':'20,00','txtTotalDocs':'R$ 0,00',
            'txtIcmsAtualizado':'100,00','txtFecpAtualizado':'20,00',
            'txtMoraIcms':'0,00','txtMultaMoraIcms':'0,00',
            'txtMoraFecp':'0,00','txtMultaMoraFecp':'0,00',
            'btnAlterarDataPagamento':'Alterar','txtDataPagamento':'22/10/2026',
            'txtDataVencimento':'22/10/2026','txtPeriodo':'10/2026',
            'txtJustificativa':'NF 345','slcNaturezaLista':'4','slcListaProduto':'442',
        }
        driver=types.SimpleNamespace(find_element=lambda by,sel:Campo(valores[sel]))
        alvo=types.SimpleNamespace(icms=Decimal('100.00'),fecp=Decimal('20.00'),total=Decimal('120.00'),
                                   pagamento=date(2026,10,22),vencimento=date(2026,10,22),periodo='10/2026',nota_raw='345')
        def esperar(d,w,c):
            resultado = c(d)
            if not resultado: raise TimeoutError('A auditoria recusou o item valido')
            return resultado
        ns={'By':types.SimpleNamespace(ID='id'),'dinheiro':dinheiro,'brl':brl,
            'esperar':esperar,'aguardar_ajax':lambda *args:None}
        exec(compile(ast.Module(body=defs,type_ignores=[]),str(BOT),'exec'),ns)
        ns['auditar_formulario'](driver,object(),alvo)

if __name__=='__main__': unittest.main(verbosity=2)
''',
        'references': [r'''"""Testa a sequência de confirmação observada no portal, sem usar a rede."""
import ast
from pathlib import Path
import types
import unittest
from datetime import date
from decimal import Decimal
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controle_darj import dinheiro, brl

BOT = Path(__file__).resolve().parents[1] / 'bot.py'

class Campo:
    def __init__(self, value='', readonly=False):
        self.value, self.readonly = value, readonly
    def get_attribute(self, name):
        return self.value if name == 'value' else None
    def get_property(self, name):
        return self.readonly if name == 'readOnly' else None
    def clear(self): self.value=''
    def send_keys(self, value): self.value=value

class Driver:
    def __init__(self):
        self.campo = Campo('20/10/2026', True)
        self.botao = Campo('Alterar')
        self.clicks = 0
        self.botao.click = self.click
    def click(self):
        self.clicks += 1
        if self.botao.value == 'Alterar':
            self.campo.value = ''
            self.campo.readonly = False
            self.botao.value = 'Confirmar!'
        else:
            self.campo.readonly = True
            self.botao.value = 'Alterar'
    def find_element(self, by, selector):
        return self.campo if selector == 'txtDataPagamento' else self.botao

class DataPagamento(unittest.TestCase):
    def test_confirmacao_real_da_data_e_obrigatoria(self):
        ns={}
        if BOT.exists():
            tree=ast.parse(BOT.read_text(encoding='utf-8-sig'))
            defs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='confirmar_data_pagamento']
            exec(compile(ast.Module(body=defs,type_ignores=[]),str(BOT),'exec'),ns)
        self.assertIn('confirmar_data_pagamento',ns,'A data ainda nao possui confirmacao explicita')
        driver=Driver()
        def esperar(driver, wait, condicao):
            if not condicao(driver): raise TimeoutError('condicao nao satisfeita')
            return True
        def preencher(driver, wait, campo_id, texto):
            campo=driver.find_element('id',campo_id); campo.clear(); campo.send_keys(texto)
        ns.update(By=types.SimpleNamespace(ID='id'),esperar=esperar,preencher=preencher)
        ns['confirmar_data_pagamento'](driver,object(),'22/10/2026')
        self.assertEqual(driver.campo.value,'22/10/2026')
        self.assertTrue(driver.campo.readonly)
        self.assertEqual(driver.botao.value,'Alterar')
        self.assertEqual(driver.clicks,2)

    def test_total_de_itens_anteriores_nao_bloqueia_auditoria_do_item_atual(self):
        tree=ast.parse(BOT.read_text(encoding='utf-8-sig'))
        defs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='auditar_formulario']
        valores={
            'txtIcmsInformado':'100,00','txtFecpInformado':'20,00',
            'txtTotalIcms':'100,00','txtTotalFecp':'20,00','txtTotalDocs':'R$ 0,00',
            'btnAlterarDataPagamento':'Alterar','txtDataPagamento':'22/10/2026',
            'txtDataVencimento':'22/10/2026','txtPeriodo':'10/2026',
            'txtJustificativa':'NF 345','slcNaturezaLista':'4','slcListaProduto':'442',
        }
        driver=types.SimpleNamespace(find_element=lambda by,sel:Campo(valores[sel]))
        alvo=types.SimpleNamespace(icms=Decimal('100.00'),fecp=Decimal('20.00'),total=Decimal('120.00'),
                                   pagamento=date(2026,10,22),vencimento=date(2026,10,22),periodo='10/2026',nota_raw='345')
        def esperar(d,w,c):
            if not c(d): raise TimeoutError('A auditoria recusou o item valido')
        ns={'By':types.SimpleNamespace(ID='id'),'dinheiro':dinheiro,'brl':brl,
            'esperar':esperar,'aguardar_ajax':lambda *args:None}
        exec(compile(ast.Module(body=defs,type_ignores=[]),str(BOT),'exec'),ns)
        ns['auditar_formulario'](driver,object(),alvo)

if __name__=='__main__': unittest.main(verbosity=2)
'''],
    },
    'tests/test_encargos.py': {
        'source': r'''"""Encargos do portal RJ: somente calculos, DOM, planilha e PDFs locais simulados."""
import ast
from dataclasses import replace
from datetime import date
from decimal import Decimal
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest


STAGE = Path(os.environ.get('RJ_ENCARGOS_STAGE',
             str(Path(__file__).resolve().parents[1])))
sys.path.insert(0, str(STAGE / 'tests'))
sys.path.insert(0, str(STAGE))
import controle_darj as c
from test_controle import Sheet, pdf_fixture, CNPJ


HOJE = date(2026, 11, 3)
NUMERO = '0123456789012345678901234'
HEADERS = ['Data entrada', 'Nº Nota Fiscal', 'Centro', 'DARJ Normal', 'FECP',
           'TOTAL DA GUIA DE ICMS ST', 'PROC DARJ', 'Nº DARJ', 'Vcto DARJ',
           'Valor DARJ', 'Link DARJ', 'ALQ ICMS']


def rows_grupo():
    return [
        ['30.10.2026', '650874-7', 'RJ01', '1000,00', '100,00', '1100,00',
         '', '', '', '', '', '4%'],
        ['', '650874-7', 'RJ01', '953,44', '114,49', '1067,93',
         '', '', '', '', '', '12%'],
        ['', 'SOMA VALORES', '', '1953,44', '214,49', '2167,93',
         '', '', '', '', '', ''],
    ]


def alvo_padrao():
    return c.planejar_lote([['Titulo'], HEADERS] + rows_grupo(), HOJE, set(), 2)[1][0]


def calculo_padrao(**alteracoes):
    valores = dict(icms=Decimal('1953.44'), fecp=Decimal('214.49'),
                   mora_icms=Decimal('19.53'), multa_icms=Decimal('6.45'),
                   mora_fecp=Decimal('2.14'), multa_fecp=Decimal('0.71'),
                   total_icms=Decimal('1979.42'), total_fecp=Decimal('217.34'))
    valores.update(alteracoes)
    return c.CalculoPortal(**valores)


def campos_padrao(**alteracoes):
    valores = {
        'txtIcmsInformado': '1.953,44', 'txtFecpInformado': '214,49',
        'txtIcmsAtualizado': '1.953,44', 'txtFecpAtualizado': '214,49',
        'txtMoraIcms': '19,53', 'txtMultaMoraIcms': '6,45',
        'txtMoraFecp': '2,14', 'txtMultaMoraFecp': '0,71',
        'txtTotalIcms': '1.979,42', 'txtTotalFecp': '217,34',
    }
    valores.update(alteracoes)
    return valores


class CalculoEncargos(unittest.TestCase):
    def test_caso_observado_preserva_principal_e_separa_final(self):
        alvo, calculo = alvo_padrao(), calculo_padrao()
        calculo.validar(alvo)
        self.assertEqual(alvo.total, Decimal('2167.93'))
        self.assertEqual(calculo.encargos, Decimal('28.83'))
        self.assertEqual(calculo.total, Decimal('2196.76'))
        self.assertEqual(c.total_esperado(alvo, calculo), Decimal('2196.76'))
        self.assertEqual((alvo.pagamento, alvo.vencimento),
                         (HOJE, date(2026, 10, 31)))

    def test_sem_calculo_continua_usando_principal(self):
        self.assertEqual(c.total_esperado(alvo_padrao()), Decimal('2167.93'))

    def test_sem_encargos_funciona_na_data_de_vencimento(self):
        alvo = replace(alvo_padrao(), pagamento=date(2026, 10, 31))
        calculo = calculo_padrao(mora_icms=Decimal('0'), multa_icms=Decimal('0'),
                                mora_fecp=Decimal('0'), multa_fecp=Decimal('0'),
                                total_icms=alvo.icms, total_fecp=alvo.fecp)
        calculo.validar(alvo)
        self.assertEqual(c.total_esperado(alvo, calculo), alvo.total)

    def test_principal_divergente_nao_passa_mesmo_com_soma_consistente(self):
        for mudanca in ({'icms': Decimal('1953.45'), 'total_icms': Decimal('1979.43')},
                        {'fecp': Decimal('214.50'), 'total_fecp': Decimal('217.35')}):
            with self.subTest(mudanca=mudanca), self.assertRaises((ValueError, RuntimeError)):
                calculo_padrao(**mudanca).validar(alvo_padrao())

    def test_diferenca_de_centavo_em_cada_total_bloqueia(self):
        for campo, valor in (('total_icms', '1979.43'), ('total_fecp', '217.35')):
            with self.subTest(campo=campo), self.assertRaises((ValueError, RuntimeError)):
                c.total_esperado(alvo_padrao(), calculo_padrao(**{campo: Decimal(valor)}))

    def test_valores_negativos_nao_finitos_e_fracao_de_centavo_bloqueiam(self):
        for valor in (Decimal('-0.01'), Decimal('NaN'), Decimal('Infinity'), Decimal('0.001')):
            with self.subTest(valor=valor), self.assertRaises((ValueError, RuntimeError)):
                calculo_padrao(mora_icms=valor).validar(alvo_padrao())

    def test_encargos_bloqueiam_quando_pagamento_nao_posterior_ao_vencimento(self):
        for pagamento in (date(2026, 10, 31), date(2026, 10, 30)):
            with self.subTest(pagamento=pagamento), self.assertRaises((ValueError, RuntimeError)):
                calculo_padrao().validar(replace(alvo_padrao(), pagamento=pagamento))

    def test_campos_do_portal_geram_calculo_exato(self):
        calculo = c.conferir_calculo_portal(alvo_padrao(), campos_padrao())
        self.assertEqual(calculo, calculo_padrao())

    def test_campo_obrigatorio_ausente_ou_vazio_nao_vira_zero(self):
        for campo in campos_padrao():
            for ausente in (True, False):
                campos = campos_padrao()
                if ausente:
                    del campos[campo]
                else:
                    campos[campo] = ''
                with self.subTest(campo=campo, ausente=ausente), \
                        self.assertRaises((ValueError, RuntimeError, KeyError)):
                    c.conferir_calculo_portal(alvo_padrao(), campos)

    def test_atualizacao_monetaria_nao_autorizada_bloqueia(self):
        for campo, valor in (('txtIcmsAtualizado', '1953,45'),
                             ('txtFecpAtualizado', '214,50')):
            with self.subTest(campo=campo), self.assertRaises((ValueError, RuntimeError)):
                c.conferir_calculo_portal(alvo_padrao(), campos_padrao(**{campo: valor}))


class Campo:
    def __init__(self, valor='', texto=''):
        self.valor, self.text, self.cliques = valor, texto, 0

    def get_attribute(self, nome):
        return self.valor if nome == 'value' else None

    def click(self):
        self.cliques += 1


def bot_funcao(nome, **extras):
    """Extrai uma funcao sem importar o bot nem iniciar navegador/servicos."""
    caminho = STAGE / 'bot.py'
    tree = ast.parse(caminho.read_text(encoding='utf-8-sig'))
    definicoes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == nome]
    def esperar(driver, wait, condicao):
        resultado = condicao(driver)
        if not resultado:
            raise TimeoutError('Condicao do DOM nao satisfeita')
        return resultado
    ns = dict(By=types.SimpleNamespace(ID='id', CSS_SELECTOR='css', XPATH='xpath'),
              dinheiro=c.dinheiro, brl=c.brl, CalculoPortal=c.CalculoPortal,
              conferir_calculo_portal=c.conferir_calculo_portal,
              total_esperado=c.total_esperado, esperar=esperar,
              aguardar_ajax=lambda *args: None, CNPJ_RESPONSAVEL=CNPJ)
    ns.update(extras)
    exec(compile(ast.Module(body=definicoes, type_ignores=[]), str(caminho), 'exec'), ns)
    return ns[nome]


class AuditoriasPortalOffline(unittest.TestCase):
    def test_formulario_retorna_calculo_com_encargos_sem_usar_total_de_itens_anteriores(self):
        alvo = alvo_padrao()
        campos = campos_padrao()
        campos.update(btnAlterarDataPagamento='Alterar', txtDataPagamento='03/11/2026',
                      txtDataVencimento='31/10/2026', txtPeriodo='10/2026',
                      txtJustificativa='NF 650874-7', slcNaturezaLista='4',
                      slcListaProduto='442', txtTotalDocs='R$ 0,00')
        driver = types.SimpleNamespace(find_element=lambda by, sel: Campo(campos[sel]))
        calculo = bot_funcao('auditar_formulario')(driver, object(), alvo)
        self.assertEqual(calculo.total, Decimal('2196.76'))

    def test_resumo_confere_o_total_final_e_bloqueia_total_principal(self):
        botao = Campo()
        funcao = bot_funcao('auditar_resumo', botao_gerar_unico=lambda driver: botao)
        for total, aceita in (('2196,76', True), ('2167,93', False), ('2196,77', False)):
            campos = {'hdnQuantidadeDocs': '1', 'hdnValorTotal': total}
            driver = types.SimpleNamespace(find_element=lambda by, sel: Campo(campos[sel]),
                                           find_elements=lambda *args: [])
            with self.subTest(total=total):
                if aceita:
                    self.assertIs(funcao(driver, object(), alvo_padrao(), calculo_padrao()), botao)
                else:
                    with self.assertRaises((ValueError, RuntimeError)):
                        funcao(driver, object(), alvo_padrao(), calculo_padrao())

    def test_tela_emitida_so_abre_pdf_quando_total_final_confere(self):
        import re
        for total, cliques in (('2196,76', 1), ('2167,93', 0), ('2196,77', 0)):
            impressora = Campo()
            campos = {'hdnQuantidadeDocs': Campo('1'), 'hdnValorTotal': Campo(total),
                      "input[name='{pageFlow.documentoForm.cnpjCpf}']": Campo(CNPJ),
                      'h1.titulopagina': Campo(texto='DARJ emitido')}
            driver = types.SimpleNamespace(find_element=lambda by, sel: campos[sel])
            funcao = bot_funcao('abrir_darj_emitido', re=re,
                               esperar_elemento=lambda *args: impressora)
            with self.subTest(total=total):
                if cliques:
                    funcao(driver, object(), alvo_padrao(), calculo_padrao())
                else:
                    with self.assertRaises((ValueError, RuntimeError)):
                        funcao(driver, object(), alvo_padrao(), calculo_padrao())
                self.assertEqual(impressora.cliques, cliques)


class LoteEncargosOffline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)
        self.sheet = Sheet([['Titulo'], HEADERS] + rows_grupo())
        self.emissoes, self.uploads = [], []

    def emitir(self, alvo, antes):
        antes()
        self.emissoes.append(alvo)
        calculo = calculo_padrao()
        pdf = pdf_fixture(self.pasta / 'emitido.pdf', nota=alvo.nota_raw,
                          numero=NUMERO, total=c.brl(calculo.total),
                          vencimento=alvo.vencimento.strftime('%d/%m/%Y'))
        return c.EmissaoPortal(pdf, calculo)

    def upload(self, caminho):
        self.assertTrue(caminho.is_file())
        self.uploads.append(caminho)
        return 'driveEncargos123'

    def executar(self, emitir=None, upload=None, apenas_validar=False):
        return c.executar_lote(self.sheet.get_all_values(), self.sheet,
                               emitir or self.emitir, upload or self.upload, HOJE,
                               set(), CNPJ, apenas_validar=apenas_validar, intervalo=0)

    def test_grupo_grava_final_em_todas_parcelas_preservando_principal_e_subtotal(self):
        entradas = [r[:6].copy() for r in self.sheet.rows[2:4]]
        subtotal = self.sheet.rows[4].copy()
        resultado = self.executar()
        self.assertEqual((resultado['X'], resultado['linhas_concluidas']), (1, 2))
        self.assertEqual((len(self.emissoes), len(self.uploads)), (1, 1))
        self.assertEqual(self.emissoes[0].total, Decimal('2167.93'))
        for indice in (2, 3):
            self.assertEqual(self.sheet.rows[indice][6:10],
                             ['X', NUMERO, '31/10/2026', '2196,76'])
            self.assertIn('driveEncargos123', self.sheet.rows[indice][10])
        self.assertEqual([r[:6] for r in self.sheet.rows[2:4]], entradas)
        self.assertEqual(self.sheet.rows[4], subtotal)
        self.assertEqual(self.executar()['X'], 0)
        self.assertEqual(len(self.emissoes), 1)

    def test_pdf_com_principal_ou_um_centavo_divergente_impede_upload(self):
        for total in ('2167,93', '2196,77'):
            with self.subTest(total=total):
                self.sheet = Sheet([['Titulo'], HEADERS] + rows_grupo())
                def emitir(alvo, antes):
                    antes()
                    self.emissoes.append(alvo)
                    caminho = pdf_fixture(self.pasta / f'errado-{total}.pdf',
                                          nota=alvo.nota_raw, numero=NUMERO,
                                          total=total, vencimento='31/10/2026')
                    return c.EmissaoPortal(caminho, calculo_padrao())
                with self.assertRaisesRegex(RuntimeError, 'REVISAR'):
                    self.executar(emitir=emitir)
                self.assertEqual(self.uploads, [])
                self.assertEqual([r[6] for r in self.sheet.rows[2:4]], ['REVISAR', 'REVISAR'])
                emissoes_antes = len(self.emissoes)
                self.assertEqual(self.executar(emitir=emitir)['X'], 0)
                self.assertEqual(len(self.emissoes), emissoes_antes)

    def test_falha_upload_nao_grava_resultado_nem_reemite(self):
        def upload_falha(caminho):
            self.uploads.append(caminho)
            raise OSError('Drive indisponivel simulado')
        with self.assertRaisesRegex(RuntimeError, 'REVISAR'):
            self.executar(upload=upload_falha)
        self.assertEqual([r[6] for r in self.sheet.rows[2:4]], ['REVISAR', 'REVISAR'])
        self.assertEqual([r[7:11] for r in self.sheet.rows[2:4]], [[''] * 4, [''] * 4])
        self.assertEqual(self.executar()['X'], 0)
        self.assertEqual((len(self.emissoes), len(self.uploads)), (1, 1))

    def test_validar_nao_emite_nao_faz_upload_nem_escreve(self):
        self.assertEqual(self.executar(apenas_validar=True)['validadas'], 1)
        self.assertEqual((self.emissoes, self.uploads, self.sheet.writes), ([], [], []))


if __name__ == '__main__':
    unittest.main(verbosity=2)
''',
        'references': [],
    },
    'tests/test_fluxo_encargos.py': {
        'source': r'''"""Propagacao de total final e tentativa unica, sem navegador ou rede."""
import ast
import base64
from pathlib import Path
import re
import tempfile
import types
import unittest
from unittest.mock import Mock
import uuid

import controle_darj as c
from test_encargos import alvo_padrao, calculo_padrao, bot_funcao, Campo, CNPJ


class FluxoEncargos(unittest.TestCase):
    def test_emitir_propaga_calculo_em_todas_etapas_sem_repetir_cliques(self):
        self.fluxo(False)

    def test_emitir_sem_calculo_para_antes_de_confirmar(self):
        self.fluxo(True)

    def fluxo(self, sem_calculo):
        with tempfile.TemporaryDirectory() as tmp:
            alvo, calculo = alvo_padrao(), calculo_padrao()
            confirmar, gerar = Campo(), Campo()
            driver = types.SimpleNamespace(quit=Mock())
            antes = Mock()
            chamadas = []
            def resumo(d, w, a, calc):
                self.assertIs(calc, calculo); chamadas.append('resumo'); return gerar
            def abrir(d, w, a, calc):
                self.assertIs(calc, calculo); chamadas.append('abrir')
            def pdf(d, pasta, antigos, a, calculo=None):
                self.assertIs(calculo, calc_esperado); chamadas.append('pdf')
                return pasta/'darj.pdf'
            calc_esperado = calculo
            func = bot_funcao('emitir_portal', BASE=Path(tmp),uuid=uuid,
                criar_driver=lambda pasta:(driver,object()),
                preencher_formulario=lambda *args:None if sem_calculo else calculo,
                dump_debug=lambda *args:None,
                esperar=lambda *args:confirmar,
                EC=types.SimpleNamespace(element_to_be_clickable=lambda *args:None),
                auditar_resumo=resumo, abrir_darj_emitido=abrir, aguardar_pdf=pdf)
            if sem_calculo:
                with self.assertRaisesRegex(RuntimeError,'calculo auditado'):
                    func(alvo, antes)
                self.assertEqual(antes.call_count,0)
                self.assertEqual(chamadas,[])
            else:
                retorno=func(alvo,antes)
                self.assertIsInstance(retorno,c.EmissaoPortal)
                self.assertIs(retorno.calculo,calculo)
                self.assertEqual(antes.call_count,2)
                self.assertEqual(chamadas,['resumo','abrir','pdf'])
            self.assertEqual(confirmar.cliques,0 if sem_calculo else 1)
            self.assertEqual(gerar.cliques,0 if sem_calculo else 1)
            driver.quit.assert_called_once()

    def test_fallback_html_so_imprime_total_final_auditado(self):
        for total, aceita in [('2.196,76',True),('2.167,93',False),('2.196,77',False)]:
            with self.subTest(total=total), tempfile.TemporaryDirectory() as tmp:
                texto=(f'DARJ\nNosso Numero: 0123456789012345678901234\n'
                       f'CNPJ: 58.248.352/0012-01\nInformacoes Complementares: NF 650874-7\n'
                       f'Vencimento: 31/10/2026\nData Validade: 03/11/2026\nValor Total: {total}')
                driver=types.SimpleNamespace(current_window_handle='aba',window_handles=['aba'],
                    switch_to=types.SimpleNamespace(window=Mock()),
                    execute_script=Mock(return_value={'texto':texto,'pronto':True,'barras':True}),
                    execute_cdp_cmd=Mock(return_value={'data':base64.b64encode(b'%PDF-simulado').decode()}))
                relogio=types.SimpleNamespace(monotonic=Mock(side_effect=[0,0.1,2]),sleep=lambda *a:None)
                func=bot_funcao('aguardar_pdf', time=relogio,re=re,base64=base64,
                    verificar_mensagens=lambda *a:None,extrair_dados_pdf=c.extrair_dados_pdf)
                if aceita:
                    caminho=func(driver,Path(tmp),set(),alvo_padrao(),timeout=1,calculo=calculo_padrao())
                    self.assertTrue(caminho.is_file())
                    driver.execute_cdp_cmd.assert_called_once()
                else:
                    with self.assertRaises(TimeoutError):
                        func(driver,Path(tmp),set(),alvo_padrao(),timeout=1,calculo=calculo_padrao())
                    driver.execute_cdp_cmd.assert_not_called()
''',
        'references': [],
    },
    'tests/test_fechamento.py': {
        'source': r'''"""Regra de fechamento autorizada: simulacoes locais, sem emissao."""
from datetime import date
import unittest
import controle_darj as c

class Fechamento(unittest.TestCase):
    def test_caso_real_29_outubro(self):
        self.assertEqual(c.calcular_datas(date(2026,10,28), date(2026,10,29), {date(2026,11,2)}), (date(2026,10,30),)*2)
    def test_execucao_no_fechamento(self):
        self.assertEqual(c.calcular_datas(date(2026,10,28), date(2026,10,30), {date(2026,11,2)}), (date(2026,10,30),)*2)
    def test_dois_dias_antes_do_fechamento(self):
        self.assertEqual(c.calcular_datas(date(2026,10,28), date(2026,10,28), set()), (date(2026,10,30),)*2)
    def test_feriado_no_ultimo_dia_util(self):
        self.assertEqual(c.calcular_datas(date(2026,10,28), date(2026,10,29), {date(2026,10,30)}), (date(2026,10,29),)*2)
    def test_dezembro_para_janeiro(self):
        self.assertEqual(c.calcular_datas(date(2026,12,30), date(2026,12,30), {date(2027,1,1)}), (date(2026,12,31),)*2)
    def test_meio_do_mes_preserva_dois_corridos(self):
        self.assertEqual(c.calcular_datas(date(2026,10,20), date(2026,10,20), set()), (date(2026,10,22),)*2)
    def test_fechamento_ja_passou_nao_retroage(self):
        self.assertEqual(c.calcular_datas(date(2026,9,30), date(2026,10,29), {date(2026,11,2)}), (date(2026,10,29), date(2026,9,30)))

    def test_caso_real_novembro_outubro(self):
        self.assertEqual(c.calcular_datas(date(2026,10,30),date(2026,11,3),set()),(date(2026,11,3),date(2026,10,31)))
    def test_vencimento_encerrado_nao_ajusta_feriado(self):
        self.assertEqual(c.calcular_datas(date(2026,10,30),date(2026,11,3),{date(2026,10,31)}),(date(2026,11,3),date(2026,10,31)))
    def test_fevereiro_bissexto(self):
        self.assertEqual(c.calcular_datas(date(2028,2,28),date(2028,3,1),set()),(date(2028,3,1),date(2028,2,29)))
    def test_mes_encerrado_ano_anterior(self):
        self.assertEqual(c.calcular_datas(date(2026,12,30),date(2027,1,4),set()),(date(2027,1,4),date(2026,12,31)))
''',
        'references': [r'''"""Regra de fechamento autorizada: simulacoes locais, sem emissao."""
from datetime import date
import unittest
import controle_darj as c

class Fechamento(unittest.TestCase):
    def test_caso_real_29_outubro(self):
        self.assertEqual(c.calcular_datas(date(2026,10,28), date(2026,10,29), {date(2026,11,2)}), (date(2026,10,30),)*2)
    def test_execucao_no_fechamento(self):
        self.assertEqual(c.calcular_datas(date(2026,10,28), date(2026,10,30), {date(2026,11,2)}), (date(2026,10,30),)*2)
    def test_dois_dias_antes_do_fechamento(self):
        self.assertEqual(c.calcular_datas(date(2026,10,28), date(2026,10,28), set()), (date(2026,10,30),)*2)
    def test_feriado_no_ultimo_dia_util(self):
        self.assertEqual(c.calcular_datas(date(2026,10,28), date(2026,10,29), {date(2026,10,30)}), (date(2026,10,29),)*2)
    def test_dezembro_para_janeiro(self):
        self.assertEqual(c.calcular_datas(date(2026,12,30), date(2026,12,30), {date(2027,1,1)}), (date(2026,12,31),)*2)
    def test_meio_do_mes_preserva_dois_corridos(self):
        self.assertEqual(c.calcular_datas(date(2026,10,20), date(2026,10,20), set()), (date(2026,10,22),)*2)
    def test_fechamento_ja_passou_nao_retroage(self):
        self.assertEqual(c.calcular_datas(date(2026,9,30), date(2026,10,29), {date(2026,11,2)}), (date(2026,10,29), date(2026,9,30)))

    def test_caso_real_novembro_outubro(self):
        self.assertEqual(c.calcular_datas(date(2026,10,30),date(2026,11,3),set()),(date(2026,11,3),date(2026,10,31)))
    def test_vencimento_encerrado_nao_ajusta_feriado(self):
        self.assertEqual(c.calcular_datas(date(2026,10,30),date(2026,11,3),{date(2026,10,31)}),(date(2026,11,3),date(2026,10,31)))
    def test_fevereiro_bissexto(self):
        self.assertEqual(c.calcular_datas(date(2028,2,28),date(2028,3,1),set()),(date(2028,3,1),date(2028,2,29)))
    def test_mes_encerrado_ano_anterior(self):
        self.assertEqual(c.calcular_datas(date(2026,12,30),date(2027,1,4),set()),(date(2027,1,4),date(2026,12,31)))
'''],
    },
}


def fingerprint(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def hashes_permitidos(item, modulo=False):
    # As referencias e o arquivo atual sao analisados no MESMO Python.
    # Nenhum hash calculado em outra versao do interpretador e usado.
    fontes = [item['source']] + item.get('references', [])
    arvores = [ast.parse(fonte) for fonte in fontes]
    return {fingerprint(arvore if modulo else arvore.body[0]) for arvore in arvores}


def start_line(node):
    return min([node.lineno] + [d.lineno for d in node.decorator_list])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument('--verificar', action='store_true')
    modo.add_argument('--aplicar', action='store_true')
    args = parser.parse_args()
    root = Path.cwd().resolve()
    if not all((root/n).is_file() for n in ('bot.py', 'controle_darj.py')):
        raise SystemExit('Execute na raiz do projeto, junto de bot.py e controle_darj.py.')
    plano = {}
    for nome, spec in FUNCOES.items():
        path = root/nome
        original = path.read_bytes()
        texto = original.decode('utf-8-sig')
        defs = {}
        for n in ast.parse(texto).body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                if n.name in defs:
                    raise SystemExit(f'{nome}: definicao duplicada {n.name}; nenhuma alteracao aplicada.')
                defs[n.name] = n
        edits = []
        for chave, item in spec['functions'].items():
            if chave not in defs or fingerprint(defs[chave]) not in hashes_permitidos(item):
                raise SystemExit(f'{nome}: versao inesperada de {chave}; nenhuma alteracao aplicada. Envie esta mensagem para conferencia.')
            node = defs[chave]
            novo = item['source']
            for variante in item.get('variants', []):
                if fingerprint(node) in hashes_permitidos(variante):
                    novo = variante['source']
                    break
            if source_normalized(texto, node) != novo:
                edits.append((start_line(node)-1, node.end_lineno, novo))
        helpers = spec.get('helpers', {})
        presentes = [n for n in helpers if n in defs]
        if presentes:
            if len(presentes) != len(helpers) or any(fingerprint(defs[n]) not in hashes_permitidos(helpers[n]) for n in presentes):
                raise SystemExit(f'{nome}: suporte a encargos parcial ou diferente; nenhuma alteracao aplicada.')
        elif helpers:
            pos = start_line(defs[spec['before']])-1
            edits.append((pos,pos,'\n\n'.join(item['source'] for item in helpers.values())+'\n\n'))
        linhas = texto.splitlines(keepends=True)
        # Mesmo indice: substitui a funcao primeiro; depois insere os helpers antes dela.
        for inicio, fim, novo in sorted(edits, key=lambda e:(e[0],e[1]), reverse=True):
            linhas[inicio:fim] = [novo]
        plano[nome] = (original, ''.join(linhas).encode('utf-8'))
    for nome, spec in ARQUIVOS_TESTE.items():
        path = root/nome
        original = path.read_bytes() if path.exists() else None
        if original is not None:
            if fingerprint(ast.parse(original.decode('utf-8-sig'))) not in hashes_permitidos(spec, modulo=True):
                raise SystemExit(f'{nome}: testes modificados fora desta revisao; nenhuma alteracao aplicada.')
        plano[nome] = (original,spec['source'].encode('utf-8'))
    plano = {n:v for n,v in plano.items() if v[0] != v[1]}
    for nome, (_,novo) in plano.items():
        path = root/nome
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise SystemExit(f'Caminho fora do projeto: {nome}')
        compile(novo.decode('utf-8'),nome,'exec')
    if not plano:
        print('Atualizacao ja aplicada. Nenhum arquivo alterado.')
        return
    print('Arquivos a atualizar: '+', '.join(plano))
    if args.verificar:
        print('Conferencia concluida. Para aplicar: python aplicar_encargos_v3.py --aplicar')
        return
    # Verifica novamente antes de escrever; o arquivo completo e preservado em backup.
    for nome,(original,_) in plano.items():
        path=root/nome
        if (path.read_bytes() if path.exists() else None) != original:
            raise SystemExit('Arquivo alterado durante a preparacao; nenhuma mudanca aplicada.')
    backup=root/('.backup_encargos_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6])
    backup.mkdir()
    escritos=[]
    try:
        for nome,(original,novo) in plano.items():
            path=root/nome
            if original is not None:
                destino=backup/nome; destino.parent.mkdir(parents=True,exist_ok=True)
                destino.write_bytes(original)
            path.parent.mkdir(parents=True,exist_ok=True)
            escritos.append(nome)
            path.write_bytes(novo)
    except Exception:
        for nome in reversed(escritos):
            original,_=plano[nome]
            path=root/nome
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        raise
    print('Atualizacao aplicada. Backup: '+str(backup))
    print('Agora execute: python -m unittest discover -s tests -v')
    print('Nenhuma guia foi emitida; a planilha nao foi alterada.')


def source_normalized(texto,node):
    return '\n'.join(texto.splitlines()[start_line(node)-1:node.end_lineno])+'\n'


if __name__ == '__main__':
    main()
