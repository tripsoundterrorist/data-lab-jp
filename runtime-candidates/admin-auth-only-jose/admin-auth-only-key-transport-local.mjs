// LOCAL CANDIDATE ONLY: injected fetch/clock; no live network, default export or bindings.
import {createAuthOnlyLocalWorker} from './admin-auth-only-jose-local-worker.mjs';
const record=x=>x!==null && typeof x==='object' && !Array.isArray(x);
const failure=()=>new Error('PUBLIC_KEY_UNAVAILABLE');
const issuerPattern=/^https:\/\/[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.cloudflareaccess\.com$/u;
const safeInteger=(n,min,max)=>Number.isSafeInteger(n)&&n>=min&&n<=max;
function publicKeys(value){
  if(!record(value)||!Array.isArray(value.keys)||value.keys.length<1||value.keys.length>16)throw failure();
  const seen=new Set();
  const keys=value.keys.map(key=>{
    if(!record(key)||key.kty!=='RSA'||typeof key.kid!=='string'||!/^[A-Za-z0-9_-]{1,128}$/u.test(key.kid)||
      seen.has(key.kid)||key.e!=='AQAB'||typeof key.n!=='string'||!/^[A-Za-z0-9_-]+$/u.test(key.n)||
      key.n.length>683||key.n.length%4===1||
      (key.alg!==undefined&&key.alg!=='RS256')||(key.use!==undefined&&key.use!=='sig')||
      ['d','p','q','dp','dq','qi','oth'].some(k=>Object.hasOwn(key,k))||
      (key.key_ops!==undefined&&(!Array.isArray(key.key_ops)||key.key_ops.length!==1||key.key_ops[0]!=='verify')))throw failure();
    const binary=atob(key.n.replace(/-/gu,'+').replace(/_/gu,'/')+'='.repeat((4-key.n.length%4)%4));
    if(binary.length<256||binary.length>512||
      btoa(binary).replace(/=/gu,'').replace(/\+/gu,'-').replace(/\//gu,'_')!==key.n)throw failure();
    seen.add(key.kid);
    // Retain public verification fields only; drop PEM/certs and unknown response metadata.
    return {kty:'RSA',kid:key.kid,n:key.n,e:'AQAB',alg:'RS256',use:'sig'};
  });
  return {keys};
}
function cancel(reader){if(reader)Promise.resolve(reader.cancel()).catch(()=>{});}
async function fetchAndRead(endpoint,fetchPublicKeys,signal,maxBytes){
  const response=await fetchPublicKeys(endpoint,{method:'GET',headers:{Accept:'application/json'},
    redirect:'error',credentials:'omit',referrerPolicy:'no-referrer',cache:'no-store',signal});
  if(!(response instanceof Response))throw failure();
  if(signal.aborted){cancel(response.body?.getReader());throw failure();}
  let reader;
  try{
    if(response.status!==200||response.redirected||
      (response.url!==''&&response.url!==endpoint)||
      response.headers.get('content-type')?.split(';')[0].trim().toLowerCase()!=='application/json')throw failure();
    const length=response.headers.get('content-length');
    if(length!==null&&(!/^\d+$/u.test(length)||!safeInteger(Number(length),0,maxBytes)))throw failure();
    if(!response.body)throw failure();
    reader=response.body.getReader();
    const onAbort=()=>cancel(reader);
    signal.addEventListener('abort',onAbort,{once:true});
    try{
      let bytes=0;const chunks=[];
      while(true){
        if(signal.aborted)throw failure();
        const {value,done}=await reader.read();
        if(done)break;
        if(!(value instanceof Uint8Array))throw failure();
        bytes+=value.byteLength;
        if(bytes>maxBytes)throw failure();
        chunks.push(value);
      }
      if(signal.aborted)throw failure();
      const all=new Uint8Array(bytes);let offset=0;
      for(const chunk of chunks){all.set(chunk,offset);offset+=chunk.byteLength;}
      return publicKeys(JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(all)));
    }finally{signal.removeEventListener('abort',onAbort);}
  }finally{cancel(reader||(!response.bodyUsed?response.body?.getReader():null));}
}
export function createBoundedPublicJwksLoader({mode,issuer,fetchPublicKeys,clock,
  timeoutMs=800,maxBytes=65536,cacheMs=60000,cooldownMs=30000}={}){
  const ready=mode==='LOCAL_ONLY'&&typeof issuer==='string'&&issuerPattern.test(issuer)&&
    typeof fetchPublicKeys==='function'&&typeof clock==='function'&&
    safeInteger(timeoutMs,1,800)&&safeInteger(maxBytes,1,65536)&&
    safeInteger(cacheMs,1,300000)&&safeInteger(cooldownMs,1,60000);
  const endpoint=ready?issuer+'/cdn-cgi/access/certs':null;
  let cached=null,pending=null,nextFetchAt=0,lastClock=-1;
  function now(){
    const time=clock();
    if(!safeInteger(time,0,8640000000000000)||time<lastClock){cached=null;throw failure();}
    lastClock=time;return time;
  }
  function begin(time){
    const controller=new AbortController();
    const job={controller,waiters:0,settled:false,promise:null};
    nextFetchAt=time+cooldownMs;
    pending=job;
    job.promise=(async()=>{
      let rejectAbort;
      const aborted=new Promise((_,reject)=>{rejectAbort=()=>reject(failure());controller.signal.addEventListener('abort',rejectAbort,{once:true});});
      const timer=setTimeout(()=>controller.abort(),timeoutMs);
      try{
        const value=await Promise.race([fetchAndRead(endpoint,fetchPublicKeys,controller.signal,maxBytes),aborted]);
        if(controller.signal.aborted)throw failure();
        const completed=now();
        cached={value,until:completed+cacheMs};
        return value;
      }finally{
        job.settled=true;clearTimeout(timer);
        controller.signal.removeEventListener('abort',rejectAbort);
        controller.abort();
        if(pending===job)pending=null;
      }
    })();
    return job;
  }
  function subscribe(job,signal){
    job.waiters++;
    return new Promise((resolve,reject)=>{
      let finished=false;
      const finish=(error,value)=>{
        if(finished)return;finished=true;
        signal.removeEventListener('abort',onAbort);job.waiters--;
        if(job.waiters===0&&!job.settled)job.controller.abort();
        if(error)reject(failure());else resolve(structuredClone(value));
      };
      const onAbort=()=>finish(failure());
      signal.addEventListener('abort',onAbort,{once:true});
      job.promise.then(value=>finish(null,value),()=>finish(failure()));
      if(signal.aborted)onAbort();
    });
  }
  return async function loadJwks(url,{signal}={}){
    if(!ready||url!==endpoint||!(signal instanceof AbortSignal)||signal.aborted)throw failure();
    const time=now();
    if(cached&&time<cached.until)return structuredClone(cached.value);
    // Never fall back to expired keys, even when refresh fails or is rate-limited.
    cached=null;
    if(pending)return subscribe(pending,signal);
    if(time<nextFetchAt)throw failure();
    return subscribe(begin(time),signal);
  };
}
export function createAuthOnlyTransportCandidate({config,fetchPublicKeys,clock,transport={}}={}){
  let pinned;
  try{pinned=structuredClone(config);}catch{pinned=null;}
  const loadJwks=createBoundedPublicJwksLoader({...transport,mode:pinned?.mode,
    issuer:pinned?.issuer,fetchPublicKeys,clock});
  return createAuthOnlyLocalWorker({config:pinned,clock,loadJwks,keyLoadTimeoutMs:1000});
}
