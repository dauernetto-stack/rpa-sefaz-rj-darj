"""Controle de lote e validações locais. Importar este módulo não acessa serviços."""
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import time
import unicodedata


def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(texto))
                   if not unicodedata.combining(c)).strip().casefold()


ALIASES = {
    'data': ['Data entrada'], 'nota': ['Nº Nota Fiscal', 'N° Nota Fiscal', 'Nota Fiscal'],
    'icms': ['DARJ Normal'], 'fecp': ['FECP'], 'total': ['TOTAL DA GUIA DE ICMS ST'],
    'status': ['PROC DARJ'], 'numero': ['Nº DARJ', 'N° DARJ', 'Numero DARJ'],
    'vencimento': ['Vcto DARJ', 'Vencimento DARJ'], 'valor': ['Valor DARJ'],
    'link': ['Link DARJ'], 'centro': ['Centro'],
    'aliquota': ['ALQ ICMS', 'Aliquota ICMS', 'Alíquota ICMS'],
}


def resolver_colunas(cabecalhos):
    resultado = {}
    for campo, nomes in ALIASES.items():
        indices = [i + 1 for i, h in enumerate(cabecalhos)
                   if normalizar(h) in {normalizar(n) for n in nomes}]
        if len(indices) > 1 or (not indices and campo not in ('centro', 'aliquota')):
            raise ValueError(f'Coluna obrigatoria ausente ou ambigua: {nomes[0]}')
        if indices:
            resultado[campo] = indices[0]
    return resultado


def registro_da_linha(valores, colunas):
    return {campo: str(valores[col - 1]).strip() if col <= len(valores) else ''
            for campo, col in colunas.items()}


def ler_registros(valores, linha_cabecalho=2):
    if len(valores) < linha_cabecalho:
        raise ValueError('Planilha sem a linha de cabecalhos esperada')
    colunas = resolver_colunas(valores[linha_cabecalho - 1])
    registros = [(linha, registro_da_linha(v, colunas))
                 for linha, v in enumerate(valores[linha_cabecalho:], linha_cabecalho + 1)
                 if any(str(c).strip() for c in v)]
    return colunas, registros


def dinheiro(valor):
    """Aceita valores numéricos ou texto BRL; nunca converte erro em zero."""
    if valor is None or isinstance(valor, bool):
        raise ValueError(f'Valor monetario invalido: {valor!r}')
    texto = str(valor).strip().replace('\xa0', '').replace('R$', '').replace(' ', '')
    if isinstance(valor, (int, float, Decimal)):
        pass
    elif re.fullmatch(r'\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?', texto):
        texto = texto.replace('.', '').replace(',', '.')
    elif re.fullmatch(r'\d+(?:,\d{1,2})?', texto):
        texto = texto.replace(',', '.')
    elif not re.fullmatch(r'\d+\.\d{1,2}', texto):
        raise ValueError(f'Valor monetario invalido: {valor!r}')
    try:
        numero = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(f'Valor monetario invalido: {valor!r}') from exc
    if not numero.is_finite() or numero < 0 or numero != numero.quantize(Decimal('0.01')):
        raise ValueError(f'Valor monetario invalido: {valor!r}')
    return numero.quantize(Decimal('0.01'))


def brl(valor):
    return f'{valor:.2f}'.replace('.', ',')


