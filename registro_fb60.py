"""Monta e publica um registro por guia confirmada."""

from datetime import datetime
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo


def data_emissao_local():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).date()



def datas_planilha(dados):
    def converter(campo):
        texto = str(dados.get(campo) or '').strip()
        for formato in ('%d/%m/%Y', '%d.%m.%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(texto, formato).date().isoformat()
            except ValueError:
                continue
        raise ValueError(f'{campo} ausente ou invalida na planilha')
    return {
        'data_fatura': converter('Data Fatura'),
        'data_lancamento': converter('Data Lanc'),
        'origem_datas_fb60': 'planilha',
    }


def registro_mg(guia, calculo, centro, nf, competencia, emissao, vencimento, pagamento, id_pdf, *, dados_planilha=None):
    mes, ano = competencia.split('/')
    return {
        **(datas_planilha(dados_planilha) if dados_planilha is not None else {}),
        'versao': 1, 'uf': 'MG', 'tipo_guia': 'DAE', 'numero_guia': str(guia['numDoc']).strip(),
        'nota_fiscal': nf.strip(), 'centro': centro, 'competencia': f'{ano}-{mes}',
        'data_emissao': emissao.isoformat(),
        'data_pagamento': datetime.strptime(pagamento, '%d/%m/%Y').date().isoformat(),
        'vencimento_fiscal': datetime.strptime(vencimento, '%d/%m/%Y').date().isoformat(),
        'validade_guia': datetime.strptime(guia['validade'], '%d/%m/%Y').date().isoformat(),
        'pdf_drive_id': id_pdf, 'total': f"{calculo['total']:.2f}",
        'itens': {'icms_st': f"{calculo['principal']:.2f}", 'juros_st': f"{calculo['juros']:.2f}",
                  'multa_st': f"{calculo['multa']:.2f}"},
    }


def registro_rj(alvo, retorno, guia, id_pdf):
    calculo = retorno.calculo
    mes, ano = alvo.periodo.split('/')
    validade = guia.get('validade')
    origem = getattr(alvo, 'origem', None)
    datas = datas_planilha({'Data Fatura': origem.get('data_fatura'),
                            'Data Lanc': origem.get('data')}) if origem is not None else {}
    return {
        **datas,
        'versao': 1, 'uf': 'RJ', 'tipo_guia': 'DARJ', 'numero_guia': guia['numero'],
        'nota_fiscal': alvo.nota_raw, 'centro': alvo.centro, 'competencia': f'{ano}-{mes}',
        'data_emissao': retorno.data_emissao.isoformat(),
        'data_pagamento': alvo.pagamento.isoformat(),
        'vencimento_fiscal': alvo.vencimento.isoformat(),
        'validade_guia': validade,
        'pdf_drive_id': id_pdf, 'total': f'{calculo.total:.2f}',
        'itens': {
            'icms_st': f'{calculo.icms:.2f}', 'fecp': f'{calculo.fecp:.2f}',
            'mora_st': f'{calculo.mora_icms:.2f}', 'multa_st': f'{calculo.multa_icms:.2f}',
            'mora_fecp': f'{calculo.mora_fecp:.2f}', 'multa_fecp': f'{calculo.multa_fecp:.2f}',
        },
    }


def gravar_registro(pasta, registro):
    uf, tipo = registro['uf'], registro['tipo_guia']
    numero = registro['numero_guia']
    if (uf, tipo) not in (('MG', 'DAE'), ('RJ', 'DARJ')) or not re.fullmatch(r'[0-9]+(?:[.-][0-9]+)*', numero):
        raise ValueError('Identificação da guia inválida para gravação do registro FB60')
    digitos = re.sub(r'[.-]', '', numero)
    caminho = Path(pasta) / f'fb60_{uf}_{tipo}_{digitos}.json'
    temporario = caminho.with_suffix('.part')
    temporario.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporario.replace(caminho)
    return caminho


def conferir_pasta(drive, pasta):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', pasta):
        raise ValueError('FB60_DRIVE_FOLDER_ID contém um ID inválido')
    dados = drive.files().get(
        fileId=pasta, fields='mimeType,capabilities(canAddChildren),trashed',
        supportsAllDrives=True,
    ).execute()
    if (dados.get('trashed') or dados.get('mimeType') != 'application/vnd.google-apps.folder'
            or not dados.get('capabilities', {}).get('canAddChildren')):
        raise ValueError('A conta do robô não pode gravar na pasta de exportação FB60')


def enviar_registro(drive, pasta, caminho):
    from googleapiclient.http import MediaFileUpload

    arquivo = drive.files().create(
        body={'name': caminho.name, 'parents': [pasta]},
        media_body=MediaFileUpload(str(caminho), mimetype='application/json'),
        fields='id', supportsAllDrives=True,
    ).execute()
    if not arquivo.get('id'):
        raise RuntimeError(f'Drive não confirmou o registro FB60 {caminho.name}')
    return arquivo['id']
