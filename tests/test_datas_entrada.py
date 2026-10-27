"""Impede que erros de ano na planilha cheguem ao portal. Sem chamadas externas."""
from datetime import date
import unittest
from unittest.mock import Mock

import controle_darj as c
from test_controle import Sheet, HEADERS, row, CNPJ


class DatasEntrada(unittest.TestCase):
    def registro(self, data):
        r = row('214509-1')
        r[0] = data
        return c.registro_da_linha(r, c.resolver_colunas(HEADERS))

    def test_ano_0206_identifica_linha_e_valor_incorreto(self):
        for data in ('26.10.0206', '26/10/0206', '0206-10-26'):
            with self.subTest(data=data), self.assertRaisesRegex(ValueError, 'Linha 12:.*0206'):
                c.preparar_alvo(12, self.registro(data), date(2026, 10, 27), set())

    def test_data_corrigida_gera_periodo_e_datas_originais(self):
        alvo = c.preparar_alvo(12, self.registro('26.10.2026'), date(2026, 10, 27), set())
        self.assertEqual(alvo.periodo, '10/2026')
        self.assertEqual((alvo.pagamento, alvo.vencimento), (date(2026, 10, 29), date(2026, 10, 29)))

    def test_data_antiga_invalida_bloqueia_lote_antes_de_escrever_ou_emitir(self):
        invalida = row('214509-1'); invalida[0] = '26.10.0206'
        sheet = Sheet([['Titulo'], HEADERS, row('1006163-5'), invalida])
        emitir, upload = Mock(), Mock()
        with self.assertRaisesRegex(ValueError, 'ano 0206'):
            c.executar_lote(sheet.rows, sheet, emitir, upload, date(2026, 10, 27), set(), CNPJ, intervalo=0)
        emitir.assert_not_called()
        upload.assert_not_called()
        self.assertEqual(sheet.writes, [])

    def test_validacao_tambem_rejeita_ano_incorreto(self):
        invalida = row(); invalida[0] = '26.10.0206'
        sheet = Sheet([['Titulo'], HEADERS, invalida])
        emitir, upload = Mock(), Mock()
        with self.assertRaisesRegex(ValueError, 'ano 0206'):
            c.executar_lote(sheet.rows, sheet, emitir, upload, date(2026, 10, 27), set(), CNPJ, apenas_validar=True)
        emitir.assert_not_called()
        self.assertEqual(sheet.writes, [])

    def test_nota_mes_anterior_mantem_regra_do_primeiro_zip(self):
        alvo = c.preparar_alvo(12, self.registro('30.09.2026'), date(2026, 10, 27), set())
        self.assertEqual(alvo.periodo, '09/2026')
        self.assertEqual(alvo.pagamento, date(2026, 10, 29))
        self.assertEqual(alvo.vencimento, date(2026, 10, 27))


if __name__ == '__main__':
    unittest.main(verbosity=2)