def parse_data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    for formato in ('%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(valor).strip(), formato).date()
        except ValueError:
            pass
    raise ValueError(f'Data invalida: {valor!r}')


def dia_util(dia, feriados):
    return dia.weekday() < 5 and dia not in feriados


def calcular_datas(entrada, hoje, feriados):
    """D+2 corridos, limitado ao fechamento vigente."""
    from calendar import monthrange

    pagamento = hoje + timedelta(days=2)
    while not dia_util(pagamento, feriados):
        pagamento += timedelta(days=1)

    if (pagamento.year, pagamento.month) == (
        entrada.year, entrada.month
    ):
        vencimento = pagamento
    else:
        ultimo_dia = monthrange(
            entrada.year, entrada.month
        )[1]

        limite = date(
            entrada.year, entrada.month, ultimo_dia
        )
        while not dia_util(limite, feriados):
            limite -= timedelta(days=1)

        vencimento = limite if limite >= hoje else hoje

        # Antecipa o pagamento para o fechamento.
        if limite >= hoje:
            pagamento = min(pagamento, limite)

    return pagamento, vencimento


@dataclass(frozen=True)
class Alvo:
    linha: int
    nota_raw: str
    nota: str
    centro: str
    entrada: date
    icms: Decimal
    fecp: Decimal
    total: Decimal
    pagamento: date
    vencimento: date
    origem: dict
    origens: tuple = ()
    subtotal: object = None

    @property
    def periodo(self):
        return self.entrada.strftime('%m/%Y')


def preparar_alvo(linha, registro, hoje, feriados):
    nota_raw = registro['nota']
    if not re.fullmatch(r'\d+(?:-\d+)?', nota_raw):
        raise ValueError(f'Linha {linha}: nota fiscal ausente ou fora do formato numero-serie')
    icms, fecp, total = (dinheiro(registro[k]) for k in ('icms', 'fecp', 'total'))
    if total <= 0 or icms + fecp != total:
        raise ValueError(f'Linha {linha}: ICMS {brl(icms)} + FECP {brl(fecp)} = {brl(icms + fecp)}, mas total informado = {brl(total)}; conferir centavos e total positivo')
    entrada = parse_data(registro['data'])
    if entrada.year < 1900:
        raise ValueError(
            f'Linha {linha}: Data entrada {registro["data"]!r} tem ano {entrada.year:04d}; '
            'confira o ano na planilha (minimo 1900). Nenhuma emissao solicitada.'
        )
    if entrada > hoje:
        raise ValueError(f'Linha {linha}: Data entrada futura')
    pagamento, vencimento = calcular_datas(entrada, hoje, feriados)
    return Alvo(linha, nota_raw, nota_raw.split('-')[0], registro.get('centro', ''),
                entrada, icms, fecp, total, pagamento, vencimento, dict(registro))


def extrair_dados_pdf(texto, alvo, cnpj):
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


def validar_pdf(caminho, alvo, cnpj):
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


def tipo_linha_estrutural(registro):
    """Distingue modelos zerados e o rodapé Total de uma nota incompleta."""
    if registro['data'] or registro['status'] or any(
        registro[campo] for campo in ('numero', 'vencimento', 'valor', 'link')
    ):
        return None
    if normalizar(registro['nota']) == 'total':
        return 'total'
    if registro['nota']:
        return None
    try:
        if all(not registro[campo] or dinheiro(registro[campo]) == 0
               for campo in ('icms', 'fecp', 'total')):
            return 'modelo'
    except ValueError:
        pass
    return None


@dataclass(frozen=True)
class BlocoNF:
    linhas: tuple
    subtotal: object = None


CAMPOS_ENTRADA = ('data', 'nota', 'centro', 'aliquota', 'icms', 'fecp', 'total')
CAMPOS_RESULTADO = ('numero', 'vencimento', 'valor', 'link')


def identidade_nota(nota):
    texto = str(nota).strip()
    if not re.fullmatch(r'\d+(?:-\d+)?', texto):
        return texto
    return tuple(int(parte) for parte in texto.split('-'))


def separar_blocos(registros):
    """Agrupa apenas linhas fisicamente consecutivas; subtotal fecha o grupo."""
    blocos, atual, estruturais = [], [], Counter()
    for linha, registro in registros:
        rotulo = ' '.join(normalizar(registro['nota']).split())
        if rotulo == 'soma valores':
            if registro['data'] or registro['status'] or any(
                registro[c] for c in CAMPOS_RESULTADO
            ):
                raise ValueError(f'Linha {linha}: SOMA VALORES deve ser apenas subtotal, sem data/status/dados de guia')
            if not atual or linha != atual[-1][0] + 1:
                raise ValueError(f'Linha {linha}: SOMA VALORES sem grupo imediatamente anterior')
            blocos.append(BlocoNF(tuple(atual), (linha, dict(registro))))
            atual = []
            estruturais['subtotal'] += 1
            continue
        tipo = tipo_linha_estrutural(registro)
        if tipo:
            if atual:
                blocos.append(BlocoNF(tuple(atual)))
                atual = []
            estruturais[tipo] += 1
            continue
        continua = (atual and linha == atual[-1][0] + 1
                    and identidade_nota(registro['nota']) == identidade_nota(atual[0][1]['nota'])
                    and registro.get('centro', '') == atual[0][1].get('centro', ''))
        if not continua and atual:
            blocos.append(BlocoNF(tuple(atual)))
            atual = []
        atual.append((linha, dict(registro)))
    if atual:
        blocos.append(BlocoNF(tuple(atual)))
    return blocos, estruturais


def chave_bloco(bloco):
    _, r = bloco.linhas[0]
    try:
        periodo = parse_data(r['data']).strftime('%Y-%m')
    except ValueError:
        periodo = None
    return identidade_nota(r['nota']), r.get('centro', ''), periodo


def ler_aliquota(valor):
    texto = str(valor).strip().replace(' ', '').replace(',', '.')
    porcentagem = texto.endswith('%')
    if porcentagem:
        texto = texto[:-1]
    if not re.fullmatch(r'\d+(?:\.\d+)?', texto):
        raise ValueError(f'Aliquota invalida ou vazia: {valor!r}')
    numero = Decimal(texto)
    if porcentagem or numero > 1:
        numero /= 100
    if not Decimal('0') <= numero <= Decimal('1'):
        raise ValueError(f'Aliquota fora do intervalo de 0% a 100%: {valor!r}')
    return numero


def preparar_grupo(bloco, hoje, feriados):
    componentes = []
    aliquotas = set()
    primeira = bloco.linhas[0][1]
    for linha, original in bloco.linhas:
        registro = dict(original)
        if not registro['data']:
            registro['data'] = primeira['data']
        if len(bloco.linhas) > 1:
            if not original.get('aliquota', ''):
                raise RuntimeError(f'Linha {linha}: NF repetida exige ALQ ICMS preenchida em cada parcela')
            aliquota = ler_aliquota(original['aliquota'])
            if aliquota in aliquotas:
                raise RuntimeError(f'Linha {linha}: mesma NF e aliquota repetidas; conferir possivel duplicidade')
            aliquotas.add(aliquota)
        parte = preparar_alvo(linha, registro, hoje, feriados)
        if componentes and parte.entrada != componentes[0].entrada:
            raise ValueError(f'Linha {linha}: datas de entrada diferentes dentro da mesma NF')
        componentes.append(parte)
    icms = sum((p.icms for p in componentes), Decimal('0.00'))
    fecp = sum((p.fecp for p in componentes), Decimal('0.00'))
    total = icms + fecp
    if bloco.subtotal:
        linha, registro = bloco.subtotal
        for campo, esperado in (('icms', icms), ('fecp', fecp), ('total', total)):
            recebido = dinheiro(registro[campo])
            if recebido != esperado:
                raise ValueError(f'Linha {linha}: subtotal {campo} {brl(recebido)} difere da soma das parcelas {brl(esperado)}')
    return replace(componentes[0], icms=icms, fecp=fecp, total=total,
                   origem=dict(primeira), origens=bloco.linhas, subtotal=bloco.subtotal)


def planejar_lote(valores, hoje, feriados, linha_cabecalho):
    colunas, registros = ler_registros(valores, linha_cabecalho)
    blocos, estruturais = separar_blocos(registros)
    contagem = Counter(chave_bloco(b) for b in blocos)
    pendentes, x_incompletos = [], 0
    for bloco in blocos:
        marcadas = [bool(r['status']) for _, r in bloco.linhas]
        if any(marcadas) and not all(marcadas):
            raise RuntimeError(f'NF {bloco.linhas[0][1]["nota"]}: grupo parcialmente processado; conferir a guia existente sem reemitir')
        if all(marcadas):
            for linha, r in bloco.linhas:
                if normalizar(r['status']) == 'x' and not all(r[c] for c in CAMPOS_RESULTADO):
                    x_incompletos += 1
                    print(f'Linha {linha}: X sem dados completos do DARJ; conferir emissao anterior. Status preservado.')
            continue
        for linha, r in bloco.linhas:
            if any(r[c] for c in CAMPOS_RESULTADO):
                raise RuntimeError(f'Linha {linha}: ja possui dados de guia; conferir sem reemitir')
        if contagem[chave_bloco(bloco)] > 1:
            raise RuntimeError(f'NF {bloco.linhas[0][1]["nota"]}: aparece em blocos separados no mesmo periodo; reunir/conferir antes de emitir')
        pendentes.append(preparar_grupo(bloco, hoje, feriados))
    linhas_pendentes = sum(len(a.origens) for a in pendentes)
    resultado = {'X': 0, 'linhas_concluidas': 0, 'ignoradas': len(registros) - linhas_pendentes,
                 'validadas': len(pendentes), 'linhas_validadas': linhas_pendentes,
                 'modelos_ignorados': estruturais['modelo'], 'totais_ignorados': estruturais['total'],
                 'subtotais_conferidos': sum(bool(a.subtotal) for a in pendentes),
                 'x_incompletos': x_incompletos}
    return colunas, pendentes, resultado


def endereco_celula(linha, coluna):
    letras = ''
    while coluna:
        coluna, resto = divmod(coluna - 1, 26)
        letras = chr(65 + resto) + letras
    return f'{letras}{linha}'


def executar_lote(valores, planilha, emitir, subir_pdf, hoje, feriados, cnpj,
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
