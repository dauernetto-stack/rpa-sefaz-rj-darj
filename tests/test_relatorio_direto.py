"""Entrada direta do relatorio, sem emissao real ou rede."""
import ast
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import types
import unittest
import controle_darj as c
from test_controle import Sheet,pdf_fixture,CNPJ

ORIGEM=['Doc MIRO','Tipo','N.Fiscal','Data Fatur','Data Lanc','Fornecedor','Nome','Região','Montante','Nº pedido','Centro','Texto','Usuário','Valor ST','Valor FCP','Doc Contab','Doc Materi','FUNEF']
SAIDA=['PROC DARJ','Nº DARJ','Vcto DARJ','Valor DARJ','Link DARJ']
HEAD=ORIGEM+SAIDA
EXEMPLO=['5105940205','compra','652063-7','28.10.2026','03.11.2026','200350','SCHAEFFLER BRASIL LTDA.','SP','485,06','4504257205','CE12','200350652063','CE12D','173,35','20,07','5002137868','5400284532','0']+['']*5
HOJE=date(2026,11,4)
def dados(rows=None,titulo=False):return ([['Titulo']] if titulo else [])+[HEAD.copy()]+deepcopy(rows if rows is not None else [EXEMPLO])
def planejar(rows=None,titulo=False):return c.planejar_lote(dados(rows,titulo),HOJE,set(),2)

class EntradaDireta(unittest.TestCase):
 def test_exemplo_real_principais_separados_e_total_sem_formula(self):
  cols,alvos,_=planejar();a=alvos[0]
  self.assertEqual((cols['data'],cols['icms'],cols['fecp']),(5,14,15))
  self.assertNotIn('total',cols)
  self.assertEqual((a.icms,a.fecp,a.total),(Decimal('173.35'),Decimal('20.07'),Decimal('193.42')))
 def test_tres_notas_dos_anexos_somam_principais(self):
  rows=[]
  for miro,nf,st,fcp in [('5105940205','652063-7','173,35','20,07'),('5105940214','397645-16','2.809,82','245,72'),('5105940256','354018-1','1.417,24','128,14')]:
   r=EXEMPLO.copy();r[0]=miro;r[2]=nf;r[13]=st;r[14]=fcp;rows.append(r)
  alvos=planejar(rows)[1]
  self.assertEqual([a.total for a in alvos],list(map(Decimal,['193.42','3055.54','1545.38'])))
  self.assertEqual(sum(a.total for a in alvos),Decimal('4794.34'))
 def test_data_lanc_determina_referencia_e_datas(self):
  a=planejar()[1][0]
  self.assertEqual(a.entrada,date(2026,11,3));self.assertEqual(a.periodo,'11/2026')
  self.assertEqual((a.pagamento,a.vencimento),(date(2026,11,6),)*2)
 def test_data_fatur_nao_altera_referencia(self):
  r=EXEMPLO.copy();r[3]='texto nao usado'
  self.assertEqual(planejar([r])[1][0].periodo,'11/2026')
 def test_header_na_linha1_ou2_preserva_numero_real(self):
  self.assertEqual(planejar()[1][0].linha,2)
  self.assertEqual(planejar(titulo=True)[1][0].linha,3)
 def test_colunas_reordenadas_funcionam(self):
  h=list(reversed(HEAD));r=list(reversed(EXEMPLO))
  cols,a,_=c.planejar_lote([h,r],HOJE,set(),2)
  self.assertEqual(a[0].total,Decimal('193.42'));self.assertEqual(cols['status'],5)
 def test_fcp_zero_permitido(self):
  r=EXEMPLO.copy();r[14]='0,00';self.assertEqual(planejar([r])[1][0].total,Decimal('173.35'))
 def test_fcp_vazio_invalido_nao_vira_zero(self):
  r=EXEMPLO.copy();r[14]=''
  with self.assertRaises(ValueError):planejar([r])
 def test_valores_invalidos_bloqueiam(self):
  for idx,v in ((13,'-1,00'),(14,'NaN'),(13,'173,351'),(14,'#VALUE!')):
   with self.subTest(idx=idx,v=v):
    r=EXEMPLO.copy();r[idx]=v
    with self.assertRaises(ValueError):planejar([r])
 def test_entrada_futura_bloqueia(self):
  r=EXEMPLO.copy();r[4]='05.11.2026'
  with self.assertRaisesRegex(ValueError,'futura'):planejar([r])
 def test_tipo_diferente_compra_bloqueia(self):
  r=EXEMPLO.copy();r[1]='estorno'
  with self.assertRaisesRegex(ValueError,'Tipo'):planejar([r])
 def test_miro_e_centro_obrigatorios(self):
  for idx in (0,10):
   r=EXEMPLO.copy();r[idx]=''
   with self.subTest(idx=idx),self.assertRaises(ValueError):planejar([r])
 def test_doc_miro_repetido_bloqueia_mesmo_com_nf_diferente(self):
  r=EXEMPLO.copy();r[2]='652064-7'
  with self.assertRaisesRegex(RuntimeError,'Doc MIRO repetido'):planejar([EXEMPLO,r])
 def test_doc_miro_normaliza_zeros_a_esquerda(self):
  r=EXEMPLO.copy();r[0]='0'+r[0];r[2]='652064-7'
  with self.assertRaisesRegex(RuntimeError,'Doc MIRO repetido'):planejar([EXEMPLO,r])
 def test_nf_repetida_nao_soma_relatorio_consolidado(self):
  r=EXEMPLO.copy();r[0]='5105940206'
  with self.assertRaisesRegex(RuntimeError,'NF repetida'):planejar([EXEMPLO,r])
 def test_miro_ja_processado_impede_nova_nf_com_mesmo_documento(self):
  anterior=EXEMPLO.copy();anterior[18]='X';r=EXEMPLO.copy();r[2]='652064-7'
  with self.assertRaisesRegex(RuntimeError,'Doc MIRO repetido'):planejar([anterior,r])
 def test_status_erro_ignorado_sem_liberar(self):
  r=EXEMPLO.copy();r[18]='ERRO';self.assertEqual(planejar([r])[2]['validadas'],0)
 def test_resultado_existente_sem_status_bloqueia(self):
  r=EXEMPLO.copy();r[19]='0123456789012345678901234'
  with self.assertRaisesRegex(RuntimeError,'dados de guia'):planejar([r])
 def test_layout_misto_bloqueia(self):
  with self.assertRaisesRegex(ValueError,'misturado'):c.resolver_colunas(HEAD+['DARJ Normal'])
 def test_saida_ausente_ou_duplicada_bloqueia(self):
  for h in (HEAD[:-1],HEAD+['PROC DARJ']):
   with self.assertRaises(ValueError):c.resolver_colunas(h)
 def test_documento_completo_sem_nf_nao_e_modelo(self):
  r=EXEMPLO.copy();r[2]='';r[13]='0,00';r[14]='0,00'
  with self.assertRaises(ValueError):planejar([r])
 def test_valida_sem_emitir_nem_escrever(self):
  sh=Sheet(dados());antes=deepcopy(sh.rows)
  def nao(*a):raise AssertionError('Nao pode emitir nem enviar')
  ret=c.executar_lote(sh.rows,sh,nao,nao,HOJE,set(),CNPJ,apenas_validar=True)
  self.assertEqual(ret['validadas'],1);self.assertEqual(sh.rows,antes);self.assertEqual(sh.writes,[])
 def test_cabecalho_duplo_bloqueia(self):
  with self.assertRaisesRegex(ValueError,'Mais de uma'):c.localizar_cabecalho([HEAD,HEAD])

