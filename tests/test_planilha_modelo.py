"""Regressões da estrutura observada no XLSX fornecido, sem editar o arquivo."""
from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import controle_darj as controle

HEADERS = ['Data entrada','Nº Nota Fiscal','Valor NF','Vlr Produtos','IPI',
           'ICMS Normal','ALQ ICMS','BC da ST','ST','DARJ Normal','FECP',
           'TOTAL DA GUIA DE ICMS ST','VALOR Z3125','Diferença','PROC DARJ',
           'Nº DARJ','Vcto DARJ','Valor DARJ','Link DARJ']

class SemAcessoExterno:
    def __getattr__(self, nome):
        raise AssertionError('A pre-validacao nao pode chamar servicos: '+nome)

def modelo():
    return ['', '', '', '', '', '0', '0.04', '0', '0', '0', '0', '0', '', '0', '', '', '', '', '']

def validar(rows):
    return controle.executar_lote([['Pagamento Antecipado pela COBRA'], HEADERS] + rows,
        SemAcessoExterno(), None, None, date(2026,10,20), set(), '58248352001201',
        apenas_validar=True, intervalo=0)

class PlanilhaReal(unittest.TestCase):
    def test_linhas_de_modelo_com_aliquota_nao_sao_notas(self):
        try:
            resultado=validar([modelo(), modelo()])
        except ValueError as erro:
            self.fail('Linha de modelo foi tratada como nota: '+str(erro))
        self.assertEqual(resultado['validadas'],0)
        self.assertEqual(resultado['ignoradas'],2)

    def test_rodape_total_sem_data_nao_e_nota(self):
        rodape=['']*19
        rodape[1]='Total'; rodape[9]='50.00'; rodape[10]='5.00'
        try:
            resultado=validar([rodape])
        except ValueError as erro:
            self.fail('Rodape Total foi tratado como nota: '+str(erro))
        self.assertEqual(resultado['validadas'],0)

    def test_valor_positivo_sem_identificacao_nao_e_ignorado_como_modelo(self):
        linha=modelo(); linha[9]='10,00'
        with self.assertRaises(ValueError): validar([linha])

    def test_total_com_data_preenchida_e_registro_invalido(self):
        linha=modelo(); linha[0]='19.10.2026'; linha[1]='Total'
        with self.assertRaises(ValueError): validar([linha])

    def test_linha_modelo_com_numero_de_guia_permanece_bloqueada(self):
        linha=modelo(); linha[15]='01234567890123'
        with self.assertRaises(RuntimeError): validar([linha])

    def test_x_sem_dados_da_guia_e_sinalizado_sem_liberar(self):
        linha=modelo(); linha[0]='19.10.2026'; linha[1]='123456-0'
        linha[9]='100.00'; linha[10]='20.00'; linha[11]='120.00'; linha[14]='X'
        resultado=validar([linha])
        self.assertEqual(resultado['validadas'],0)
        self.assertEqual(resultado.get('x_incompletos'),1)
        self.assertEqual(linha[14],'X')

if __name__=='__main__': unittest.main(verbosity=2)
