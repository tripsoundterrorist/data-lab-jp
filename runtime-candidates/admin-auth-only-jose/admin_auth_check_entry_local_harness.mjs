import {test,before} from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {createLocalAuthCheckEntry} from './admin-auth-check-entry-local.mjs';
globalThis.fetch=()=>{throw Error('REAL_NETWORK_FORBIDDEN');};
const host='revalidation-admin.datalabx.jp',issuer='https://synthetic-team.cloudflareaccess.com';
const now=Date.parse('2026-10-24T00:00:00Z'),audience='a'.repeat(64),ownerEmail='owner@example.invalid';
let pair,jwk;
before(async()=>{
  pair=await webcrypto.subtle.generateKey({name:'RSASSA-PKCS1-v1_5',modulusLength:2048,
    publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['sign','verify']);
  jwk={...await webcrypto.subtle.exportKey('jwk',pair.publicKey),kid:'synthetic-key',alg:'RS256',use:'sig'};
});
const config=()=>({mode:'LOCAL_ONLY',hostname:host,issuer,audience,ownerEmail});
async function token(changes={}){
  const b64=value=>Buffer.from(value).toString('base64url');
  const payload={iss:issuer,aud:[audience],email:ownerEmail,sub:'synthetic-owner',type:'app',
    iat:now/1000,nbf:now/1000,exp:now/1000+900,...changes};
  const data=b64(JSON.stringify({alg:'RS256',kid:jwk.kid,typ:'JWT'}))+'.'+b64(JSON.stringify(payload));
  return data+'.'+b64(await webcrypto.subtle.sign('RSASSA-PKCS1-v1_5',pair.privateKey,new TextEncoder().encode(data)));
}
function fixture(changes={}){
  const calls=[];
  const options={config:config(),clock:()=>now,fetchPublicKeys:async(url,init)=>{
    calls.push({url,init});return new Response(JSON.stringify({keys:[jwk]}),{headers:{'content-type':'application/json'}});
  },...changes};
  return {entry:createLocalAuthCheckEntry(options),calls,options};
}
const request=(jwt,path='/auth-check',init={})=>new Request('https://'+host+path,
  {...init,headers:{...(jwt?{'cf-access-jwt-assertion':jwt}:{}),...init.headers}});

test('signed synthetic identity succeeds with execution disabled and no identity disclosure',async()=>{
  const f=fixture(),jwt=await token(),r=await f.entry.fetch(request(jwt));
  assert.equal(r.status,200);
  assert.deepEqual(await r.json(),{status:'AUTHENTICATED_EXECUTION_DISABLED',production_ready:false});
  assert.equal(f.calls.length,1);
  assert.equal(f.calls[0].url,issuer+'/cdn-cgi/access/certs');
  assert.deepEqual(f.calls[0].init.headers,{Accept:'application/json'});
  assert.equal(f.calls[0].init.credentials,'omit');
});
test('only auth-check exists; root and execution paths never reach keys',async()=>{
  const jwt=await token();
  for(const path of ['/','/execute','/operations/two-route/execute','/auth-check/','/go/synthetic']){
    const f=fixture();assert.equal((await f.entry.fetch(request(jwt,path))).status,404);assert.equal(f.calls.length,0);
  }
});
test('write methods and query parameters cannot reach keys',async()=>{
  const jwt=await token();
  for(const method of ['POST','PUT','DELETE','PATCH','OPTIONS','HEAD']){
    const f=fixture();assert.equal((await f.entry.fetch(request(jwt,'/auth-check',{method}))).status,405);
    assert.equal(f.calls.length,0);
  }
  const f=fixture();assert.equal((await f.entry.fetch(request(jwt,'/auth-check?execute=1'))).status,400);
  assert.equal(f.calls.length,0);
});
test('wrong host protocol or forwarded host cannot grant access',async()=>{
  const jwt=await token();
  for(const address of ['https://other.invalid/auth-check','http://'+host+'/auth-check','https://'+host+':444/auth-check']){
    const f=fixture();assert.equal((await f.entry.fetch(new Request(address,{headers:{'cf-access-jwt-assertion':jwt,'x-forwarded-host':host}}))).status,403);
    assert.equal(f.calls.length,0);
  }
  const f=fixture();assert.equal((await f.entry.fetch(request(jwt,'/auth-check',{headers:{host:'other.invalid'}}))).status,403);
  assert.equal(f.calls.length,0);
});
test('missing token and caller flags do not authenticate',async()=>{
  for(const headers of [{},{authenticated:'true'},{'cf-access-authenticated-user-email':ownerEmail},
    {cookie:'CF_Authorization=synthetic-not-a-token'}]){
    const f=fixture();assert.equal((await f.entry.fetch(request(null,'/auth-check',{headers}))).status,403);
    assert.equal(f.calls.length,0);
  }
});
test('wrong owner issuer audience and expiration remain closed',async()=>{
  for(const change of [{email:'other@example.invalid'},{iss:'https://other.cloudflareaccess.com'},
    {aud:['b'.repeat(64)]},{exp:now/1000},{exp:now/1000+901},{type:'org'}]){
    const f=fixture();assert.equal((await f.entry.fetch(request(await token(change)))).status,403);
    assert.equal(f.calls.length,0);
  }
});
test('signature tampering is rejected by reused verifier',async()=>{
  const jwt=await token(),pieces=jwt.split('.');
  const signature=Buffer.from(pieces[2],'base64url');signature[0]^=1;pieces[2]=signature.toString('base64url');
  assert.equal((await fixture().entry.fetch(request(pieces.join('.')))).status,403);
});
test('missing injections unknown options and production mode fail closed',async()=>{
  const jwt=await token();
  for(const options of [undefined,null,{}, {config:config()},
    {...fixture().options,config:{...config(),mode:'PRODUCTION'}},
    {...fixture().options,env:{}}, {...fixture().options,transport:{timeoutMs:5000}}]){
    const entry=createLocalAuthCheckEntry(options);assert.equal((await entry.fetch(request(jwt))).status,403);
    assert.equal(entry.production_ready,false);
  }
});
test('public-key failures and mutated external config never open access',async()=>{
  const jwt=await token();
  const f=fixture({fetchPublicKeys:async()=>{throw Error('SYNTHETIC_FAILURE');}});
  assert.equal((await f.entry.fetch(request(jwt))).status,403);
  const g=fixture();g.options.config.ownerEmail='other@example.invalid';
  assert.equal((await g.entry.fetch(request(jwt))).status,200);
});
test('responses prevent caching framing and indexing and expose no cross-origin permission',async()=>{
  const f=fixture();
  for(const req of [request(await token()),request(null),request(null,'/'),request(null,'/auth-check',{method:'POST'})]){
    const r=await f.entry.fetch(req);
    assert.equal(r.headers.get('cache-control'),'no-store');assert.equal(r.headers.get('x-frame-options'),'DENY');
    assert.match(r.headers.get('x-robots-tag'),/noindex/);assert.equal(r.headers.has('access-control-allow-origin'),false);
  }
});
test('entry has no default export deployment env logger network or execution imports',()=>{
  const source=readFileSync(new URL('./admin-auth-check-entry-local.mjs',import.meta.url),'utf8');
  assert.equal(/export\s+default|console\.|process\.env|globalThis\.fetch/u.test(source),false);
  assert.deepEqual(source.match(/^import .*$/gmu),[
    "import {createAuthOnlyTransportCandidate} from './admin-auth-only-key-transport-local.mjs';"]);
});
