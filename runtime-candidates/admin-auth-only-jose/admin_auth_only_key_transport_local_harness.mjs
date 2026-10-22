import {test,before} from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {createBoundedPublicJwksLoader,createAuthOnlyTransportCandidate} from './admin-auth-only-key-transport-local.mjs';
globalThis.fetch=()=>{throw Error('REAL_NETWORK_FORBIDDEN');};
const NOW=Date.parse('2026-10-22T00:00:00Z'),issuer='https://synthetic-team.cloudflareaccess.com';
const endpoint=issuer+'/cdn-cgi/access/certs',host='revalidation-admin.datalabx.jp';
const audience='a'.repeat(64),email='synthetic-owner@example.invalid';
let pair,other,key,rotated;
before(async()=>{
  const algorithm={name:'RSASSA-PKCS1-v1_5',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'};
  pair=await webcrypto.subtle.generateKey(algorithm,true,['sign','verify']);
  other=await webcrypto.subtle.generateKey(algorithm,true,['sign','verify']);
  key={...await webcrypto.subtle.exportKey('jwk',pair.publicKey),kid:'synthetic-key',alg:'RS256',use:'sig'};
  rotated={...await webcrypto.subtle.exportKey('jwk',other.publicKey),kid:'synthetic-rotated',alg:'RS256',use:'sig'};
});
const response=(value={keys:[key]},options={})=>new Response(JSON.stringify(value),
  {status:200,...options,headers:{'content-type':'application/json',...(options.headers||{})}});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture({fetcher,limits={},config={}}={}){
  let time=NOW;const calls=[];
  const fetchPublicKeys=async(url,init)=>{calls.push({url,init});return fetcher?fetcher(url,init,calls.length):response();};
  const clock=()=>time;
  const load=createBoundedPublicJwksLoader({mode:'LOCAL_ONLY',issuer,clock,fetchPublicKeys,...limits,...config});
  return {load,calls,fetchPublicKeys,clock,setTime:value=>{time=value;}};
}
const load=(f,controller=new AbortController(),url=endpoint)=>f.load(url,{signal:controller.signal});
const claims=()=>({iss:issuer,aud:[audience],email,sub:'synthetic-subject',type:'app',
  iat:NOW/1000,nbf:NOW/1000,exp:NOW/1000+900});
async function token(payload=claims(),header={alg:'RS256',typ:'JWT',kid:'synthetic-key'},signingKey){
  const b64=value=>Buffer.from(value).toString('base64url');
  const data=b64(JSON.stringify(header))+'.'+b64(JSON.stringify(payload));
  return data+'.'+b64(await webcrypto.subtle.sign('RSASSA-PKCS1-v1_5',signingKey||pair.privateKey,new TextEncoder().encode(data)));
}
const config=()=>({mode:'LOCAL_ONLY',hostname:host,issuer,audience,ownerEmail:email});
const request=jwt=>new Request('https://'+host+'/auth-check',{headers:jwt?{'cf-access-jwt-assertion':jwt}:{}});
test('exact trusted endpoint and safe GET options; no caller credentials',async()=>{
  const f=fixture(),result=await load(f);assert.equal(result.keys[0].kid,key.kid);
  assert.equal(f.calls.length,1);const {url,init}=f.calls[0];
  assert.equal(url,endpoint);assert.equal(init.method,'GET');assert.equal(init.redirect,'error');
  assert.equal(init.credentials,'omit');assert.equal(init.referrerPolicy,'no-referrer');
  assert.equal(init.cache,'no-store');assert.deepEqual(init.headers,{Accept:'application/json'});
  assert.equal(init.signal.aborted,true);
});
test('wrong URL issuer hostname query or protocol cannot select a destination',async()=>{
  const f=fixture();for(const url of ['http://synthetic-team.cloudflareaccess.com/cdn-cgi/access/certs',
    issuer+'/cdn-cgi/access/certs?extra=1','https://attacker.invalid/keys',issuer+'/other'])
    await assert.rejects(()=>load(f,new AbortController(),url),/PUBLIC_KEY_UNAVAILABLE/u);
  assert.equal(f.calls.length,0);
});
test('invalid config and transport limits fail closed without fetch',async()=>{
  for(const config of [{mode:'PRODUCTION'},{issuer:'https://attacker.invalid'},{issuer:issuer+'/'},
    {issuer:issuer+':443'},{clock:null},{fetchPublicKeys:null}]){
    const f=fixture({config});await assert.rejects(()=>load(f));assert.equal(f.calls.length,0);
  }
  for(const limits of [{timeoutMs:0},{timeoutMs:801},{maxBytes:65537},{maxBytes:0},
    {cacheMs:0},{cacheMs:300001},{cooldownMs:0},{cooldownMs:60001},{timeoutMs:NaN}]){
    const f=fixture({limits});await assert.rejects(()=>load(f));assert.equal(f.calls.length,0);
  }
});
test('missing and pre-aborted caller signals do not fetch',async()=>{
  const f=fixture();await assert.rejects(()=>f.load(endpoint));
  const controller=new AbortController();controller.abort();await assert.rejects(()=>load(f,controller));
  assert.equal(f.calls.length,0);
});
test('HTTP errors non-response values and redirection fail',async()=>{
  for(const fetcher of [()=>new Response(null,{status:204}),()=>response({}, {status:500}),
    ()=>Response.redirect('https://attacker.invalid',302),()=>({status:200}),()=>{throw Error('PRIVATE_NETWORK_FAILURE');}]){
    const f=fixture({fetcher});await assert.rejects(()=>load(f),/PUBLIC_KEY_UNAVAILABLE/u);
  }
  for(const field of ['url','redirected']){
    const f=fixture({fetcher:()=>{const r=response();Object.defineProperty(r,field,{value:field==='url'?'https://other.invalid':true});return r;}});
    await assert.rejects(()=>load(f));
  }
});
test('content type must be JSON',async()=>{
  for(const type of ['text/html','text/plain','application/octet-stream','']){
    const f=fixture({fetcher:()=>response(undefined,{headers:{'content-type':type}})});
    await assert.rejects(()=>load(f));
  }
  const f=fixture({fetcher:()=>response(undefined,{headers:{'content-type':'application/json; charset=utf-8'}})});
  assert.equal((await load(f)).keys.length,1);
});
test('declared length invalid negative or oversized is refused',async()=>{
  for(const length of ['65537','-1','1.5','abc','9007199254740992']){
    const f=fixture({fetcher:()=>response(undefined,{headers:{'content-length':length}})});
    await assert.rejects(()=>load(f));
  }
});
test('actual streamed byte count is bounded independent of Content-Length',async()=>{
  let cancelled=false;
  const f=fixture({limits:{maxBytes:1024},fetcher:()=>new Response(new ReadableStream({
    start(c){c.enqueue(new Uint8Array(700));c.enqueue(new Uint8Array(700));},
    cancel(){cancelled=true;}
  }),{headers:{'content-type':'application/json','content-length':'1'}})});
  await assert.rejects(()=>load(f));assert.equal(cancelled,true);
});
test('invalid JSON and invalid UTF-8 fail safely',async()=>{
  for(const body of ['not-json','[]','null',new Uint8Array([0xff,0xfe])]){
    const f=fixture({fetcher:()=>new Response(body,{headers:{'content-type':'application/json'}})});
    await assert.rejects(()=>load(f),/PUBLIC_KEY_UNAVAILABLE/u);
  }
});
test('key shapes count duplicates private fields algorithms and sizes are constrained',async()=>{
  for(const value of [{},{keys:[]},{keys:'bad'},{keys:Array(17).fill(key)},
    {keys:[key,key]},{keys:[{...key,d:'SYNTHETIC_NOT_SECRET'}]},
    {keys:[{...key,kty:'oct'}]},{keys:[{...key,n:'bad'}]},
    {keys:[{...key,e:'Aw'}]},{keys:[{...key,use:'enc'}]},
    {keys:[{...key,alg:'RS512'}]},{keys:[{...key,key_ops:['sign','verify']}]}]){
    const f=fixture({fetcher:()=>response(value)});await assert.rejects(()=>load(f));
  }
});
test('only public verification fields are cached and returned',async()=>{
  const f=fixture({fetcher:()=>response({keys:[{...key,unknown:'DROP'}],public_cert:'DROP',metadata:'DROP'})});
  const result=await load(f);
  assert.deepEqual(Object.keys(result),['keys']);
  assert.deepEqual(Object.keys(result.keys[0]),['kty','kid','n','e','alg','use']);
});

test('exact sixteen-key boundary is accepted with distinct key identifiers',async()=>{
  const keys=Array.from({length:16},(_,i)=>({...key,kid:'synthetic-boundary-'+i}));
  const f=fixture({fetcher:()=>response({keys})});
  const result=await load(f);
  assert.equal(result.keys.length,16);
  assert.equal(new Set(result.keys.map(k=>k.kid)).size,16);
  assert.equal(f.calls.length,1);
});

test('RSA modulus outside the byte bounds is rejected without caching',async()=>{
  for(const bytes of [255,513]){
    const n=Buffer.alloc(bytes,0xff).toString('base64url');
    const f=fixture({fetcher:()=>response({keys:[{...key,n}]})});
    await assert.rejects(()=>load(f),/PUBLIC_KEY_UNAVAILABLE/u);
    await assert.rejects(()=>load(f),/PUBLIC_KEY_UNAVAILABLE/u);
    assert.equal(f.calls.length,1);
  }
});

test('late streamed body after cancellation cannot publish keys into cache',async()=>{
  let streamController,cancelled=false;
  const f=fixture({fetcher:(_url,_init,n)=>n>1?response():new Response(new ReadableStream({
    start(controller){streamController=controller;},cancel(){cancelled=true;}
  }),{headers:{'content-type':'application/json'}})});
  const controller=new AbortController();
  const pending=load(f,controller),denied=assert.rejects(pending,/PUBLIC_KEY_UNAVAILABLE/u);
  await tick();controller.abort();await denied;await tick();
  assert.equal(cancelled,true);
  assert.throws(()=>streamController.enqueue(new TextEncoder().encode(JSON.stringify({keys:[rotated]}))));
  await assert.rejects(()=>load(f));assert.equal(f.calls.length,1);
  f.setTime(NOW+30000);
  assert.equal((await load(f)).keys[0].kid,key.kid);
  assert.equal(f.calls.length,2);
});
test('cached results are cloned and expire exactly without background refresh',async()=>{
  const f=fixture();const first=await load(f);first.keys[0].kid='mutated';
  f.setTime(NOW+59999);assert.equal((await load(f)).keys[0].kid,key.kid);assert.equal(f.calls.length,1);
  await tick();assert.equal(f.calls.length,1);
  f.setTime(NOW+60000);await load(f);assert.equal(f.calls.length,2);
});
test('rotation is observed after cache expiry, with no forced kid retry',async()=>{
  const f=fixture({fetcher:(_url,_init,n)=>response({keys:[n===1?key:rotated]})});
  assert.equal((await load(f)).keys[0].kid,key.kid);
  f.setTime(NOW+60000);assert.equal((await load(f)).keys[0].kid,rotated.kid);
  assert.equal(f.calls.length,2);
});
test('failure cooldown suppresses retries until the boundary',async()=>{
  const f=fixture({fetcher:(_url,_init,n)=>{if(n===1)throw Error('FAILED');return response();}});
  await assert.rejects(()=>load(f));await assert.rejects(()=>load(f));assert.equal(f.calls.length,1);
  f.setTime(NOW+29999);await assert.rejects(()=>load(f));assert.equal(f.calls.length,1);
  f.setTime(NOW+30000);await load(f);assert.equal(f.calls.length,2);
});
test('expired cache is never reused on refresh failure',async()=>{
  const f=fixture({fetcher:(_url,_init,n)=>{if(n>1)throw Error('FAILED');return response();}});
  await load(f);f.setTime(NOW+60000);await assert.rejects(()=>load(f));
  await assert.rejects(()=>load(f));assert.equal(f.calls.length,2);
});
test('hung HTTP fetch has bounded deadline and aborts its signal',async()=>{
  let signal;const f=fixture({limits:{timeoutMs:20},fetcher:(_url,init)=>{signal=init.signal;return new Promise(()=>{});}});
  await assert.rejects(()=>load(f));assert.equal(signal.aborted,true);assert.equal(f.calls.length,1);
});
test('hung response body is covered by the same deadline and cancelled',async()=>{
  let cancelled=false;const f=fixture({limits:{timeoutMs:20},fetcher:()=>new Response(new ReadableStream({
    start(){},cancel(){cancelled=true;}
  }),{headers:{'content-type':'application/json'}})});
  await assert.rejects(()=>load(f));assert.equal(cancelled,true);
});
test('late fetch cannot populate cache after deadline',async()=>{
  let finish;
  const f=fixture({limits:{timeoutMs:20},fetcher:(_url,_init,n)=>n===1?new Promise(r=>{finish=r;}):response()});
  await assert.rejects(()=>load(f));finish(response({keys:[rotated]}));await tick();
  f.setTime(NOW+30000);assert.equal((await load(f)).keys[0].kid,key.kid);assert.equal(f.calls.length,2);
});
test('concurrent callers share one bounded key request',async()=>{
  let finish;const f=fixture({fetcher:()=>new Promise(r=>{finish=r;})});
  const a=load(f),b=load(f);assert.equal(f.calls.length,1);finish(response());
  const [x,y]=await Promise.all([a,b]);assert.deepEqual(x,y);x.keys[0].kid='changed';
  assert.equal(y.keys[0].kid,key.kid);
});
test('one caller cancellation does not cancel another caller',async()=>{
  let finish,signal;const f=fixture({fetcher:(_url,init)=>{signal=init.signal;return new Promise(r=>{finish=r;});}});
  const controller=new AbortController(),a=load(f,controller),b=load(f);
  const rejected=assert.rejects(a);controller.abort();await rejected;assert.equal(signal.aborted,false);
  finish(response());assert.equal((await b).keys[0].kid,key.kid);
});
test('all callers cancelling aborts shared work and prevents late cache updates',async()=>{
  let finish,signal;const f=fixture({fetcher:(_url,init)=>{signal=init.signal;return new Promise(r=>{finish=r;});}});
  const controller=new AbortController(),a=load(f,controller),rejected=assert.rejects(a);
  controller.abort();await rejected;assert.equal(signal.aborted,true);
  finish(response());await tick();await assert.rejects(()=>load(f));assert.equal(f.calls.length,1);
});
test('invalid and backwards clocks cannot extend cached key validity',async()=>{
  const f=fixture();await load(f);f.setTime(NOW-1);await assert.rejects(()=>load(f));
  const invalid=fixture();invalid.setTime(NaN);await assert.rejects(()=>load(invalid));
  assert.equal(invalid.calls.length,0);
});
test('composition verifies signed identity but sends no JWT to public key transport',async()=>{
  const f=fixture();const worker=createAuthOnlyTransportCandidate({config:config(),clock:f.clock,fetchPublicKeys:f.fetchPublicKeys});
  assert.equal((await worker.fetch(request(null))).status,403);assert.equal(f.calls.length,0);
  assert.equal((await worker.fetch(request(await token({...claims(),email:'other@example.invalid'})))).status,403);
  assert.equal(f.calls.length,0);
  const jwt=await token(),r=await worker.fetch(request(jwt));assert.equal(r.status,200);
  assert.deepEqual(await r.json(),{status:'AUTHENTICATED_EXECUTION_DISABLED',production_ready:false});
  assert.equal(JSON.stringify({url:f.calls[0].url,headers:f.calls[0].init.headers}).includes(jwt),false);
  assert.equal(worker.local_only,true);assert.equal(worker.production_ready,false);
});
test('composition remains closed for missing config fetch and production mode',async()=>{
  const jwt=await token();for(const options of [{},{config:config(),clock:()=>NOW},
    {config:{...config(),mode:'PRODUCTION'},clock:()=>NOW,fetchPublicKeys:async()=>response()}]){
    assert.equal((await createAuthOnlyTransportCandidate(options).fetch(request(jwt))).status,403);
  }
});
test('new rotated tokens remain denied until bounded cache refresh',async()=>{
  const f=fixture({fetcher:(_url,_init,n)=>response({keys:[n===1?key:rotated]})});
  const worker=createAuthOnlyTransportCandidate({config:config(),clock:f.clock,fetchPublicKeys:f.fetchPublicKeys});
  assert.equal((await worker.fetch(request(await token()))).status,200);
  const jwt=await token(claims(),{alg:'RS256',typ:'JWT',kid:rotated.kid},other.privateKey);
  assert.equal((await worker.fetch(request(jwt))).status,403);assert.equal(f.calls.length,1);
  f.setTime(NOW+60000);assert.equal((await worker.fetch(request(jwt))).status,200);assert.equal(f.calls.length,2);
});
