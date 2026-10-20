"""Testa a sequência de confirmação observada no portal, sem usar a rede."""
import ast
from pathlib import Path
import types
import unittest
from datetime import date
from decimal import Decimal
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from controle_darj import dinheiro, brl

BOT = Path(__file__).resolve().parents[1] / 'bot.py'

class Campo:
    def __init__(self, value='', readonly=False):
        self.value, self.readonly = value, readonly
    def get_attribute(self, name):
        return self.value if name == 'value' else None
    def get_property(self, name):
        return self.readonly if name == 'readOnly' else None
    def clear(self): self.value=''
    def send_keys(self, value): self.value=value

class Driver:
    def __init__(self):
        self.campo = Campo('20/10/2026', True)
        self.botao = Campo('Alterar')
        self.clicks = 0
        self.botao.click = self.click
    def click(self):
        self.clicks += 1
        if self.botao.value == 'Alterar':
            self.campo.value = ''
            self.campo.readonly = False
            self.botao.value = 'Confirmar!'
        else:
            self.campo.readonly = True
            self.botao.value = 'Alterar'
    def find_element(self, by, selector):
        return self.campo if selector == 'txtDataPagamento' else self.botao

class DataPagamento(unittest.TestCase):
    def test_confirmacao_real_da_data_e_obrigatoria(self):
        ns={}
        if BOT.exists():
            tree=ast.parse(BOT.read_text(encoding='utf-8-sig'))
            defs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='confirmar_data_pagamento']
            exec(compile(ast.Module(body=defs,type_ignores=[]),str(BOT),'exec'),ns)
        self.assertIn('confirmar_data_pagamento',ns,'A data ainda nao possui confirmacao explicita')
        driver=Driver()
        def esperar(driver, wait, condicao):
            if not condicao(driver): raise TimeoutError('condicao nao satisfeita')
            return True
        def preencher(driver, wait, campo_id, texto):
            campo=driver.find_element('id',campo_id); campo.clear(); campo.send_keys(texto)
        ns.update(By=types.SimpleNamespace(ID='id'),esperar=esperar,preencher=preencher)
        ns['confirmar_data_pagamento'](driver,object(),'22/10/2026')
        self.assertEqual(driver.campo.value,'22/10/2026')
        self.assertTrue(driver.campo.readonly)
        self.assertEqual(driver.botao.value,'Alterar')
        self.assertEqual(driver.clicks,2)

    def test_total_de_itens_anteriores_nao_bloqueia_auditoria_do_item_atual(self):
        tree=ast.parse(BOT.read_text(encoding='utf-8-sig'))
        defs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='auditar_formulario']
        valores={
            'txtIcmsInformado':'100,00','txtFecpInformado':'20,00',
            'txtTotalIcms':'100,00','txtTotalFecp':'20,00','txtTotalDocs':'R$ 0,00',
            'btnAlterarDataPagamento':'Alterar','txtDataPagamento':'22/10/2026',
            'txtDataVencimento':'22/10/2026','txtPeriodo':'10/2026',
            'txtJustificativa':'NF 345','slcNaturezaLista':'4','slcListaProduto':'442',
        }
        driver=types.SimpleNamespace(find_element=lambda by,sel:Campo(valores[sel]))
        alvo=types.SimpleNamespace(icms=Decimal('100.00'),fecp=Decimal('20.00'),total=Decimal('120.00'),
                                   pagamento=date(2026,10,22),vencimento=date(2026,10,22),periodo='10/2026',nota_raw='345')
        def esperar(d,w,c):
            if not c(d): raise TimeoutError('A auditoria recusou o item valido')
        ns={'By':types.SimpleNamespace(ID='id'),'dinheiro':dinheiro,'brl':brl,
            'esperar':esperar,'aguardar_ajax':lambda *args:None}
        exec(compile(ast.Module(body=defs,type_ignores=[]),str(BOT),'exec'),ns)
        ns['auditar_formulario'](driver,object(),alvo)

if __name__=='__main__': unittest.main(verbosity=2)
