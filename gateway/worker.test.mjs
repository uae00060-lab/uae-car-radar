import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pbkdf2Sync} from 'node:crypto';
import worker,{seal,open,verify} from './worker.mjs';
test('encrypted files retain Python-compatible envelope and never accept the wrong key',async()=>{
 const text=await seal('{"requests":[]}', 'test-key');
 assert.equal(JSON.parse(text).iter,250000);
 assert.equal(new TextDecoder().decode(await open(text,'test-key')),'{"requests":[]}');
 await assert.rejects(open(text,'wrong-key'));
});
test('password verifier matches a local generated hash',async()=>{
 const salt=Buffer.from('0123456789abcdef');
 const record='600000:'+salt.toString('base64')+':'+pbkdf2Sync('owner-password',salt,600000,32,'sha256').toString('base64');
 assert.equal(await verify('owner-password',record),true);
 assert.equal(await verify('wrong',record),false);
});
test('unconfigured server fails closed',async()=>{
 assert.equal((await worker.fetch(new Request('https://radar.test/api/session'),{})).status,503);
});
test('unauthenticated users cannot read data or dispatch work',async()=>{
 const env={DB:{},GITHUB_TOKEN:'test',RADAR_KEY:'test',AUTH_EMAIL:'owner@example.test',AUTH_PASSWORD_HASH:'test'};
 assert.equal((await worker.fetch(new Request('https://radar.test/api/file?path=data/user.enc'),env)).status,401);
 assert.equal((await worker.fetch(new Request('https://radar.test/api/dispatch',{method:'POST',headers:{Origin:'https://evil.test'}}),env)).status,403);
});
test('owner login uses an HttpOnly session and rejects an incorrect password',async()=>{
 const env={GITHUB_TOKEN:'test',RADAR_KEY:'test',AUTH_EMAIL:'owner@example.test',AUTH_PASSWORD:'a-long-owner-password',DB:{prepare(sql){return {bind(){return {async run(){return{};},async first(){return sql.startsWith('SELECT count') ? {count:1} : null;}};}}}}};
 const request=password=>new Request('https://radar.test/api/login',{method:'POST',headers:{Origin:'https://radar.test','Content-Type':'application/json'},body:JSON.stringify({email:'owner@example.test',password})});
 const good=await worker.fetch(request('a-long-owner-password'),env);
 assert.equal(good.status,200);assert.match(good.headers.get('Set-Cookie'),/HttpOnly; Secure; SameSite=Strict/);
 assert.equal((await worker.fetch(request('incorrect'),env)).status,401);
});
test('signed-in reads return large files (engine data, PDFs) and files over the contents-API limit',async()=>{
 const big='{"listings":"'+'x'.repeat(400000)+'"}', sealed=await seal(big,'test-key');
 const env={GITHUB_TOKEN:'test',RADAR_KEY:'test-key',AUTH_EMAIL:'owner@example.test',AUTH_PASSWORD:'p',DB:{prepare(){return {bind(){return {async first(){return {token:'t'};},async run(){return{};}};}};}}};
 const original=globalThis.fetch;
 for(const raw of [false,true]) {
  globalThis.fetch=async(url,options)=>options.headers.Accept==='application/vnd.github.raw' ? new Response(sealed)
   : Response.json(raw ? {sha:'s',encoding:'none',content:''} : {sha:'s',encoding:'base64',content:Buffer.from(sealed).toString('base64')});
  try {
   const response=await worker.fetch(new Request('https://radar.test/api/file?path=data/engine.enc',{headers:{Cookie:'__Host-radar=abc'}}),env);
   assert.equal(response.status,200);
   assert.equal(Buffer.from((await response.json()).base64,'base64').toString(),big);
  } finally { globalThis.fetch=original; }
 }
});
test('saves reuse the salt of opened data so the derived key is not recomputed',async()=>{
 const first=JSON.parse(await seal('{}','salt-key'));
 await open(JSON.stringify(first),'salt-key');
 const second=JSON.parse(await seal('{"a":1}','salt-key'));
 assert.equal(second.salt,first.salt);assert.notEqual(second.iv,first.iv);
});
test('production key (RADAR_DATA_KEY) opens and saves without PBKDF2, and names files not yet re-keyed',async()=>{
 const salt=Buffer.from('fedcba9876543210');
 const fixed={RADAR_DATA_KEY:salt.toString('base64')+':'+pbkdf2Sync('data-pass',salt,250000,32,'sha256').toString('base64')};
 const {dataKey}=await import('./worker.mjs');
 // a file sealed by the engine for that salt (re-sealed here with the derived key for the test)
 const derived=JSON.parse(await seal('{"requests":[],"marks":{}}',dataKey(fixed)));
 assert.equal(derived.salt,salt.toString('base64'));
 assert.equal(new TextDecoder().decode(await open(JSON.stringify(derived),dataKey(fixed))),'{"requests":[],"marks":{}}');
 assert.equal(new TextDecoder().decode(await open(JSON.stringify(derived),'data-pass')),'{"requests":[],"marks":{}}');
 const other=await seal('{}','another-pass');
 const env={...fixed,GITHUB_TOKEN:'t',AUTH_EMAIL:'o@x.test',AUTH_PASSWORD:'p',DB:{prepare(){return {bind(){return {async first(){return {token:'t'};},async run(){return{};}};}};}}};
 const original=globalThis.fetch;
 globalThis.fetch=async()=>Response.json({sha:'s',encoding:'base64',content:Buffer.from(other).toString('base64')});
 try {
  const response=await worker.fetch(new Request('https://radar.test/api/file?path=data/engine.enc',{headers:{Cookie:'__Host-radar=abc'}}),env);
  assert.equal(response.status,503);assert.equal((await response.json()).error,'Data key pending');
 } finally { globalThis.fetch=original; }
 assert.throws(()=>dataKey({RADAR_DATA_KEY:'short:abc'}));
});
