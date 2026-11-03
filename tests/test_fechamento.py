"""Regra de fechamento autorizada: simulacoes locais, sem emissao."""
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