class IntegracaoDireta(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.pasta=Path(self.tmp.name);self.sh=Sheet(dados());self.uploads=[];self.emissoes=[]
 def lote(self,emitir,upload=None):
  def subir(p):self.uploads.append(p);return 'drive123'
  return c.executar_lote(self.sh.rows,self.sh,emitir,upload or subir,HOJE,set(),CNPJ,intervalo=0)
 def emitir(self,a,antes):
  antes();self.emissoes.append(a)
  return pdf_fixture(self.pasta/'guia.pdf',nota=a.nota_raw,total=c.brl(a.total),vencimento=a.vencimento.strftime('%d/%m/%Y'))
 def test_grava_somente_colunas_saida_e_nome_sem_ce12_duplicado(self):
  orig=deepcopy(self.sh.rows[1][:18]);ret=self.lote(self.emitir)
  self.assertEqual(ret['X'],1);self.assertEqual(self.sh.rows[1][:18],orig)
  self.assertEqual(self.sh.rows[1][18],'X');self.assertEqual(self.sh.rows[1][21],'193,42')
  self.assertTrue(self.uploads[0].name.startswith('CE12_DARJ_NF_652063-7'))
  self.assertEqual({col for _,col,_ in self.sh.writes},{19,20,21,22,23})
  self.assertEqual(self.lote(self.emitir)['X'],0);self.assertEqual(len(self.emissoes),1)
 def test_pdf_total_errado_impede_upload(self):
  def errado(a,antes):
   antes();return pdf_fixture(self.pasta/'errada.pdf',nota=a.nota_raw,total='193,43',vencimento=a.vencimento.strftime('%d/%m/%Y'))
  with self.assertRaisesRegex(RuntimeError,'REVISAR'):self.lote(errado)
  self.assertEqual(self.uploads,[]);self.assertEqual(self.sh.rows[1][18],'REVISAR')
 def test_alteracao_miro_antes_confirmar_bloqueia(self):
  def alterado(a,antes):self.sh.rows[1][0]='5105940999';antes()
  with self.assertRaisesRegex(RuntimeError,'ERRO'):self.lote(alterado)
  self.assertEqual(self.uploads,[])
 def test_miro_duplicado_inserido_antes_confirmar_bloqueia(self):
  def alterado(a,antes):
   r=EXEMPLO.copy();r[2]='652064-7';self.sh.rows.append(r);antes()
  with self.assertRaisesRegex(RuntimeError,'ERRO'):self.lote(alterado)
 def test_mes_encerrado_com_encargos_registra_total_final(self):
  self.sh.rows[1][4]='30.10.2026'
  def emitir(a,antes):
   antes()
   self.assertEqual((a.pagamento,a.vencimento),(HOJE,date(2026,10,31)))
   calc=c.CalculoPortal(a.icms,a.fecp,Decimal('1.73'),Decimal('.57'),Decimal('.20'),Decimal('.07'),Decimal('175.65'),Decimal('20.34'))
   pdf=pdf_fixture(self.pasta/'comencargos.pdf',nota=a.nota_raw,total=c.brl(calc.total),vencimento='31/10/2026')
   return c.EmissaoPortal(pdf,calc)
  self.lote(emitir);self.assertEqual(self.sh.rows[1][21],'195,99');self.assertEqual(self.sh.rows[1][13:15],['173,35','20,07'])
 def test_falha_drive_preserva_revisar_sem_segunda_emissao(self):
  def falha(p):raise OSError('falha simulada')
  with self.assertRaisesRegex(RuntimeError,'REVISAR'):self.lote(self.emitir,falha)
  self.assertEqual(self.lote(self.emitir)['X'],0);self.assertEqual(len(self.emissoes),1)

class SelecaoAba(unittest.TestCase):
 def test_prefere_entrada_rj_sobre_modelo_antigo(self):
  import test_controle as t
  origem=Sheet([HEAD,EXEMPLO]);origem.title='Entrada RJ'
  antiga=Sheet([['Titulo'],t.HEADERS,t.row()]);antiga.title='Página1'
  p=Path(__file__).resolve().parents[1]/'bot.py';tree=ast.parse(p.read_text(encoding='utf-8-sig'))
  n=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='selecionar_aba')
  ns={'ABA_CONTROLE':'Entrada RJ','LINHA_CABECALHO':2};exec(compile(ast.Module(body=[n],type_ignores=[]),str(p),'exec'),ns)
  self.assertIs(ns['selecionar_aba'](types.SimpleNamespace(worksheets=lambda:[antiga,origem])),origem)

 def test_aba_nova_ausente_nao_cai_no_historico(self):
  import test_controle as t
  antiga=Sheet([['Titulo'],t.HEADERS,t.row()]);antiga.title='Página1'
  p=Path(__file__).resolve().parents[1]/'bot.py';n=next(n for n in ast.parse(p.read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name=='selecionar_aba')
  ns={'ABA_CONTROLE':'Entrada RJ','LINHA_CABECALHO':2};exec(compile(ast.Module(body=[n],type_ignores=[]),str(p),'exec'),ns)
  with self.assertRaisesRegex(RuntimeError,'nao encontrada'):ns['selecionar_aba'](types.SimpleNamespace(worksheets=lambda:[antiga]))
 def test_aba_configurada_invalida_nao_usa_outra_aba(self):
  invalida=Sheet([['sem cabecalho'],[]]);invalida.title='Entrada RJ'
  outra=Sheet([HEAD,EXEMPLO]);outra.title='Outra'
  p=Path(__file__).resolve().parents[1]/'bot.py';n=next(n for n in ast.parse(p.read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name=='selecionar_aba')
  ns={'ABA_CONTROLE':'Entrada RJ','LINHA_CABECALHO':2};exec(compile(ast.Module(body=[n],type_ignores=[]),str(p),'exec'),ns)
  with self.assertRaisesRegex(RuntimeError,'invalidos'):ns['selecionar_aba'](types.SimpleNamespace(worksheets=lambda:[invalida,outra]))
