import {jwtVerify,createLocalJWKSet} from 'jose';
// Pure verification: explicit trusted identity and injected public-key loader only.
const B64=/^[A-Za-z0-9_-]+$/u;
const object=value=>value!==null && typeof value==='object' && !Array.isArray(value);
function decode(segment) {
  if(typeof segment!=='string' || !B64.test(segment) || segment.length%4===1)throw Error();
  const binary=atob(segment.replace(/-/gu,'+').replace(/_/gu,'/')+'='.repeat((4-segment.length%4)%4));
  const bytes=Uint8Array.from(binary,x=>x.charCodeAt(0));
  // Require canonical base64url; unused bits must not create alternate tokens.
  if(btoa(binary).replace(/=/gu,'').replace(/\+/gu,'-').replace(/\//gu,'_')!==segment)throw Error();
  return bytes;
}
function json(segment) {
  const value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(decode(segment)));
  if(!object(value))throw Error();return value;
}
export function validAccessIdentityConfig(config) {
  const keys=['issuer','audience','ownerEmail'];
  return object(config) && Object.keys(config).length===keys.length && keys.every(k=>Object.hasOwn(config,k)) &&
    typeof config.issuer==='string' &&
    /^https:\/\/[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.cloudflareaccess\.com$/u.test(config.issuer) &&
    typeof config.audience==='string' && /^[0-9a-f]{64}$/u.test(config.audience) &&
    typeof config.ownerEmail==='string' && config.ownerEmail.length<=254 &&
    /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/u.test(config.ownerEmail);
}
function validClaims(payload,config,now) {
  return payload.iss===config.issuer && payload.type==='app' &&
    Array.isArray(payload.aud) && payload.aud.length===1 && payload.aud[0]===config.audience &&
    payload.email===config.ownerEmail && typeof payload.sub==='string' && /^[A-Za-z0-9_-]{1,256}$/u.test(payload.sub) &&
    !Object.hasOwn(payload,'common_name') && !Object.hasOwn(payload,'service_token_id') &&
    [payload.iat,payload.exp,payload.nbf].every(Number.isSafeInteger) &&
    payload.iat>=0 && payload.nbf>=0 && payload.iat<=now && payload.nbf<=now &&
    payload.nbf<payload.exp && payload.exp>now && payload.exp>payload.iat && payload.exp-payload.iat<=900;
}
function nowSeconds(clock) {
  const value=clock();
  if(!Number.isSafeInteger(value) || value<0 || value>8640000000000000)throw Error();
  return Math.floor(value/1000);
}
async function boundedPublicKeys(loadJwks,url,timeoutMs) {
  const controller=new AbortController();let timer;
  try {
    return await Promise.race([
      Promise.resolve().then(()=>loadJwks(url,{signal:controller.signal})),
      new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error()),timeoutMs);})
    ]);
  } finally {clearTimeout(timer);controller.abort();}
}
async function verify(token,config,loadJwks,clock,keyLoadTimeoutMs) {
  if(typeof token!=='string' || token.length>16384)return false;
  const pieces=token.split('.');
  if(pieces.length!==3 || pieces[0].length>2048 || pieces[1].length>12000)return false;
  const header=json(pieces[0]),payload=json(pieces[1]),signature=decode(pieces[2]);
  if(header.alg!=='RS256' || (header.typ!==undefined && header.typ!=='JWT') ||
      typeof header.kid!=='string' || !/^[A-Za-z0-9_-]{1,128}$/u.test(header.kid) ||
      Object.keys(header).some(k=>!['alg','typ','kid'].includes(k)) ||
      signature.length<256 || signature.length>512 || !validClaims(payload,config,nowSeconds(clock)))return false;
  // Never derive an issuer/JWKS URL from token/header/request claims.
  const jwks=structuredClone(await boundedPublicKeys(loadJwks,config.issuer+'/cdn-cgi/access/certs',keyLoadTimeoutMs));
  if(!object(jwks) || !Array.isArray(jwks.keys) || jwks.keys.length<1 || jwks.keys.length>16)return false;
  const matches=jwks.keys.filter(k=>object(k) && k.kid===header.kid);
  if(matches.length!==1)return false;
  const key=matches[0];
  if(key.kty!=='RSA' || (key.alg!==undefined && key.alg!=='RS256') ||
      (key.use!==undefined && key.use!=='sig') || key.e!=='AQAB' ||
      typeof key.n!=='string' || decode(key.n).length<256 || decode(key.n).length>512 ||
      ['d','p','q','dp','dq','qi','oth'].some(k=>Object.hasOwn(key,k)) ||
      (key.key_ops!==undefined && (!Array.isArray(key.key_ops) || key.key_ops.length!==1 || key.key_ops[0]!=='verify')))return false;
  // The manual decode above is an untrusted-input prefilter only.
  // Authentication and claim validation are delegated to the pinned jose dependency.
  const resolver=createLocalJWKSet({keys:[{kty:'RSA',n:key.n,e:key.e,
    kid:header.kid,alg:'RS256',use:'sig'}]});
  const {payload:verifiedPayload}=await jwtVerify(token,resolver,{
    algorithms:['RS256'],issuer:config.issuer,audience:config.audience,
    requiredClaims:['iss','aud','email','sub','type','iat','exp','nbf'],
    maxTokenAge:900,clockTolerance:0,currentDate:new Date(clock())
  });
  return validClaims(verifiedPayload,config,nowSeconds(clock));
}

export async function verifyAccessAssertion(token,identity,loadJwks,clock,keyLoadTimeoutMs=1000) {
  try {
    if(!validAccessIdentityConfig(identity) || typeof loadJwks!=='function' || typeof clock!=='function' ||
       !Number.isSafeInteger(keyLoadTimeoutMs) || keyLoadTimeoutMs<1 || keyLoadTimeoutMs>5000)return false;
    const pinned=Object.freeze({...identity});
    return await verify(token,pinned,loadJwks,clock,keyLoadTimeoutMs);
  } catch { return false; }
}
