import {test,before} from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {readFileSync} from 'node:fs';
import defaultWorker,{createAuthCheckWorkerCandidate} from './auth-check-worker-candidate.mjs';
import {createAuthOnlyLocalWorker} from './admin-auth-only-jose-local-worker.mjs';
import {verifyAccessAssertion} from './access-assertion-verifier.mjs';
globalThis.fetch=()=>{throw Error('REAL_NETWORK_FORBIDDEN');};
const host='revalidation-admin.datalabx.jp',issuer='https://synthetic-team.cloudflareaccess.com';
const NOW=Date.parse('2026-10-24T00:00:00Z'),audience='a'.repeat(64),email='synthetic-owner@example.invalid';
let pair,key;
before(async()=>{
  pair=await webcrypto.subtle.generateKey({name:'RSASSA-PKCS1-v1_5',modulusLength:2048,
    publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['sign','verify']);
  key={...await webcrypto.subtle.exportKey('jwk',pair.publicKey),kid:'synthetic-key',alg:'RS256',use:'sig'};
});
const env=()=>({AUTH_CHECK_ENABLED:'true',AUTH_CHECK_SCOPE:'AUTHENTICATION_ONLY',
  ACCESS_ISSUER:issuer,ACCESS_AUDIENCE:audience,ACCESS_OWNER_EMAIL:email});
const identity=()=>({issuer,audience,ownerEmail:email});
async function token(changes={}){
  const b64=x=>Buffer.from(x).toString('base64url');
  const payload={iss:issuer,aud:[audience],email,sub:'synthetic-owner',type:'app',
    iat:NOW/1000,nbf:NOW/1000,exp:NOW/1000+900,...changes};
  const data=b64(JSON.stringify({alg:'RS256',typ:'JWT',kid:key.kid}))+'.'+b64(JSON.stringify(payload));
  return data+'.'+b64(await webcrypto.subtle.sign('RSASSA-PKCS1-v1_5',pair.privateKey,new TextEncoder().encode(data)));
}
const request=(jwt,path='/auth-check',init={})=>new Request('https://'+host+path,
  {...init,headers:{...(jwt?{'cf-access-jwt-assertion':jwt}:{}),...init.headers}});
function fixture(fetcher){
  const calls=[];let time=NOW;
  const worker=createAuthCheckWorkerCandidate({clock:()=>time,fetchPublicKeys:async(url,init)=>{
    calls.push({url,init});return fetcher?fetcher(url,init):new Response(JSON.stringify({keys:[key]}),
      {headers:{'content-type':'application/json'}});
  }});
  return {worker,calls,setTime:t=>{time=t;}};
}

test('default Worker interface stays denied without explicit configuration',async()=>{
  const r=await defaultWorker.fetch(request(await token()),{});assert.equal(r.status,403);
  assert.equal(defaultWorker.production_ready,false);
});
test('all five exact settings are required before any key request',async()=>{
  const jwt=await token();
  for(const name of Object.keys(env())){
    const settings=env();delete settings[name];const f=fixture();
    assert.equal((await f.worker.fetch(request(jwt),settings)).status,403);assert.equal(f.calls.length,0);
  }
});
test('enable and scope are exact strings, not caller authentication flags',async()=>{
  const jwt=await token();
  for(const change of [{AUTH_CHECK_ENABLED:true},{AUTH_CHECK_ENABLED:'false'},
    {AUTH_CHECK_ENABLED:'TRUE'},{AUTH_CHECK_SCOPE:'PRODUCTION'},{AUTH_CHECK_SCOPE:'LOCAL_ONLY'}]){
    const f=fixture();assert.equal((await f.worker.fetch(request(jwt),{...env(),...change})).status,403);
    assert.equal(f.calls.length,0);
  }
});
test('extra bindings configuration arrays and inherited settings fail closed',async()=>{
  const jwt=await token();
  for(const settings of [null,[],Object.create(env()),{...env(),DB:{}},{...env(),EXECUTOR:()=>{}},
    {...env(),timeoutMs:5000}]){
    const f=fixture();assert.equal((await f.worker.fetch(request(jwt),settings)).status,403);assert.equal(f.calls.length,0);
  }
});
test('invalid trusted identity values never select a key endpoint',async()=>{
  const jwt=await token();
  for(const change of [{ACCESS_ISSUER:issuer+'/'},{ACCESS_ISSUER:'https://attacker.invalid'},
    {ACCESS_AUDIENCE:'wrong'},{ACCESS_OWNER_EMAIL:''}]){
    const f=fixture();assert.equal((await f.worker.fetch(request(jwt),{...env(),...change})).status,403);
    assert.equal(f.calls.length,0);
  }
});
test('signed synthetic identity succeeds with business execution disabled',async()=>{
  const f=fixture(),r=await f.worker.fetch(request(await token()),env());assert.equal(r.status,200);
  assert.deepEqual(await r.json(),{status:'AUTHENTICATED_EXECUTION_DISABLED',production_ready:false});
});
test('only exact HTTPS management host is accepted',async()=>{
  const jwt=await token();
  for(const url of ['https://other.invalid/auth-check','http://'+host+'/auth-check','https://'+host+':444/auth-check']){
    const f=fixture();assert.equal((await f.worker.fetch(new Request(url,{headers:{'cf-access-jwt-assertion':jwt,
      'x-forwarded-host':host}}),env())).status,403);assert.equal(f.calls.length,0);
  }
  const f=fixture();assert.equal((await f.worker.fetch(request(jwt,'/auth-check',{headers:{host:'other.invalid'}}),env())).status,403);
  assert.equal(f.calls.length,0);
});
test('root execution and alternate paths are absent',async()=>{
  const jwt=await token();for(const path of ['/','/auth-check/','/execute','/go/synthetic','/operations/execute']){
    const f=fixture();assert.equal((await f.worker.fetch(request(jwt,path),env())).status,404);assert.equal(f.calls.length,0);
  }
});
test('non-GET methods are rejected before loading keys',async()=>{
  const jwt=await token();for(const method of ['POST','PUT','DELETE','PATCH','HEAD','OPTIONS']){
    const f=fixture(),r=await f.worker.fetch(request(jwt,'/auth-check',{method}),env());
    assert.equal(r.status,405);assert.equal(r.headers.get('allow'),'GET');assert.equal(f.calls.length,0);
  }
});
test('query parameters cannot become commands or key destinations',async()=>{
  const f=fixture();assert.equal((await f.worker.fetch(request(await token(),'/auth-check?execute=1'),env())).status,400);
  assert.equal(f.calls.length,0);
});
test('cookies email headers and authenticated flags are not credentials',async()=>{
  for(const headers of [{},{authenticated:'true'},{'cf-access-authenticated-user-email':email},
    {cookie:'CF_Authorization=synthetic-not-a-token'}]){
    const f=fixture();assert.equal((await f.worker.fetch(request(null,'/auth-check',{headers}),env())).status,403);
    assert.equal(f.calls.length,0);
  }
});
test('owner audience issuer type and lifetime validation are unchanged',async()=>{
  for(const change of [{email:'other@example.invalid'},{aud:['b'.repeat(64)]},
    {iss:'https://other.cloudflareaccess.com'},{type:'org'},{exp:NOW/1000},{exp:NOW/1000+901},
    {nbf:NOW/1000+1},{common_name:'synthetic-service'}]){
    const f=fixture();assert.equal((await f.worker.fetch(request(await token(change)),env())).status,403);
    assert.equal(f.calls.length,0);
  }
});
test('tampered cryptographic signature is rejected',async()=>{
  const parts=(await token()).split('.'),sig=Buffer.from(parts[2],'base64url');sig[0]^=1;parts[2]=sig.toString('base64url');
  assert.equal((await fixture().worker.fetch(request(parts.join('.')),env())).status,403);
});
test('key transport receives only fixed public endpoint without JWT cookie or owner email',async()=>{
  const f=fixture();await f.worker.fetch(request(await token(),' /auth-check'.trim(),{headers:{cookie:'synthetic-cookie'}}),env());
  assert.equal(f.calls.length,1);const {url,init}=f.calls[0];assert.equal(url,issuer+'/cdn-cgi/access/certs');
  assert.deepEqual(init.headers,{Accept:'application/json'});assert.equal(init.credentials,'omit');
  assert.equal(init.redirect,'error');assert.equal(init.referrerPolicy,'no-referrer');
  assert.equal(JSON.stringify({url,headers:init.headers}).includes(email),false);
});
test('public-key failures malformed JSON and redirection all deny',async()=>{
  const jwt=await token();for(const fetcher of [()=>{throw Error('SYNTHETIC_FAILURE');},
    ()=>new Response('bad',{headers:{'content-type':'application/json'}}),
    ()=>Response.redirect('https://attacker.invalid',302)]){
    assert.equal((await fixture(fetcher).worker.fetch(request(jwt),env())).status,403);
  }
});
test('same trusted configuration reuses bounded cache and refreshes after expiry',async()=>{
  const f=fixture(),jwt=await token();
  for(let i=0;i<2;i++)assert.equal((await f.worker.fetch(request(jwt),env())).status,200);
  assert.equal(f.calls.length,1);f.setTime(NOW+60000);
  assert.equal((await f.worker.fetch(request(jwt),env())).status,200);assert.equal(f.calls.length,2);
});
test('changing or disabling trusted configuration cannot reuse identity or old cache',async()=>{
  const f=fixture(),jwt=await token(),settings=env();assert.equal((await f.worker.fetch(request(jwt),settings)).status,200);
  settings.ACCESS_OWNER_EMAIL='other@example.invalid';assert.equal((await f.worker.fetch(request(jwt),settings)).status,403);
  assert.equal(f.calls.length,1);assert.equal((await f.worker.fetch(request(jwt),{})).status,403);
  assert.equal((await f.worker.fetch(request(jwt),env())).status,200);assert.equal(f.calls.length,2);
});
test('responses are fixed no-store non-indexable and contain no identity or token',async()=>{
  const f=fixture(),jwt=await token();for(const req of [request(jwt),request(null),request(jwt,'/'),
    request(jwt,'/auth-check',{method:'POST'})]){
    const r=await f.worker.fetch(req,env()),body=await r.text();
    for(const value of [jwt,email,issuer,audience])assert.equal(body.includes(value),false);
    assert.equal(r.headers.get('cache-control'),'no-store');assert.match(r.headers.get('x-robots-tag'),/noindex/);
    assert.equal(r.headers.get('x-frame-options'),'DENY');assert.equal(r.headers.has('access-control-allow-origin'),false);
  }
});
test('existing LOCAL_ONLY worker still refuses the new authentication-only scope',async()=>{
  const config={mode:'AUTHENTICATION_ONLY',hostname:host,...identity()};let loads=0;
  const w=createAuthOnlyLocalWorker({config,clock:()=>NOW,loadJwks:async()=>{loads++;return {keys:[key]};}});
  assert.equal((await w.fetch(request(await token()))).status,403);assert.equal(loads,0);
});
test('shared verifier validates trusted config and injections before loading keys',async()=>{
  let loads=0;const load=async()=>{loads++;return {keys:[key]};};const jwt=await token();
  for(const config of [null,{...identity(),issuer:'https://attacker.invalid'},{...identity(),extra:true}])
    assert.equal(await verifyAccessAssertion(jwt,config,load,()=>NOW),false);
  assert.equal(await verifyAccessAssertion(jwt,identity(),load,()=>NOW,0),false);assert.equal(loads,0);
});
test('missing or throwing clock and fetch injections deny without disclosure',async()=>{
  const jwt=await token();for(const settings of [{},{clock:()=>NOW},
    {clock:()=>{throw Error('PRIVATE_CLOCK');},fetchPublicKeys:async()=>{throw Error('SYNTHETIC_FAILURE');}}]){
    assert.equal((await createAuthCheckWorkerCandidate(settings).fetch(request(jwt),env())).status,403);
  }
});
test('a hung key request is bounded and aborts without extending the 800ms transport limit',async()=>{
  let signal;const f=fixture((_url,init)=>{signal=init.signal;return new Promise(()=>{});});
  assert.equal((await f.worker.fetch(request(await token()),env())).status,403);assert.equal(signal.aborted,true);
});
test('worker source has no logging execution bindings scheduling or private identity values',()=>{
  const source=readFileSync(new URL('./auth-check-worker-candidate.mjs',import.meta.url),'utf8');
  for(const forbidden of ['console.','DMM_API','AFFILIATE_ITEM_LOOKUP','scheduled(',email,issuer,audience])
    assert.equal(source.includes(forbidden),false);
  assert.match(source,/export default createAuthCheckWorkerCandidate/);
});
