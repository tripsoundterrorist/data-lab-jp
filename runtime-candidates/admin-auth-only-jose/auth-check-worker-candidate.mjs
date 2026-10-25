// AUTHENTICATION-ONLY WORKER CANDIDATE. No route/deployment configuration is provided.
// Default disabled. This module does not fetch at import or inspect cookie credentials.
import {validAccessIdentityConfig,verifyAccessAssertion} from './access-assertion-verifier.mjs';
import {createBoundedPublicKeyLoader} from './access-public-key-loader.mjs';
const HOST='revalidation-admin.datalabx.jp';
const ENV_KEYS=['AUTH_CHECK_ENABLED','AUTH_CHECK_SCOPE','ACCESS_ISSUER','ACCESS_AUDIENCE','ACCESS_OWNER_EMAIL'];
function identityFromEnv(env) {
  if(env===null || typeof env!=='object' || Array.isArray(env) ||
     Object.keys(env).length!==ENV_KEYS.length || !ENV_KEYS.every(k=>Object.hasOwn(env,k)) ||
     env.AUTH_CHECK_ENABLED!=='true' || env.AUTH_CHECK_SCOPE!=='AUTHENTICATION_ONLY')return null;
  const identity={issuer:env.ACCESS_ISSUER,audience:env.ACCESS_AUDIENCE,ownerEmail:env.ACCESS_OWNER_EMAIL};
  return validAccessIdentityConfig(identity)?Object.freeze(identity):null;
}
function response(status,value) {
  return new Response(JSON.stringify({status:value,production_ready:false}),{status,headers:{
    'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',
    'Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    'X-Frame-Options':'DENY','X-Content-Type-Options':'nosniff',
    'X-Robots-Tag':'noindex, nofollow, noarchive',...(status===405?{Allow:'GET'}:{})
  }});
}
export function createAuthCheckWorkerCandidate({fetchPublicKeys,clock}={}) {
  let cached=null;
  const ready=typeof fetchPublicKeys==='function' && typeof clock==='function';
  return Object.freeze({auth_only:true,production_ready:false,
    async fetch(request,env) {
      try {
        const identity=ready?identityFromEnv(env):null;
        if(!identity || !(request instanceof Request)){cached=null;return response(403,'DENIED');}
        const url=new URL(request.url),host=request.headers.get('host');
        if(url.protocol!=='https:' || url.hostname!==HOST || url.port || url.username || url.password ||
           (host!==null && host!==HOST))return response(403,'DENIED');
        if(request.method!=='GET')return response(405,'METHOD_NOT_ALLOWED');
        if(url.pathname!=='/auth-check')return response(404,'NOT_FOUND');
        if(url.search)return response(400,'INVALID_REQUEST');
        const configKey=JSON.stringify(identity);
        if(!cached || cached.configKey!==configKey) {
          cached={configKey,load:createBoundedPublicKeyLoader({issuer:identity.issuer,fetchPublicKeys,clock})};
        }
        if(!await verifyAccessAssertion(request.headers.get('cf-access-jwt-assertion'),identity,cached.load,clock))
          return response(403,'DENIED');
        return response(200,'AUTHENTICATED_EXECUTION_DISABLED');
      } catch {cached=null;return response(403,'DENIED');}
    }
  });
}
// Standard Worker interface, but inert until all explicit authentication-only settings exist.
// Real network and deployment tests are NOT authorized by this local implementation.
export default createAuthCheckWorkerCandidate({
  fetchPublicKeys:(url,init)=>globalThis.fetch(url,init),
  clock:()=>Date.now()
});
