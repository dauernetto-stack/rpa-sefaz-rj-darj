"""Controle de lote e validações locais. Importar este módulo não acessa serviços."""
from collections import Counter
from dataclasses import dataclass
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
}


def resolver_colunas(cabecalhos):
    resultado = {}
    for campo, nomes in ALIASES.items():
        indices = [i + 1 for i, h in enumerate(cabecalhos)
                   if normalizar(h) in {normalizar(n) for n in nomes}]
        if len(indices) > 1 or (not indices and campo != 'centro'):
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
    """Regra do primeiro ZIP RJ: D+2 corridos, ajustado para dia util."""
    from calendar import monthrange

    pagamento = hoje + timedelta(days=2)
    while not dia_util(pagamento, feriados):
        pagamento += timedelta(days=1)

    if (pagamento.year, pagamento.month) == (entrada.year, entrada.month):
        vencimento = pagamento
    else:
        ultimo_dia = monthrange(entrada.year, entrada.month)[1]
        limite = date(entrada.year, entrada.month, ultimo_dia)
        while not dia_util(limite, feriados):
            limite -= timedelta(days=1)
        vencimento = limite if limite >= hoje else hoje

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

    @property
    def periodo(self):
        return self.entrada.strftime('%m/%Y')


def preparar_alvo(linha, registro, hoje, feriados):
    nota_raw = registro['nota']
    if not re.fullmatch(r'\d+(?:-\d+)?', nota_raw):
        raise ValueError(f'Linha {linha}: nota fiscal ausente ou fora do formato numero-serie')
    icms, fecp, total = (dinheiro(registro[k]) for k in ('icms', 'fecp', 'total'))
    if total <= 0 or icms + fecp != total:
        raise ValueError(f'Linha {linha}: ICMS + FECP nao coincide exatamente com o total positivo')
    entrada = parse_data(registro['data'])
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


def executar_lote(valores, planilha, emitir, subir_pdf, hoje, feriados, cnpj,
                  apenas_validar=False, intervalo=5, linha_cabecalho=2):
    colunas, registros = ler_registros(valores, linha_cabecalho)
    pendentes = []
    chaves = []
    estruturais = Counter()
    x_incompletos = 0
    for linha, r in registros:
        tipo = tipo_linha_estrutural(r)
        if tipo:
            estruturais[tipo] += 1
            continue
        if r['nota'] and r['data']:
            try:
                chaves.append((r['nota'], parse_data(r['data']).strftime('%Y-%m')))
            except ValueError:
                if not r['status']:
                    raise
        if r['status']:
            if normalizar(r['status']) == 'x' and not all(
                r[campo] for campo in ('numero', 'vencimento', 'valor', 'link')
            ):
                x_incompletos += 1
                print(f'Linha {linha}: X sem dados completos do DARJ; conferir emissao anterior. Status preservado.')
            continue
        if r['numero'] or r['link']:
            raise RuntimeError(f'Linha {linha}: ja possui numero ou link; conferir sem reemitir')
        pendentes.append(preparar_alvo(linha, r, hoje, feriados))
    contagem = Counter(chaves)
    for alvo in pendentes:
        if contagem[(alvo.nota_raw, alvo.entrada.strftime('%Y-%m'))] > 1:
            raise RuntimeError(f'Linha {alvo.linha}: nota repetida no mesmo periodo; conferir antes de emitir')
    resultado = {'X': 0, 'ignoradas': len(registros) - len(pendentes), 'validadas': len(pendentes),
                 'modelos_ignorados': estruturais['modelo'], 'totais_ignorados': estruturais['total'],
                 'x_incompletos': x_incompletos}
    print(f'Lote: {len(pendentes)} pendentes validadas; {resultado["ignoradas"]} linhas ignoradas '
          f'({estruturais["modelo"]} modelos e {estruturais["total"]} totais).')
    if apenas_validar:
        return resultado

    def ler_atual(alvo, status):
        if resolver_colunas(planilha.row_values(linha_cabecalho)) != colunas:
            raise RuntimeError('Cabecalhos foram alterados durante o lote')
        atual = registro_da_linha(planilha.row_values(alvo.linha), colunas)
        if atual['status'] != status:
            raise RuntimeError(f'Linha {alvo.linha}: status mudou durante o processamento')
        if atual['numero'] or atual['link']:
            raise RuntimeError(f'Linha {alvo.linha}: numero/link apareceu durante o processamento')
        for campo in ('data', 'nota', 'centro', 'icms', 'fecp', 'total'):
            if atual.get(campo, '') != alvo.origem.get(campo, ''):
                raise RuntimeError(f'Linha {alvo.linha}: campo {campo} alterado durante o processamento')

    for indice, alvo in enumerate(pendentes):
        # Nova leitura antes de reservar: outra execucao pode ter terminado esta linha.
        atual = registro_da_linha(planilha.row_values(alvo.linha), colunas)
        if atual['status']:
            resultado['ignoradas'] += 1
            continue
        ler_atual(alvo, '')
        planilha.update_cell(alvo.linha, colunas['status'], 'PROCESSANDO')
        estado = {'envio': False}

        def antes_envio():
            ler_atual(alvo, 'PROCESSANDO')
            # Conservador: inclusive Confirmar item fica fora de qualquer retry.
            estado['envio'] = True

        try:
            ler_atual(alvo, 'PROCESSANDO')
            print(f'Linha {alvo.linha} | NF {alvo.nota_raw} | ICMS {brl(alvo.icms)} | FECP {brl(alvo.fecp)}')
            caminho = emitir(alvo, antes_envio)
            if not estado['envio']:
                raise RuntimeError('Retorno sem registro do envio ao portal')
            caminho, dados = validar_pdf(caminho, alvo, cnpj)
            file_id = subir_pdf(caminho)
            if not isinstance(file_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', file_id):
                raise RuntimeError('Drive nao confirmou o ID do PDF')
            ler_atual(alvo, 'PROCESSANDO')
            dados['link'] = f'https://drive.google.com/file/d/{file_id}/view'
            for campo, valor in dados.items():
                planilha.update_cell(alvo.linha, colunas[campo], valor)
            gravado = registro_da_linha(planilha.row_values(alvo.linha), colunas)
            if any(gravado[campo] != valor for campo, valor in dados.items()):
                raise RuntimeError('Nao foi possivel confirmar a gravacao dos resultados')
            if (gravado['status'] != 'PROCESSANDO' or any(
                gravado.get(campo, '') != alvo.origem.get(campo, '')
                for campo in ('data', 'nota', 'centro', 'icms', 'fecp', 'total')
            )):
                raise RuntimeError('Dados ou status mudaram antes da conclusao da linha')
            planilha.update_cell(alvo.linha, colunas['status'], 'X')
            resultado['X'] += 1
        except Exception as exc:
            status = 'REVISAR' if estado['envio'] else 'ERRO'
            try:
                planilha.update_cell(alvo.linha, colunas['status'], status)
            except Exception as erro_status:
                raise RuntimeError(f'Linha {alvo.linha}: falha e status nao confirmado; manter bloqueada') from erro_status
            raise RuntimeError(f'Linha {alvo.linha}: {status}; lote interrompido sem repetir a emissao: {exc}') from exc
        if intervalo and indice + 1 < len(pendentes):
            time.sleep(intervalo)
    return resultado
