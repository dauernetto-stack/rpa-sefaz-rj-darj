"""Testa a barreira antes da emissao. Sem navegador, credenciais ou rede."""
import ast
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class PeriodoRJ(unittest.TestCase):
    def setUp(self):
        bot = Path(__file__).resolve().parents[1] / 'bot.py'
        tree = ast.parse(bot.read_text(encoding='utf-8-sig'))
        defs = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == 'preencher_periodo']
        self.assertEqual(len(defs), 1, 'Adicionar preencher_periodo ao bot.py')
        self.valor = '10/2026'
        self.campo = Mock()
        self.campo.get_property.side_effect = lambda nome: (
            False if nome == 'readOnly' else self.valor)
        tipo = Mock()
        tipo.get_attribute.return_value = 'M'
        self.driver = Mock()
        self.driver.find_element.side_effect = lambda by, nome: (
            self.campo if nome == 'txtPeriodo' else tipo)
        self.ajax = Mock()
        self.ns = {'re':re, 'By':SimpleNamespace(ID='id'),
                   'aguardar_ajax':self.ajax,
                   'esperar_elemento':Mock(return_value=self.campo)}
        exec(compile(ast.Module(body=defs, type_ignores=[]), str(bot), 'exec'), self.ns)

    def executar(self, periodo='10/2026'):
        return self.ns['preencher_periodo'](self.driver, object(), periodo)

    def test_valor_preenchido_nao_e_limpo_antes_da_validacao(self):
        self.executar()
        self.campo.clear.assert_not_called()
        self.campo.send_keys.assert_not_called()
        self.driver.execute_script.assert_called_once()
        self.assertEqual(self.driver.execute_script.call_args.args[2], '10/2026')
        self.assertEqual(self.ajax.call_count, 2)

    def test_formato_invalido_bloqueia_antes_de_tocar_no_portal(self):
        for valor in ('13/2026', '1/2026', '', '10/202', '10/20266'):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                self.executar(valor)
        self.driver.execute_script.assert_not_called()

    def test_rejeicao_do_servidor_continua_fatal_sem_retry(self):
        self.ajax.side_effect = [None, RuntimeError('Periodo de Referencia invalido')]
        with self.assertRaisesRegex(RuntimeError, 'invalido'):
            self.executar()
        self.driver.execute_script.assert_called_once()

    def test_campo_apagado_pelo_portal_nao_e_aprovado(self):
        self.driver.execute_script.side_effect = lambda *args: setattr(self, 'valor', '')
        with self.assertRaisesRegex(RuntimeError, 'Periodo nao confirmado'):
            self.executar()
        self.driver.execute_script.assert_called_once()

    def test_mensagem_preexistente_nao_e_ignorada(self):
        self.ajax.side_effect = RuntimeError('Mensagem pendente do portal')
        with self.assertRaisesRegex(RuntimeError, 'Mensagem pendente'):
            self.executar()
        self.driver.execute_script.assert_not_called()

    def test_campo_readonly_nao_e_forcado(self):
        self.campo.get_property.side_effect = lambda nome: True if nome == 'readOnly' else self.valor
        with self.assertRaisesRegex(RuntimeError, 'somente leitura'):
            self.executar()
        self.driver.execute_script.assert_not_called()

    def test_tipo_de_periodo_incorreto_bloqueia(self):
        self.driver.find_element('id', 'slcTipoPeriodo').get_attribute.return_value = 'D'
        with self.assertRaisesRegex(RuntimeError, 'mensal'):
            self.executar()
        self.driver.execute_script.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
