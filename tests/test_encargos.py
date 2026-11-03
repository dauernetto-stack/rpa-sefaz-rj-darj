"""Encargos do portal RJ: somente calculos, DOM, planilha e PDFs locais simulados."""
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
