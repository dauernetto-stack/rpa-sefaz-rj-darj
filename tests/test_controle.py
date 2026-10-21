import importlib
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    controle = importlib.import_module('controle_darj')
except ModuleNotFoundError:
    controle = None

HEADERS = ['Data entrada', 'Nº Nota Fiscal', 'Centro', 'DARJ Normal', 'FECP',
           'TOTAL DA GUIA DE ICMS ST', 'PROC DARJ', 'Nº DARJ', 'Vcto DARJ',
           'Valor DARJ', 'Link DARJ']
CNPJ = '58248352001201'

def row(nota='345', status=''):
    return ['19.10.2026', nota, 'RJ01', '100,00', '20,00', '120,00', status, '', '', '', '']

class Sheet:
    def __init__(self, rows):
        self.rows = [list(r) for r in rows]
        self.writes = []
    def row_values(self, line):
        return list(self.rows[line - 1])
    def update_cell(self, line, column, value):
        target = self.rows[line - 1]
        target.extend([''] * max(0, column - len(target)))
        target[column - 1] = str(value)
        self.writes.append((line, column, str(value)))

def pdf_fixture(path, nota='345', total='120,00', cnpj='58.248.352/0012-01', numero='01234567890123'):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
    text = ['GOVERNO DO ESTADO DO RIO DE JANEIRO', 'DARJ - Documento de Arrecadacao',
            f'Numero do DARJ: {numero}', 'Data de Vencimento: 22/10/2026',
            f'Valor Total: R$ {total}', f'CNPJ: {cnpj}', f'Informacoes Complementares: NF {nota}']
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    stream.set_data(('BT /F1 10 Tf 30 760 Td ' + ' '.join(f'({line}) Tj 0 -16 Td' for line in text) + ' ET').encode('latin1'))
    page[NameObject('/Contents')] = stream
    writer.write(path)
    return path

