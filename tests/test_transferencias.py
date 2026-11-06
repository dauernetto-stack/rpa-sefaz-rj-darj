"""Compras e transferencias: planilha, PDF e Drive simulados; sem emissao real."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
import controle_darj as c
from test_controle import Sheet,pdf_fixture,CNPJ
from test_relatorio_direto import HEAD,EXEMPLO

HOJE=date(2026,11,6)
def transferencia(nota='444462',st='3183,08',fcp='394,03'):
 r=EXEMPLO.copy();r[0]='';r[1]='transferencia';r[2]=nota;r[4]='05.11.2026';r[13]=st;r[14]=fcp
 return r

def planejar(rows):return c.planejar_lote([HEAD]+deepcopy(rows),HOJE,set(),2)

class Transferencias(unittest.TestCase):
 def test_transferencia_sem_miro_e_nf_sem_serie(self):
  a=planejar([transferencia()])[1][0]
  self.assertEqual((a.nota_raw,a.total,a.periodo),('444462',Decimal('3577.11'),'11/2026'))
  self.assertEqual((a.pagamento,a.vencimento),(date(2026,11,9),)*2)
 def test_tipo_com_acento_espacos_e_caixa(self):
  r=transferencia();r[1]=' Transferência '
  self.assertEqual(len(planejar([r])[1]),1)
 def test_compra_continua_exigindo_miro(self):
  r=EXEMPLO.copy();r[0]=''
  with self.assertRaisesRegex(ValueError,'Doc MIRO'):planejar([r])
 def test_miro_preenchido_na_transferencia_precisa_ser_valido(self):
  for valor in ('0','abc','510.1','1e8'):
   r=transferencia();r[0]=valor
   with self.subTest(valor=valor),self.assertRaisesRegex(ValueError,'Doc MIRO'):planejar([r])
 def test_transferencia_pode_ter_miro_valido(self):
  r=transferencia();r[0]='5105940999'
  self.assertEqual(len(planejar([r])[1]),1)
 def test_transferencia_com_miro_duplicado_bloqueia(self):
  r=transferencia();r[0]=EXEMPLO[0]
  with self.assertRaisesRegex(RuntimeError,'Doc MIRO repetido'):planejar([EXEMPLO,r])
 def test_nf_transferencia_repetida_sem_miro_bloqueia(self):
  with self.assertRaisesRegex(RuntimeError,'NF repetida'):planejar([transferencia(),transferencia()])
 def test_tipos_nao_autorizados_continuam_bloqueados(self):
  for tipo in ('estorno','devolucao',''):
   r=transferencia();r[1]=tipo
   with self.subTest(tipo=tipo),self.assertRaisesRegex(ValueError,'Tipo'):planejar([r])
 def test_tres_transferencias_da_planilha_e_compra(self):
  rows=[EXEMPLO,transferencia(),transferencia('444464','140,13','15,75'),transferencia('444622','1611,33','203,30')]
  alvos=planejar(rows)[1]
  self.assertEqual(len(alvos),4)
  self.assertEqual([a.total for a in alvos[1:]],list(map(Decimal,['3577.11','155.88','1814.63'])))
 def test_transferencia_sem_nf_ou_centro_e_invalida(self):
  for idx in (2,10):
   r=transferencia();r[idx]=''
   with self.subTest(idx=idx),self.assertRaises(ValueError):planejar([r])
 def test_valores_e_data_continuam_obrigatorios(self):
  for idx,valor in ((13,'-1,00'),(14,''),(4,''),(4,'07.11.2026')):
   r=transferencia();r[idx]=valor
   with self.subTest(idx=idx,valor=valor),self.assertRaises(ValueError):planejar([r])
 def test_validacao_nao_emite_nem_escreve(self):
  sh=Sheet([HEAD,transferencia()]);orig=deepcopy(sh.rows)
  def proibido(*a):raise AssertionError('Emissao proibida no validar')
  ret=c.executar_lote(sh.rows,sh,proibido,proibido,HOJE,set(),CNPJ,apenas_validar=True)
  self.assertEqual(ret['validadas'],1);self.assertEqual(sh.rows,orig);self.assertEqual(sh.writes,[])
 def test_fluxo_pdf_upload_x_e_sem_segunda_emissao(self):
  with tempfile.TemporaryDirectory() as tmp:
   sh=Sheet([HEAD,transferencia()]);orig=sh.rows[1][:18].copy();emissoes=[];uploads=[]
   def emitir(a,antes):
    antes();emissoes.append(a)
    return pdf_fixture(Path(tmp)/'transferencia.pdf',nota=a.nota_raw,total=c.brl(a.total),vencimento=a.vencimento.strftime('%d/%m/%Y'))
   def upload(p):uploads.append(p);return 'drive123'
   ret=c.executar_lote(sh.rows,sh,emitir,upload,HOJE,set(),CNPJ,intervalo=0)
   self.assertEqual(ret['X'],1);self.assertEqual(sh.rows[1][18],'X');self.assertEqual(sh.rows[1][21],'3577,11')
   self.assertEqual(sh.rows[1][:18],orig);self.assertEqual(uploads[0].name,'CE12_DARJ_NF_444462.pdf')
   self.assertEqual(c.executar_lote(sh.rows,sh,emitir,upload,HOJE,set(),CNPJ,intervalo=0)['X'],0)
   self.assertEqual((len(emissoes),len(uploads)),(1,1))
