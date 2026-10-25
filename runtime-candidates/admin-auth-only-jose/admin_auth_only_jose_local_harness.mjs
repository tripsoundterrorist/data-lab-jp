import {test,before} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createAuthOnlyLocalWorker} from './admin-auth-only-jose-local-worker.mjs';
globalThis.fetch=()=>{throw Error('NETWORK_FORBIDDEN');};
const NOW=Date.parse('2026-10-21T13:00:00Z'),seconds=NOW/1000;
const config=()=>({mode:'LOCAL_ONLY',hostname:'revalidation-admin.datalabx.jp',
  issuer:'https://synthetic-team.cloudflareaccess.com',audience:'a'.repeat(64),ownerEmail:'synthetic-owner@example.invalid'});
const claims=()=>({iss:config().issuer,aud:[config().audience],email:config().ownerEmail,
  sub:'synthetic-subject',type:'app',iat:seconds,nbf:seconds,exp:seconds+900});
const b64=bytes=>Buffer.from(bytes).toString('base64url');
const encoded=value=>b64(JSON.stringify(value));
let pair,other,publicJwk;
before(async()=>{
  const algorithm={name:'RSASSA-PKCS1-v1_5',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'};
  pair=await crypto.subtle.generateKey(algorithm,true,['sign','verify']);
  other=await crypto.subtle.generateKey(algorithm,true,['sign','verify']);
  publicJwk={...await crypto.subtle.exportKey('jwk',pair.publicKey),kid:'synthetic-key',alg:'RS256',use:'sig'};
});
async function token(payload=claims(),header={alg:'RS256',typ:'JWT',kid:'synthetic-key'},key=pair.privateKey) {
  const data=encoded(header)+'.'+encoded(payload);
  return data+'.'+b64(await crypto.subtle.sign('RSASSA-PKCS1-v1_5',key,new TextEncoder().encode(data)));
}
const request=(jwt,path='/auth-check',extra={})=>new Request('https://'+config().hostname+path,
  {...extra,headers:{...(jwt?{'cf-access-jwt-assertion':jwt}:{}),...extra.headers}});
function fixture(options={}) {
  let loads=0,lastUrl;
  const worker=createAuthOnlyLocalWorker({config:options.config||config(),clock:options.clock||(()=>NOW),
    keyLoadTimeoutMs:options.timeoutMs??1000,
    async loadJwks(url,context){loads++;lastUrl=url;if(options.fail)throw Error('PRIVATE_KEY_LOADER_FAILURE');
      if(options.loader)return options.loader(url,context);return {keys:options.keys||[publicJwk]};}});
  return {worker,loads:()=>loads,lastUrl:()=>lastUrl};
}
test('cryptographically signed synthetic identity is admitted with execution disabled',async()=>{
  const f=fixture();const r=await f.worker.fetch(request(await token()));
  assert.equal(r.status,200);assert.deepEqual(await r.json(),{status:'AUTHENTICATED_EXECUTION_DISABLED',production_ready:false});
  assert.equal(f.loads(),1);assert.equal(f.lastUrl(),config().issuer+'/cdn-cgi/access/certs');
  assert.equal(f.worker.local_only,true);assert.equal(f.worker.production_ready,false);
});
test('both read-only paths work and output contains no identity or token',async()=>{
  const jwt=await token();for(const path of ['/','/auth-check']){
    const r=await fixture().worker.fetch(request(jwt,path));assert.equal(r.status,200);
    const body=await r.text();for(const privateValue of [jwt,config().ownerEmail,config().issuer,config().audience])assert.equal(body.includes(privateValue),false);
  }
});
test('missing token and caller authentication flags do not authenticate',async()=>{
  for(const headers of [{},{authenticated:'true'},{'cf-access-authenticated-user-email':config().ownerEmail},{cookie:'CF_Authorization=not-a-real-token'}]){
    const f=fixture(),r=await f.worker.fetch(request(null,'/auth-check',{headers}));assert.equal(r.status,403);assert.equal(f.loads(),0);
  }
});
test('wrong identity issuer audience type and machine identities are rejected',async()=>{
  for(const change of [{email:'other@example.invalid'},{iss:'https://attacker.invalid'},
    {aud:['b'.repeat(64)]},{aud:config().audience},{aud:[config().audience,'extra']},{type:'org'},
    {sub:''},{common_name:'synthetic-machine'},{service_token_id:'synthetic-machine'}]){
    const f=fixture(),r=await f.worker.fetch(request(await token({...claims(),...change})));
    assert.equal(r.status,403);assert.equal(f.loads(),0);
  }
});
test('expired future not-before and overlong-lifetime claims fail closed',async()=>{
  for(const change of [{iat:seconds-900,nbf:seconds-900,exp:seconds},{iat:seconds+1},
    {nbf:seconds+1},{exp:seconds+901},{iat:'invalid'},{exp:null},{nbf:-1}]){
    const f=fixture();assert.equal((await f.worker.fetch(request(await token({...claims(),...change})))).status,403);
    assert.equal(f.loads(),0);
  }
});
test('incorrect signature and payload tampering never authenticate',async()=>{
  const signed=await token();const pieces=signed.split('.');pieces[1]=encoded({...claims(),country:'changed'});
  for(const jwt of [await token(claims(),undefined,other.privateKey),pieces.join('.')])
    assert.equal((await fixture().worker.fetch(request(jwt))).status,403);
});
test('algorithm confusion and header key URLs are rejected without any key loading',async()=>{
  for(const header of [{alg:'none',kid:'synthetic-key'},{alg:'HS256',kid:'synthetic-key'},
    {alg:'RS256',kid:'synthetic-key',jku:'https://attacker.invalid/keys'},
    {alg:'RS256',kid:'synthetic-key',jwk:publicJwk},{alg:'RS256',kid:'synthetic-key',crit:['extra']},
    {alg:'RS256',kid:'synthetic-key',typ:'NOT_JWT'}]){
    const f=fixture();assert.equal((await f.worker.fetch(request(await token(claims(),header)))).status,403);assert.equal(f.loads(),0);
  }
});
test('unknown duplicate wrong-use private or malformed keys never authenticate',async()=>{
  const jwt=await token();for(const keys of [[],[{...publicJwk,kid:'other'}],[publicJwk,publicJwk],
    [{...publicJwk,use:'enc'}],[{...publicJwk,kty:'oct'}],[{...publicJwk,d:'not-a-real-private-key'}],
    [{...publicJwk,n:'bad'}],[{...publicJwk,key_ops:['sign','verify']}],[{...publicJwk,alg:'RS512'}]])
    assert.equal((await fixture({keys}).worker.fetch(request(jwt))).status,403);
});
test('loader failure and expired-during-key-loading return a fixed denial',async()=>{
  const jwt=await token();const r=await fixture({fail:true}).worker.fetch(request(jwt));
  assert.equal(r.status,403);assert.equal((await r.text()).includes('PRIVATE'),false);
  let time=NOW;const f=fixture({clock:()=>time,loader:async()=>{time+=900000;return {keys:[publicJwk]};}});
  assert.equal((await f.worker.fetch(request(jwt))).status,403);
});
test('alternate hostname HTTP port and spoofed forwarding cannot reach key loading',async()=>{
  const jwt=await token();for(const address of ['https://other.example.invalid/auth-check','http://'+config().hostname+'/auth-check',
    'https://'+config().hostname+':8443/auth-check','https://candidate.workers.dev/auth-check']){
    const f=fixture();const r=await f.worker.fetch(new Request(address,{headers:{'cf-access-jwt-assertion':jwt,
      'x-forwarded-host':config().hostname,host:config().hostname}}));assert.equal(r.status,403);assert.equal(f.loads(),0);
  }
  assert.equal((await fixture().worker.fetch(request(jwt,'/auth-check',{headers:{host:'other.invalid'}}))).status,403);
});
test('write methods execution routes and query-string commands have no handlers',async()=>{
  const jwt=await token();for(const method of ['POST','PUT','PATCH','DELETE','OPTIONS','HEAD']){
    const f=fixture(),r=await f.worker.fetch(request(jwt,'/auth-check',{method}));assert.equal(r.status,405);assert.equal(f.loads(),0);
  }
  for(const path of ['/execute','/operations/two-route/execute','/confirm','/receipts','/go/itm_synthetic']){
    const f=fixture();assert.equal((await f.worker.fetch(request(jwt,path))).status,404);assert.equal(f.loads(),0);
  }
  const f=fixture();assert.equal((await f.worker.fetch(request(jwt,'/auth-check?execute=true'))).status,400);assert.equal(f.loads(),0);
});
test('all response classes disable caching framing indexing and cross-origin access',async()=>{
  const jwt=await token();for(const req of [request(jwt),request(null),request(jwt,'/absent'),request(jwt,'/',{method:'POST'})]){
    const r=await fixture().worker.fetch(req);assert.equal(r.headers.get('cache-control'),'no-store');
    assert.equal(r.headers.get('x-frame-options'),'DENY');assert.equal(r.headers.get('x-content-type-options'),'nosniff');
    assert.equal(r.headers.get('x-robots-tag'),'noindex, nofollow, noarchive');
    assert.equal(r.headers.get('access-control-allow-origin'),null);assert.equal(r.headers.get('set-cookie'),null);
    assert.ok(r.headers.get('content-security-policy').includes("default-src 'none'"));
  }
});
test('invalid config missing injection production mode or mutable external config cannot open access',async()=>{
  const jwt=await token();for(const change of [{mode:'PRODUCTION'},{audience:''},{issuer:'https://attacker.invalid'},
    {hostname:'datalabx.jp'},{ownerEmail:''},{extra:'forbidden'}]){
    const f=fixture({config:{...config(),...change}});assert.equal((await f.worker.fetch(request(jwt))).status,403);assert.equal(f.loads(),0);
  }
  assert.equal((await createAuthOnlyLocalWorker().fetch(request(jwt))).status,403);
  const value=config(),f=fixture({config:value});value.ownerEmail='other@example.invalid';
  assert.equal((await f.worker.fetch(request(jwt))).status,200);
});
test('malformed huge or noncanonical tokens fail safely',async()=>{
  for(const jwt of ['malformed','a.b.c','.'.repeat(10),'a'.repeat(17000),'a.a.a',encoded([])+'.a.a']){
    const f=fixture();assert.equal((await f.worker.fetch(request(jwt))).status,403);assert.equal(f.loads(),0);
  }
});
test('invalid clock and loader output are fail-closed',async()=>{
  const jwt=await token();for(const clock of [()=>NaN,()=>Infinity,()=>-1,()=>{throw Error('PRIVATE_CLOCK');}])
    assert.equal((await fixture({clock}).worker.fetch(request(jwt))).status,403);
  for(const returned of [null,{}, {keys:'bad'}, {keys:Array(17).fill(publicJwk)}])
    assert.equal((await fixture({loader:async()=>returned}).worker.fetch(request(jwt))).status,403);
});
test('candidate only imports jose and has no executor env default handler or network transport',()=>{
  const source=readFileSync(new URL('./admin-auth-only-jose-local-worker.mjs',import.meta.url),'utf8');
  assert.deepEqual(source.match(/^import .*$/gmu),["import {validAccessIdentityConfig,verifyAccessAssertion} from './access-assertion-verifier.mjs';"]);assert.equal(/export\s+default/u.test(source),false);
  const core=readFileSync(new URL('./access-assertion-verifier.mjs',import.meta.url),'utf8');
  assert.deepEqual(core.match(/^import .*$/gmu),["import {jwtVerify,createLocalJWKSet} from 'jose';"]);
  assert.equal(/export\s+default|globalThis\.fetch|console\./u.test(core),false);
  assert.equal(/globalThis\.fetch|\bfetch\s*\(/u.test(source.replace('async fetch(request)','async handler(request)')),false);
  assert.equal(/\.env\b|\benv\s*[,.=)]/u.test(source),false);
});
test('unresponsive key loader times out and its signal is cancelled',async()=>{
  let observedSignal;
  const f=fixture({timeoutMs:20,loader:async(_url,{signal})=>{
    observedSignal=signal;return new Promise(()=>{});
  }});
  const r=await f.worker.fetch(request(await token()));
  assert.equal(r.status,403);assert.equal(f.loads(),1);assert.equal(observedSignal.aborted,true);
  assert.deepEqual(await r.json(),{status:'DENIED',production_ready:false});
});
test('a key response arriving after timeout cannot retroactively grant access',async()=>{
  let finish;
  const f=fixture({timeoutMs:20,loader:()=>new Promise(resolve=>{finish=resolve;})});
  const r=await f.worker.fetch(request(await token()));assert.equal(r.status,403);
  finish({keys:[publicJwk]});await Promise.resolve();
  assert.equal(r.status,403);assert.equal(f.loads(),1);
});
test('invalid key-load timeout fails closed before loader invocation',async()=>{
  const jwt=await token();for(const timeoutMs of [0,-1,5001,NaN,Infinity,1.5,'20']){
    const f=fixture({timeoutMs});assert.equal((await f.worker.fetch(request(jwt))).status,403);assert.equal(f.loads(),0);
  }
});
test('key selection handles rotation without accepting unknown or duplicated IDs',async()=>{
  const rotated={...await crypto.subtle.exportKey('jwk',other.publicKey),kid:'synthetic-rotated-key',alg:'RS256',use:'sig'};
  const jwt=await token(claims(),{alg:'RS256',typ:'JWT',kid:rotated.kid},other.privateKey);
  assert.equal((await fixture({keys:[publicJwk,rotated]}).worker.fetch(request(jwt))).status,200);
  assert.equal((await fixture({keys:[publicJwk]}).worker.fetch(request(jwt))).status,403);
  assert.equal((await fixture({keys:[publicJwk,rotated,rotated]}).worker.fetch(request(jwt))).status,403);
});
test('timing boundary is exact and malformed or missing claims cannot default open',async()=>{
  const valid=await token();assert.equal((await fixture({clock:()=>NOW+899999}).worker.fetch(request(valid))).status,200);
  assert.equal((await fixture({clock:()=>NOW+900000}).worker.fetch(request(valid))).status,403);
  for(const field of ['iss','aud','email','sub','type','iat','exp','nbf']){
    const payload=claims();delete payload[field];
    assert.equal((await fixture().worker.fetch(request(await token(payload)))).status,403);
  }
});
test('concurrent independent read-only checks do not create any execution endpoint',async()=>{
  const jwt=await token(),f=fixture();
  const responses=await Promise.all(Array.from({length:4},()=>f.worker.fetch(request(jwt))));
  assert.equal(responses.every(r=>r.status===200),true);assert.equal(f.loads(),4);
  assert.equal((await f.worker.fetch(request(jwt,'/execute',{method:'POST'}))).status,405);
  assert.equal(f.loads(),4);
});

test('optional header omission remains supported without accepting wrong header type',async()=>{
  const valid=await token(claims(),{alg:'RS256',kid:'synthetic-key'});
  assert.equal((await fixture().worker.fetch(request(valid))).status,200);
  assert.equal((await fixture().worker.fetch(request(await token(claims(),{alg:'RS256',kid:'synthetic-key',typ:42})))).status,403);
});
test('single-audience profile stays stricter than general JWT audience matching',async()=>{
  const jwt=await token({...claims(),aud:[config().audience,'another-app']});
  const f=fixture();assert.equal((await f.worker.fetch(request(jwt))).status,403);assert.equal(f.loads(),0);
});
test('lifetime and future-issued checks are preserved beyond library defaults',async()=>{
  for(const changes of [{iat:seconds-1,exp:seconds+900},{iat:seconds+1},{nbf:seconds+1}]){
    const f=fixture();assert.equal((await f.worker.fetch(request(await token({...claims(),...changes})))).status,403);
    assert.equal(f.loads(),0);
  }
});
test('input limits apply before injected JWKS loader',async()=>{
  const f=fixture();assert.equal((await f.worker.fetch(request('x'.repeat(16385)))).status,403);
  assert.equal(f.loads(),0);
});