class ControleDARJ(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(controle, 'O controle ainda precisa ser implementado')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def lote(self, rows, emitir=None, upload=None, validar=False):
        self.sheet = Sheet([['Titulo'], HEADERS] + rows)
        self.issued = []
        def normal(alvo, antes_envio):
            self.assertEqual(self.sheet.rows[alvo.linha - 1][6], 'PROCESSANDO')
            self.assertNotIn((alvo.linha, 7, 'X'), self.sheet.writes)
            antes_envio()
            self.issued.append(alvo.linha)
            return pdf_fixture(self.folder / f'{alvo.linha}.pdf', nota=alvo.nota_raw)
        return controle.executar_lote(self.sheet.rows, self.sheet, emitir or normal,
                                      upload or (lambda path: 'drive123'), date(2026,10,20),
                                      set(), CNPJ, apenas_validar=validar, intervalo=0)

    def test_moeda_brl_exata(self):
        self.assertEqual(controle.dinheiro('1.234,56'), Decimal('1234.56'))

    def test_texto_invalido_nao_vira_zero(self):
        with self.assertRaises(ValueError): controle.dinheiro('abc')

    def test_nan_infinito_negativo_bloqueados(self):
        for value in ['NaN', 'Infinity', '-10,00']:
            with self.subTest(value=value), self.assertRaises(ValueError): controle.dinheiro(value)

    def test_linha_vazia_nao_desloca_gravacao(self):
        self.lote([row('111', 'X'), [], row()])
        self.assertEqual(self.issued, [5])
        self.assertEqual(self.sheet.rows[4][6], 'X')
        self.assertEqual(self.sheet.rows[3], [])

    def test_todas_pendentes_em_ordem(self):
        result = self.lote([row('345'), row('346'), row('347')])
        self.assertEqual(self.issued, [3, 4, 5])
        self.assertEqual(result['X'], 3)
        self.assertEqual(self.sheet.rows[2][10], 'https://drive.google.com/file/d/drive123/view')

    def test_status_preenchido_nao_e_liberado(self):
        result = self.lote([row(str(i), value) for i,value in enumerate(['X','REVISAR','PROCESSANDO','ERRO'],100)])
        self.assertEqual(self.issued, [])
        self.assertEqual(self.sheet.writes, [])
        self.assertEqual(result['ignoradas'], 4)

    def test_numero_existente_bloqueia_status_vazio(self):
        r = row(); r[7] = '001234567890'
        with self.assertRaises(RuntimeError): self.lote([r])
        self.assertEqual(self.issued, [])

    def test_nota_repetida_nao_emite_duas_vezes(self):
        with self.assertRaises(RuntimeError): self.lote([row(), row()])
        self.assertEqual(self.issued, [])

    def test_falha_antes_envio_e_erro_sem_x(self):
        def failed(alvo, antes): raise ValueError('formulario recusado')
        with self.assertRaises(RuntimeError): self.lote([row(), row('346')], emitir=failed)
        self.assertEqual(self.sheet.rows[2][6], 'ERRO')
        self.assertEqual(self.sheet.rows[3][6], '')

    def test_falha_apos_envio_e_revisar_sem_repetir(self):
        calls=[]
        def failed(alvo, antes):
            antes(); calls.append(alvo.linha); raise TimeoutError('retorno desconhecido')
        with self.assertRaises(RuntimeError): self.lote([row(), row('346')], emitir=failed)
        self.assertEqual(calls, [3])
        self.assertEqual(self.sheet.rows[2][6], 'REVISAR')
        self.assertEqual(self.sheet.rows[3][6], '')

    def test_falha_drive_nao_marca_x(self):
        def failed(path): raise OSError('drive indisponivel')
        with self.assertRaises(RuntimeError): self.lote([row()], upload=failed)
        self.assertEqual(self.sheet.rows[2][6], 'REVISAR')
        self.assertFalse(any(v=='X' for _,_,v in self.sheet.writes))

    def test_pdf_de_outra_nota_bloqueia_conclusao(self):
        def wrong(alvo, antes):
            antes(); return pdf_fixture(self.folder/'errado.pdf', nota='999')
        with self.assertRaises(RuntimeError): self.lote([row()], emitir=wrong)
        self.assertEqual(self.sheet.rows[2][6], 'REVISAR')

    def test_pdf_com_valor_diferente_bloqueia_conclusao(self):
        def wrong(alvo, antes):
            antes(); return pdf_fixture(self.folder/'errado.pdf', total='120,01')
        with self.assertRaises(RuntimeError): self.lote([row()], emitir=wrong)
        self.assertEqual(self.sheet.rows[2][6], 'REVISAR')

    def test_alteracao_planilha_antes_envio_bloqueia(self):
        def changed(alvo, antes):
            self.sheet.rows[alvo.linha-1][3]='200,00'; antes()
            self.fail('nao pode enviar com dados alterados')
        with self.assertRaises(RuntimeError): self.lote([row()], emitir=changed)
        self.assertEqual(self.sheet.rows[2][6], 'ERRO')

    def test_validacao_nao_emite_nem_grava(self):
        result=self.lote([row(),row('346')],validar=True)
        self.assertEqual(self.sheet.writes, [])
        self.assertEqual(self.issued, [])
        self.assertEqual(result['validadas'], 2)

    def test_alteracao_durante_upload_nao_conclui_linha_modificada(self):
        def changed(path):
            self.sheet.rows[2][3] = '200,00'
            return 'drive123'
        with self.assertRaises(RuntimeError): self.lote([row()], upload=changed)
        self.assertEqual(self.sheet.rows[2][6], 'REVISAR')
        self.assertFalse(any(v=='X' for _,_,v in self.sheet.writes))

    def test_feriado_12_outubro_avanca_vencimento(self):
        self.assertEqual(controle.calcular_datas(date(2026,10,7),date(2026,10,8),{date(2026,10,12)}),
                         (date(2026,10,13),date(2026,10,13)))

    def test_virada_preserva_limite_do_mes_original(self):
        self.assertEqual(
            controle.calcular_datas(date(2026,10,28), date(2026,10,29), {date(2026,11,2)}),
            (date(2026,11,3), date(2026,10,30)))

    def test_mes_anterior_preserva_vencimento_hoje(self):
        self.assertEqual(
            controle.calcular_datas(date(2026,9,30), date(2026,10,20), set()),
            (date(2026,10,22), date(2026,10,20)))

    def test_sexta_conta_dois_dias_uteis_ate_terca(self):
        self.assertEqual(
            controle.calcular_datas(date(2026, 10, 23), date(2026, 10, 23), set()),
            (date(2026, 10, 27), date(2026, 10, 27)),
        )

    def test_feriado_no_primeiro_dia_util_nao_conta(self):
        self.assertEqual(
            controle.calcular_datas(
                date(2026, 10, 9), date(2026, 10, 9), {date(2026, 10, 12)}
            ),
            (date(2026, 10, 14), date(2026, 10, 14)),
        )

    def test_execucao_no_sabado_conta_segunda_e_terca(self):
        self.assertEqual(
            controle.calcular_datas(date(2026, 10, 17), date(2026, 10, 17), set()),
            (date(2026, 10, 20), date(2026, 10, 20)),
        )

    def test_mes_anterior_pode_ser_validado_sem_emissao(self):
        anterior = row('346')
        anterior[0] = '30.09.2026'
        resultado = self.lote([row('345'), anterior], validar=True)
        self.assertEqual(resultado['validadas'], 2)
        self.assertEqual(self.issued, [])
        self.assertEqual(self.sheet.writes, [])

    def test_pdf_cnpj_diferente_bloqueia(self):
        def wrong(alvo, antes):
            antes(); return pdf_fixture(self.folder/'errado.pdf', cnpj='12.345.678/0001-90')
        with self.assertRaises(RuntimeError): self.lote([row()], emitir=wrong)
        self.assertEqual(self.sheet.rows[2][6], 'REVISAR')

    def test_pdf_sem_numero_bloqueia(self):
        def wrong(alvo, antes):
            antes(); return pdf_fixture(self.folder/'errado.pdf', numero='')
        with self.assertRaises(RuntimeError): self.lote([row()], emitir=wrong)
        self.assertEqual(self.sheet.rows[2][6], 'REVISAR')

    def test_cabecalho_obrigatorio_duplicado_bloqueia(self):
        with self.assertRaises(ValueError): controle.resolver_colunas(HEADERS + ['PROC DARJ'])

    def test_fecp_zero_e_um_valor_valido(self):
        r = row(); r[4]='0,00'; r[5]='100,00'
        def normal(alvo, antes):
            antes(); return pdf_fixture(self.folder/'zero.pdf', total='100,00')
        resultado=self.lote([r], emitir=normal)
        self.assertEqual(resultado['X'],1)

if __name__ == '__main__': unittest.main(verbosity=2)
