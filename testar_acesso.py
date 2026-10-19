"""
Script simples de verificação de acesso - roda ANTES do bot.py.

Não abre navegador nem mexe em nada na SEFAZ. Só confirma que a service
account configurada em credenciais.json realmente consegue:
  1. Ler a planilha de controle no Google Sheets.
  2. Enxergar a pasta do Google Drive onde o PDF vai ser salvo.

Uso:
    python testar_acesso.py
"""

import sys
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from googleapiclient.discovery import build

ID_PLANILHA = "1U0HgRTfVIoGo3Jrr9-62ItBZumgJP77QH4SGa_lZ9jI"
ID_PASTA_DRIVE = "1UApSGUMncRgU15q7UH1MGT6EKrEskYim"

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

print("1. Carregando credenciais.json...")
try:
    creds = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", scope)
    print(f"   OK - service account: {creds.service_account_email}")
except FileNotFoundError:
    print("   ERRO: arquivo 'credenciais.json' não encontrado nesta pasta.")
    print("   Copie credenciais.example.json para credenciais.json e cole a chave real da service account.")
    sys.exit(1)
except Exception as e:
    print(f"   ERRO ao carregar credenciais.json: {e}")
    sys.exit(1)

print("\n2. Testando acesso à planilha de controle (Google Sheets)...")
try:
    client = gspread.authorize(creds)
    planilha = client.open_by_key(ID_PLANILHA).sheet1
    cabecalhos = planilha.row_values(1)
    print(f"   OK - planilha acessada! Cabeçalhos encontrados: {cabecalhos}")
except Exception as e:
    print(f"   ERRO: não consegui abrir a planilha. Verifique se ela foi compartilhada com "
          f"'{creds.service_account_email}' com permissão de Editor.")
    print(f"   Detalhe técnico: {e}")
    sys.exit(1)

print("\n3. Testando acesso à pasta do Google Drive...")
try:
    drive_service = build('drive', 'v3', credentials=creds)
    pasta = drive_service.files().get(
        fileId=ID_PASTA_DRIVE,
        fields='id, name',
        supportsAllDrives=True
    ).execute()
    print(f"   OK - pasta encontrada: '{pasta.get('name')}' (id: {pasta.get('id')})")
except Exception as e:
    print(f"   ERRO: não consegui acessar a pasta do Drive. Verifique se ela foi compartilhada com "
          f"'{creds.service_account_email}' com permissão de Editor.")
    print(f"   Detalhe técnico: {e}")
    sys.exit(1)

print("\n✅ Tudo certo! A service account tem acesso à planilha e à pasta do Drive. "
      "Pode rodar o bot.py normalmente.")
