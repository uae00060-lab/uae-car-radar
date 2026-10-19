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
 const record='100000:'+salt.toString('base64')+':'+pbkdf2Sync('owner-password',salt,100000,32,'sha256').toString('base64');
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
