// Optional server deployment. GitHub Pages keeps using its existing encrypted-data login.
import {pbkdf2} from 'node:crypto';
const encoder = new TextEncoder();
const decode = value => Uint8Array.from(atob(value), c => c.charCodeAt(0));
// Chunked: spreading a few hundred KB (engine.enc, a PDF) into one call overflows the stack.
const encode = bytes => {
  const view=new Uint8Array(bytes);let text='';
  for(let i=0;i<view.length;i+=0x8000) text+=String.fromCharCode.apply(null,view.subarray(i,i+0x8000));
  return btoa(text);
};
const digest = async value => encode(await crypto.subtle.digest('SHA-256', encoder.encode(value)));
const json = (data, status=200, headers={}) => new Response(JSON.stringify(data), {status, headers:{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff',...headers}});
const cookie = (value, age=86400) => `__Host-radar=${value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${age}`;
const pbkdf2Bits=(password,salt,iterations)=>new Promise((resolve,reject)=>pbkdf2(password,salt,iterations,32,'sha256',
  (error,key)=>error ? reject(error) : resolve(new Uint8Array(key))));
// A free-plan Worker gets about 10 ms of CPU per request and one 250,000-round PBKDF2 costs several times
// that. Data keys are therefore derived once per isolate, and saves reuse the salt of the files the
// engine writes (one salt per passphrase), so a warm isolate opens and saves without deriving again.
const keys=new Map(), salts=new Map();
export async function derive(password, salt, iterations) {
  const id=await digest(password)+':'+iterations+':'+encode(salt);
  if(!keys.has(id)) {
    if(keys.size>=16) keys.delete(keys.keys().next().value);
    keys.set(id,pbkdf2Bits(password,salt,iterations).catch(error=>{keys.delete(id);throw error;}));
  }
  return keys.get(id);
}
export async function open(text, password) {
  const item=JSON.parse(text);
  const bits=await derive(password,decode(item.salt),item.iter);
  const key=await crypto.subtle.importKey('raw',bits,'AES-GCM',false,['decrypt']);
  const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:decode(item.iv)},key,decode(item.ct));
  if(item.iter===250000) salts.set(await digest(password),item.salt);
  return plain;
}
export async function seal(text,password) {
  // Same key with a fresh random IV per file: AES-GCM stays safe, and the salt is still unique to this data.
  const known=salts.get(await digest(password));
  const salt=known ? decode(known) : crypto.getRandomValues(new Uint8Array(16)),iv=crypto.getRandomValues(new Uint8Array(12));
  const bits=await derive(password,salt,250000);
  const key=await crypto.subtle.importKey('raw',bits,'AES-GCM',false,['encrypt']);
  const ct=await crypto.subtle.encrypt({name:'AES-GCM',iv},key,encoder.encode(text));
  return JSON.stringify({v:1,kdf:'pbkdf2-sha256',iter:250000,salt:encode(salt),iv:encode(iv),ct:encode(ct)});
}
export async function verify(password, record) {
  const [iterations,salt,expected]=record.split(':');
  if(Number(iterations)!==600000 || !salt || !expected) return false;
  const actual=await pbkdf2Bits(password,decode(salt),600000), target=decode(expected);
  let difference=actual.length ^ target.length;
  for(let i=0;i<actual.length;i++) difference |= actual[i] ^ (target[i] || 0);
  return difference===0;
}
async function github(env,path,options={}) {
  const result=await fetch(`https://api.github.com/repos/uae00060-lab/uae-car-radar${path}`,{...options,headers:{'Authorization':`Bearer ${env.GITHUB_TOKEN}`,'Accept':'application/vnd.github+json','User-Agent':'car-radar-gateway','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json',...(options.headers || {})}});
  return result;
}
export default {async fetch(request,env) {
  const url=new URL(request.url), path=url.pathname;
  if(!path.startsWith('/api/')) {
    const response=env.ASSETS ? await env.ASSETS.fetch(request) : await fetch(new URL(path.replace(/^\//,''), 'https://uae00060-lab.github.io/uae-car-radar/'), {headers:{'Accept':request.headers.get('Accept') || '*/*'}});
    if(response.headers.get('Content-Type')?.includes('text/html')) {
      const html=(await response.text()).replace('<head>','<head><script>window.RADAR_GATEWAY=true</script>');
      return new Response(html,{status:response.status,headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
    }
    return response;
  }
  if(!env.DB || !env.GITHUB_TOKEN || !env.RADAR_KEY || !env.AUTH_EMAIL || !(env.AUTH_PASSWORD_HASH || env.AUTH_PASSWORD)) return json({error:'Server setup is incomplete'},503);
  if(request.method!=='GET' && request.headers.get('Origin')!==url.origin) return json({error:'Origin rejected'},403);
  let stage='session';
  try {
    const raw=request.headers.get('Cookie')?.match(/(?:^|;\s*)__Host-radar=([A-Za-z0-9-]+)/)?.[1];
    const session=raw && await env.DB.prepare('SELECT token FROM sessions WHERE token=? AND expires>?').bind(await digest(raw),Date.now()).first();
    if(path==='/api/session') return json({gateway:true,authenticated:!!session});
    if(path==='/api/login' && request.method==='POST') {
      const ip=await digest(request.headers.get('CF-Connecting-IP') || 'unknown');
      // Count attempts atomically before password verification; one window per IP.
      const window=Math.floor(Date.now()/900000);
      await env.DB.prepare('INSERT INTO attempts(ip,window,count) VALUES(?,?,1) ON CONFLICT(ip,window) DO UPDATE SET count=count+1').bind(ip,window).run();
      const attempt=await env.DB.prepare('SELECT count FROM attempts WHERE ip=? AND window=?').bind(ip,window).first();
      if(attempt.count>8) return json({error:'Try again later'},429);
      const body=await request.text(); if(body.length>4096) return json({error:'Invalid login'},400);
      const {email,password}=JSON.parse(body);
      let valid=false;
      if(typeof password==='string' && password.length<=256) {
        if(env.AUTH_PASSWORD_HASH) valid=await verify(password,env.AUTH_PASSWORD_HASH);
        else {
          // Single-owner password is a runtime secret, never a database field or client value.
          const a=decode(await digest(password)),b=decode(await digest(env.AUTH_PASSWORD));
          let mismatch=0;for(let i=0;i<a.length;i++)mismatch |= a[i]^b[i];valid=mismatch===0;
        }
      }
      if(!valid || String(email).trim().toLowerCase()!==env.AUTH_EMAIL.trim().toLowerCase()) return json({error:'Invalid login'},401);
      const token=crypto.randomUUID()+'-'+crypto.randomUUID();
      await env.DB.prepare('DELETE FROM sessions WHERE expires<?').bind(Date.now()).run();
      await env.DB.prepare('DELETE FROM attempts WHERE window<?').bind(window-1).run();
      await env.DB.prepare('INSERT INTO sessions(token,expires) VALUES(?,?)').bind(await digest(token),Date.now()+86400000).run();
      return json({ok:true},200,{'Set-Cookie':cookie(token)});
    }
    if(!session) return json({error:'Sign in required'},401);
    if(path==='/api/logout' && request.method==='POST') {
      await env.DB.prepare('DELETE FROM sessions WHERE token=?').bind(await digest(raw)).run();
      return json({ok:true},200,{'Set-Cookie':cookie('',0)});
    }
    if(path==='/api/file' && request.method==='GET') {
      const name=url.searchParams.get('path');
      if(!/^(data\/(engine|user)\.enc|reports\/[A-Za-z0-9_-]+\.pdf\.enc)$/.test(name || '')) return json({error:'Invalid file'},400);
      stage='github-read';
      const response=await github(env,`/contents/${name}`,{headers:{}});
      if(!response.ok) return json({error:'File unavailable'},response.status);
      const file=await response.json();
      stage='decrypt-file';
      // The contents API omits files over 1 MB; those are read as raw bytes instead.
      const text=file.encoding==='base64' && file.content ? new TextDecoder().decode(decode(file.content.replace(/\s/g,'')))
        : await (await github(env,`/contents/${name}`,{headers:{'Accept':'application/vnd.github.raw'}})).text();
      const bytes=await open(text,env.RADAR_KEY);
      stage='encode-file';
      return json({plain:true,base64:encode(bytes),sha:file.sha});
    }
    if(path==='/api/user' && request.method==='PUT') {
      const body=await request.text();if(body.length>500000) return json({error:'Data too large'},413);
      const {user,sha}=JSON.parse(body);
      if(!user || !Array.isArray(user.requests) || !user.marks) return json({error:'Invalid data'},400);
      const content=await seal(JSON.stringify(user),env.RADAR_KEY);
      const response=await github(env,'/contents/data/user.enc',{method:'PUT',body:JSON.stringify({message:'dashboard: sync',content:encode(encoder.encode(content)),sha,branch:'main'})});
      const data=await response.json();return json({sha:data.content?.sha},response.status);
    }
    if(path==='/api/github' && request.method==='GET') {
      const target=url.searchParams.get('path') || '';
      if(!/^\/actions\/(workflows\/radar\.yml\/runs|runs(?:\/\d+(?:\/jobs)?)?)(?:\?[^#]*)?$/.test(target)) return json({error:'Path rejected'},403);
      const response=await github(env,target);return json(await response.json(),response.status);
    }
    if(path==='/api/dispatch' && request.method==='POST') {
      const body=await request.json(), input=body.inputs || {};
      if(!['run','watch','review','diagnose','notify-test','retry-notify'].includes(input.cmd) || !['manual','scheduled','opportunity'].includes(input.mode) || !/^[A-Za-z0-9_-]{0,80}$/.test(input.request || '') || !/^[A-Za-z0-9_-]{0,80}$/.test(input.run_id || '')) return json({error:'Invalid task'},400);
      const response=await github(env,'/actions/workflows/radar.yml/dispatches',{method:'POST',body:JSON.stringify({ref:'main',inputs:{cmd:input.cmd,mode:input.mode,request:input.request || 'all',run_id:input.run_id || ''}})});
      return json({ok:response.ok},response.status===204 ? 200 : response.status);
    }
    return json({error:'Not found'},404);
  } catch(error) {console.error(JSON.stringify({code:'gateway_failure',stage,type:error?.name || 'Error',errorCode:String(error?.code || '').replace(/[^A-Za-z0-9_-]/g,'').slice(0,60)}));return json({error:'Request failed',stage},500); }
}};
