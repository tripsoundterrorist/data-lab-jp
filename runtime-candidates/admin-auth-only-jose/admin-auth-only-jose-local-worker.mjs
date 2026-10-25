import {validAccessIdentityConfig,verifyAccessAssertion} from './access-assertion-verifier.mjs';
// LOCAL_ONLY boundary remains independent of the authentication-only runtime candidate.
const HOST='revalidation-admin.datalabx.jp';
const object=value=>value!==null && typeof value==='object' && !Array.isArray(value);
function validConfig(config) {
  const keys=['mode','hostname','issuer','audience','ownerEmail'];
  return object(config) && Object.keys(config).length===keys.length && keys.every(k=>Object.hasOwn(config,k)) &&
    config.mode==='LOCAL_ONLY' && config.hostname===HOST &&
    validAccessIdentityConfig({issuer:config.issuer,audience:config.audience,ownerEmail:config.ownerEmail});
}
function response(status,body) {
  return new Response(JSON.stringify({status:body,production_ready:false}),{status,headers:{
    'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',
    'Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    'X-Frame-Options':'DENY','X-Content-Type-Options':'nosniff',
    'X-Robots-Tag':'noindex, nofollow, noarchive',...(status===405?{Allow:'GET'}:{})}});
}
export function createAuthOnlyLocalWorker({config,loadJwks,clock,keyLoadTimeoutMs=1000}={}) {
  // Invalid/missing configuration always produces a closed handler, not defaults.
  const ready=validConfig(config) && typeof loadJwks==='function' && typeof clock==='function' &&
    Number.isSafeInteger(keyLoadTimeoutMs) && keyLoadTimeoutMs>=1 && keyLoadTimeoutMs<=5000;
  const pinned=ready?Object.freeze({...config}):null;
  const identity=ready?Object.freeze({issuer:pinned.issuer,audience:pinned.audience,ownerEmail:pinned.ownerEmail}):null;
  return Object.freeze({local_only:true,production_ready:false,
    async fetch(request) {
      try {
        if(!ready || !(request instanceof Request))return response(403,'DENIED');
        const url=new URL(request.url),hostHeader=request.headers.get('host');
        if(url.protocol!=='https:' || url.hostname!==pinned.hostname || url.port || url.username || url.password ||
            (hostHeader!==null && hostHeader!==pinned.hostname))return response(403,'DENIED');
        if(request.method!=='GET')return response(405,'METHOD_NOT_ALLOWED');
        if(!['/','/auth-check'].includes(url.pathname))return response(404,'NOT_FOUND');
        if(url.search)return response(400,'INVALID_REQUEST');
        const token=request.headers.get('cf-access-jwt-assertion');
        if(!await verifyAccessAssertion(token,identity,loadJwks,clock,keyLoadTimeoutMs))return response(403,'DENIED');
        return response(200,'AUTHENTICATED_EXECUTION_DISABLED');
      } catch { return response(403,'DENIED'); }
    }});
}
