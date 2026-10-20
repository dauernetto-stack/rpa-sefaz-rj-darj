// Executa o Apps Script num ambiente simulado, sem chamar o GitHub.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '..', 'AppsScript_RJ.gs'), 'utf8');
let count = 0;
function run(status = 204, networkError = false, token = 'token-de-teste') {
  const calls = [], alerts = [];
  const ui = {alert: text => alerts.push(text), createMenu: () => ({addItem(){return this;},addToUi(){}})};
  const ctx = {SpreadsheetApp:{getUi:()=>ui},
    PropertiesService:{getScriptProperties:()=>({getProperty:name=>name==='GITHUB_TOKEN_RJ'?token:null})},
    UrlFetchApp:{fetch:(url, options)=>{calls.push({url,options});if(networkError)throw new Error('rede indisponivel');return{getResponseCode:()=>status,getContentText:()=>'{"message":"erro de teste"}'};}}};
  vm.createContext(ctx);vm.runInContext(code,ctx);ctx.dispararRoboDARJRJ();
  return{calls,alerts};
}
for(const status of [200,204]) {
  const r=run(status);assert.equal(r.calls.length,1);
  assert.equal(r.calls[0].url,'https://api.github.com/repos/dauernetto-stack/rpa-sefaz-rj-darj/actions/workflows/darj-rj.yml/dispatches');
  assert.deepEqual(JSON.parse(r.calls[0].options.payload),{ref:'main'});
  assert.match(r.alerts[0],/Lote solicitado/);count++;
}
for(const status of [401,403,404,422,500]) {
  const r=run(status);assert.equal(r.calls.length,1);assert.match(r.alerts[0],new RegExp('HTTP '+status));count++;
}
const network=run(204,true);assert.equal(network.calls.length,1);assert.match(network.alerts[0],/antes de clicar novamente/);count++;
const missing=run(204,false,'');assert.equal(missing.calls.length,0);assert.match(missing.alerts[0],/GITHUB_TOKEN_RJ/);count++;
console.log(`${count} cenarios do Apps Script passaram, sem acesso a rede.`);
