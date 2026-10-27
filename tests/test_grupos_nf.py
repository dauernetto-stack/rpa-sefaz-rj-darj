"""Agrupamento por NF com planilha e portal simulados; nao emite guias reais."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

import controle_darj as c
from test_controle import Sheet, pdf_fixture, CNPJ


HEADERS = ['Data entrada', 'Nº Nota Fiscal', 'Centro', 'DARJ Normal', 'FECP',
           'TOTAL DA GUIA DE ICMS ST', 'PROC DARJ', 'Nº DARJ', 'Vcto DARJ',
           'Valor DARJ', 'Link DARJ', 'ALQ ICMS']
NUMERO = '0123456789012345678901234'


def parcela(nota='650874-7', data='26.10.2026', aliquota='4%',
            icms='338,81', fecp='37,14', total='375,95', status='', centro='RJ01'):
    return [data, nota, centro, icms, fecp, total, status, '', '', '', '', aliquota]


def exemplo():
    return [parcela(),
            parcela(data='', aliquota='12%', icms='1508,68', fecp='215,19', total='1723,87'),
            parcela(nota='SOMA VALORES', data='', aliquota='', centro='',
                    icms='1847,49', fecp='252,33', total='2099,82')]


class GruposNF(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)
        self.emissoes, self.uploads = [], []

    def preparar(self, rows=None, classe=Sheet):
        self.sheet = classe([['Titulo'], HEADERS] + (exemplo() if rows is None else rows))

    def emitir(self, alvo, antes):
        antes()
        self.emissoes.append(alvo)
        return pdf_fixture(self.pasta / f'{alvo.linha}.pdf', nota=alvo.nota_raw,
                           total=c.brl(alvo.total), numero=str(int(NUMERO) + len(self.emissoes) - 1).zfill(25),
                           vencimento=alvo.vencimento.strftime('%d/%m/%Y'))

    def upload(self, caminho):
        self.uploads.append(caminho)
        return 'drive123'

    def executar(self, validar=False, emitir=None, upload=None):
        return c.executar_lote(self.sheet.get_all_values(), self.sheet,
                              emitir or self.emitir, upload or self.upload,
                              date(2026, 10, 27), set(), CNPJ,
                              apenas_validar=validar, intervalo=0)

    def bloqueado(self, rows, mensagem=None):
        self.preparar(rows)
        with self.assertRaises((ValueError, RuntimeError)) as erro:
            self.executar()
        if mensagem:
            self.assertIn(mensagem, str(erro.exception))
        self.assertEqual(self.emissoes, [])
        self.assertEqual(self.uploads, [])
        self.assertEqual(self.sheet.writes, [])

    def test_uma_guia_soma_parcelas_sem_somar_subtotal_novamente(self):
        self.preparar()
        subtotal = self.sheet.rows[4].copy()
        resultado = self.executar()
        self.assertEqual(len(self.emissoes), 1)
        self.assertEqual(len(self.uploads), 1)
        alvo = self.emissoes[0]
        self.assertEqual((alvo.icms, alvo.fecp, alvo.total),
                         (Decimal('1847.49'), Decimal('252.33'), Decimal('2099.82')))
        self.assertEqual(alvo.entrada, date(2026, 10, 26))
        self.assertEqual(alvo.vencimento, date(2026, 10, 29))
        self.assertEqual(resultado['X'], 1)
        self.assertEqual(resultado['linhas_concluidas'], 2)
        self.assertEqual(self.sheet.rows[2][6:11], self.sheet.rows[3][6:11])
        self.assertEqual(self.sheet.rows[2][6:10], ['X', NUMERO, '29/10/2026', '2099,82'])
        self.assertIn('"Link PDF"', self.sheet.rows[2][10])
        self.assertEqual(self.sheet.rows[4], subtotal)
        self.assertEqual(self.sheet.rows[3][0], '')

    def test_validar_mostra_uma_guia_duas_linhas_sem_escrever_ou_emitir(self):
        self.preparar()
        resultado = self.executar(validar=True)
        self.assertEqual((resultado['validadas'], resultado['linhas_validadas'],
                          resultado['subtotais_conferidos']), (1, 2, 1))
        self.assertEqual(self.sheet.writes, [])
        self.assertEqual(self.emissoes, [])

    def test_grupo_sem_subtotal_tambem_e_valido(self):
        self.preparar(exemplo()[:2])
        self.assertEqual(self.executar()['X'], 1)

    def test_segunda_execucao_ignora_grupo_ja_concluido(self):
        self.preparar()
        self.executar()
        self.assertEqual(self.executar()['X'], 0)
        self.assertEqual(len(self.emissoes), 1)

    def test_nf_seguinte_processada_uma_vez_em_ordem(self):
        self.preparar(exemplo() + [parcela(nota='255506-8')])
        resultado = self.executar()
        self.assertEqual([a.nota_raw for a in self.emissoes], ['650874-7', '255506-8'])
        self.assertEqual(resultado['X'], 2)
        self.assertEqual(resultado['linhas_concluidas'], 3)

    def test_nota_invalida_posterior_impede_todo_lote_antes_emissao(self):
        self.bloqueado(exemplo() + [parcela(nota='invalida')])

    def test_mesmo_numero_com_serie_diferente_nao_se_agrupa(self):
        self.preparar([parcela(), parcela(nota='650874-8')])
        self.assertEqual(self.executar()['X'], 2)

    def test_mesmo_numero_centro_diferente_nao_se_agrupa(self):
        self.preparar([parcela(), parcela(centro='RJ02')])
        self.assertEqual(self.executar(validar=True)['validadas'], 2)

    def test_nota_sem_cabecalho_centro_funciona(self):
        self.preparar()
        for row in self.sheet.rows[1:]:
            del row[2]
        self.assertEqual(self.executar()['X'], 1)

    def test_subtotal_com_um_centavo_divergente_bloqueia(self):
        for coluna in (3, 4, 5):
            with self.subTest(coluna=coluna):
                rows = exemplo()
                rows[2][coluna] = c.brl(c.dinheiro(rows[2][coluna]) + Decimal('0.01'))
                self.bloqueado(rows, 'subtotal')

    def test_parcela_divergente_bloqueia_mesmo_com_subtotal_correto(self):
        rows = exemplo(); rows[1][5] = '1723,86'
        self.bloqueado(rows, 'centavos')

    def test_sem_aliquota_na_nf_repetida_bloqueia(self):
        rows = exemplo(); rows[1][11] = ''
        self.bloqueado(rows, 'ALQ ICMS')

    def test_mesma_aliquota_em_formatos_diferentes_bloqueia(self):
        for valor in ('4%', '4', '0,04', '0.04'):
            with self.subTest(valor=valor):
                rows = exemplo(); rows[1][11] = valor
                self.bloqueado(rows, 'aliquota repetidas')

    def test_aliquota_12_em_formatos_diferentes_aceita(self):
        for valor in ('12%', '12', '0,12', '0.12'):
            with self.subTest(valor=valor):
                rows = exemplo(); rows[1][11] = valor
                self.preparar(rows)
                self.assertEqual(self.executar(validar=True)['validadas'], 1)

    def test_datas_distintas_dentro_da_nf_bloqueiam(self):
        rows = exemplo(); rows[1][0] = '25.10.2026'
        self.bloqueado(rows, 'datas de entrada diferentes')

    def test_data_vazia_na_primeira_parcela_bloqueia(self):
        rows = exemplo(); rows[0][0] = ''
        self.bloqueado(rows, 'Data invalida')

    def test_nao_herda_data_de_outra_nf(self):
        rows = exemplo()[:2]; rows[1][1] = '999-1'
        self.bloqueado(rows, 'Data invalida')

    def test_nf_em_blocos_separados_bloqueia(self):
        self.bloqueado([parcela(), parcela(nota='999-1'), parcela()], 'blocos separados')

    def test_linha_vazia_separa_blocos(self):
        self.bloqueado([parcela(), [], parcela()], 'blocos separados')

    def test_subtotal_sem_grupo_anterior_bloqueia(self):
        self.bloqueado([exemplo()[2]], 'sem grupo')

    def test_subtotal_com_dados_de_guia_bloqueia(self):
        rows = exemplo(); rows[2][7] = NUMERO
        self.bloqueado(rows, 'apenas subtotal')

    def test_parcela_processada_e_parcela_nova_bloqueiam_grupo(self):
        for status in ('X', 'REVISAR', 'PROCESSANDO', 'ERRO'):
            with self.subTest(status=status):
                rows = exemplo(); rows[0][6] = status
                self.bloqueado(rows, 'parcialmente processado')

    def test_numero_existente_em_qualquer_parcela_bloqueia(self):
        rows = exemplo(); rows[1][7] = NUMERO
        self.bloqueado(rows, 'ja possui dados de guia')

    def test_qualquer_resultado_existente_bloqueia_mesmo_sem_numero(self):
        for coluna, valor in ((8, '29/10/2026'), (9, '2099,82'), (10, 'Link PDF')):
            with self.subTest(coluna=coluna):
                rows = exemplo(); rows[1][coluna] = valor
                self.bloqueado(rows, 'ja possui dados de guia')

    def test_parcela_nova_apos_grupo_ja_emitido_bloqueia(self):
        rows = exemplo()
        rows[0][6] = rows[1][6] = 'X'
        self.bloqueado(rows + [parcela()], 'blocos separados')

    def test_todo_grupo_revisar_e_preservado_sem_reemissao(self):
        rows = exemplo(); rows[0][6] = rows[1][6] = 'REVISAR'
        self.preparar(rows)
        self.assertEqual(self.executar()['X'], 0)
        self.assertEqual(self.emissoes, [])
        self.assertEqual(self.sheet.writes, [])

    def test_alteracao_da_segunda_parcela_antes_envio_bloqueia(self):
        self.preparar()
        def emitir(alvo, antes):
            self.sheet.rows[3][3] = '1509,68'
            antes()
            self.fail('nao pode emitir')
        with self.assertRaisesRegex(RuntimeError, 'ERRO'):
            self.executar(emitir=emitir)
        self.assertEqual([r[6] for r in self.sheet.rows[2:4]], ['ERRO', 'ERRO'])

    def test_parcela_adicionada_antes_envio_bloqueia(self):
        self.preparar()
        def emitir(alvo, antes):
            self.sheet.rows.insert(4, parcela(data='', aliquota='7%'))
            antes()
            self.fail('nao pode emitir')
        with self.assertRaisesRegex(RuntimeError, 'Parcelas'):
            self.executar(emitir=emitir)
        with self.assertRaisesRegex(RuntimeError, 'parcialmente processado'):
            self.executar()
        self.assertEqual(self.emissoes, [])

    def test_subtotal_alterado_apos_envio_mantem_revisar(self):
        self.preparar()
        def upload(caminho):
            self.sheet.rows[4][5] = '2099,83'
            return 'drive123'
        with self.assertRaisesRegex(RuntimeError, 'REVISAR'):
            self.executar(upload=upload)
        self.assertEqual([r[6] for r in self.sheet.rows[2:4]], ['REVISAR', 'REVISAR'])

    def test_pdf_valor_apenas_da_primeira_parcela_nao_conclui_grupo(self):
        self.preparar()
        def emitir(alvo, antes):
            antes()
            return pdf_fixture(self.pasta/'errado.pdf', nota=alvo.nota_raw,
                               total='375,95', vencimento='29/10/2026')
        with self.assertRaisesRegex(RuntimeError, 'REVISAR'):
            self.executar(emitir=emitir)
        self.assertEqual(self.uploads, [])
        self.assertEqual([r[6] for r in self.sheet.rows[2:4]], ['REVISAR', 'REVISAR'])

    def test_falha_apos_envio_nao_processa_nf_seguinte(self):
        self.preparar(exemplo() + [parcela(nota='999-1')])
        def emitir(alvo, antes):
            antes(); self.emissoes.append(alvo)
            raise TimeoutError('retorno desconhecido')
        with self.assertRaisesRegex(RuntimeError, 'REVISAR'):
            self.executar(emitir=emitir)
        self.assertEqual(len(self.emissoes), 1)
        self.assertEqual([r[6] for r in self.sheet.rows[2:4]], ['REVISAR', 'REVISAR'])
        self.assertEqual(self.sheet.rows[5][6], '')

    def test_falha_drive_preserva_grupo_sem_x(self):
        self.preparar()
        def upload(caminho):
            raise OSError('Drive indisponivel')
        with self.assertRaisesRegex(RuntimeError, 'REVISAR'):
            self.executar(upload=upload)
        self.assertEqual([r[6] for r in self.sheet.rows[2:4]], ['REVISAR', 'REVISAR'])

    def test_falha_reserva_nao_emite(self):
        class Falha(Sheet):
            def update_cell(self, line, column, value):
                if line == 4 and value == 'PROCESSANDO':
                    raise OSError('falha de reserva')
                super().update_cell(line, column, value)
        self.preparar(classe=Falha)
        with self.assertRaisesRegex(RuntimeError, 'ERRO'):
            self.executar()
        self.assertEqual(self.emissoes, [])
        self.assertEqual(self.executar()['X'], 0)

    def test_falha_gravacao_segunda_parcela_preserva_numero_e_bloqueia_retry(self):
        class Falha(Sheet):
            def update_cell(self, line, column, value):
                if line == 4 and column == 8:
                    raise OSError('falha gravacao segunda parcela')
                super().update_cell(line, column, value)
        self.preparar(classe=Falha)
        with self.assertRaisesRegex(RuntimeError, 'REVISAR'):
            self.executar()
        self.assertEqual(self.sheet.rows[2][7], NUMERO)
        self.assertEqual([r[6] for r in self.sheet.rows[2:4]], ['REVISAR', 'REVISAR'])
        self.assertEqual(self.executar()['X'], 0)
        self.assertEqual(len(self.emissoes), 1)

    def test_falha_ao_marcar_x_recoloca_grupo_em_revisar(self):
        class Falha(Sheet):
            def update_cell(self, line, column, value):
                if line == 4 and value == 'X':
                    raise OSError('falha conclusao')
                super().update_cell(line, column, value)
        self.preparar(classe=Falha)
        with self.assertRaisesRegex(RuntimeError, 'REVISAR'):
            self.executar()
        self.assertEqual([r[6] for r in self.sheet.rows[2:4]], ['REVISAR', 'REVISAR'])
        self.assertEqual(self.executar()['X'], 0)
        self.assertEqual(len(self.emissoes), 1)

    def test_link_com_rotulo_correto_destino_errado_nao_conclui(self):
        class Falha(Sheet):
            def update_cell(self, line, column, value):
                if str(value).startswith('=HYPERLINK('):
                    value = value.replace('drive123', 'outroArquivo')
                super().update_cell(line, column, value)
        self.preparar(classe=Falha)
        with self.assertRaisesRegex(RuntimeError, 'destino do Link PDF'):
            self.executar()
        self.assertEqual([r[6] for r in self.sheet.rows[2:4]], ['REVISAR', 'REVISAR'])

    def test_resultados_usam_raw_para_preservar_25_digitos(self):
        class Rastreador(Sheet):
            def __init__(self, rows):
                super().__init__(rows)
                self.lotes = []
            def batch_update(self, data, value_input_option='RAW'):
                self.lotes.append((data, value_input_option))
                super().batch_update(data, value_input_option)
        self.preparar(classe=Rastreador)
        self.executar()
        self.assertEqual(len(self.sheet.lotes), 4)
        for dados, modo in self.sheet.lotes:
            for item in dados:
                value = item['values'][0][0]
                if value == NUMERO:
                    self.assertEqual(modo, 'RAW')
                if value.startswith('=HYPERLINK('):
                    self.assertEqual(modo, 'USER_ENTERED')

    def test_nf_movida_nao_sobrescreve_status_de_outra_nota(self):
        self.preparar()
        def emitir(alvo, antes):
            self.sheet.rows.insert(2, parcela(nota='999-1', status='X'))
            antes()
            self.fail('nao pode emitir')
        with self.assertRaisesRegex(RuntimeError, 'status nao confirmado'):
            self.executar(emitir=emitir)
        self.assertEqual(self.sheet.rows[2][6], 'X')
        self.assertEqual(self.emissoes, [])
        self.assertTrue(all(r[6] in ('ERRO', 'PROCESSANDO') for r in self.sheet.rows[3:5]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
