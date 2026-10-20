function onOpen() {
  adicionarMenuDARJRJ();
}

function adicionarMenuDARJRJ() {
  SpreadsheetApp.getUi()
    .createMenu('🤖 Guias RJ')
    .addItem('▶️ Criar Guias DARJ', 'dispararRoboDARJRJ')
    .addToUi();
}

function dispararRoboDARJRJ() {
  var ui = SpreadsheetApp.getUi();
  var token = PropertiesService
    .getScriptProperties()
    .getProperty('GITHUB_TOKEN_RJ');

  if (!token) {
    ui.alert(
      'Cadastre GITHUB_TOKEN_RJ nas propriedades do script, ' +
      'com acesso ao repositorio rpa-sefaz-rj-darj.'
    );
    return;
  }

  var url =
    'https://api.github.com/repos/dauernetto-stack/' +
    'rpa-sefaz-rj-darj/actions/workflows/darj-rj.yml/dispatches';

  var resposta;

  try {
    resposta = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
      },
      payload: JSON.stringify({ ref: 'main' }),
      muteHttpExceptions: true
    });
  } catch (erro) {
    ui.alert(
      'Nao foi possivel confirmar o disparo. ' +
      'Confira o GitHub Actions antes de clicar novamente.\n' +
      erro.message
    );
    return;
  }

  var status = resposta.getResponseCode();

  if (status === 204 || status === 200) {
    ui.alert(
      'Lote solicitado. O robo processara as pendentes em sequencia ' +
      'e interrompera se houver falha. ' +
      'Acompanhe o resultado no GitHub Actions.'
    );
    return;
  }

  var motivo = {
    401: 'Token recusado pelo GitHub.',
    403: 'Confira a permissao de Actions: leitura e escrita do token para este repositorio.',
    404: 'Confira o repositorio, o acesso do token e o arquivo darj-rj.yml.',
    422: 'Confira a branch main e se o workflow esta publicado sem inputs obrigatorios.'
  }[status] ||
    'Confira a resposta e o GitHub Actions antes de tentar novamente.';

  ui.alert(
    'Falha no disparo: HTTP ' + status + '\n' +
    motivo + '\n' +
    resposta.getContentText().slice(0, 1000)
  );
}