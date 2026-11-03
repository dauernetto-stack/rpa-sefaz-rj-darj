"""Propagacao de total final e tentativa unica, sem navegador ou rede."""
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
