// OFFLINE ENTRY BOUNDARY ONLY. No default export, deployment config, or live fetch.
// Reuse the existing cryptographic verifier; never translate LOCAL_ONLY into LIVE.
import {createAuthOnlyTransportCandidate} from './admin-auth-only-key-transport-local.mjs';

const HOST='revalidation-admin.datalabx.jp';
function deny(status,reason){
  return new Response(JSON.stringify({status:reason,production_ready:false}),{status,headers:{
    'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store',
    'Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    'X-Frame-Options':'DENY','X-Content-Type-Options':'nosniff',
    'X-Robots-Tag':'noindex, nofollow, noarchive',...(status===405?{Allow:'GET'}:{})
  }});
}

export function createLocalAuthCheckEntry(options={}){
  let verifier=null;
  try{
    if(options!==null && typeof options==='object' && !Array.isArray(options) &&
       Object.keys(options).every(key=>['config','fetchPublicKeys','clock'].includes(key))){
      verifier=createAuthOnlyTransportCandidate(options);
    }
  }catch{/* Missing or invalid injection must leave a closed entry. */}
  return Object.freeze({local_only:true,production_ready:false,
    async fetch(request){
      try{
        if(!verifier || !(request instanceof Request))return deny(403,'DENIED');
        const url=new URL(request.url);
        if(url.protocol!=='https:' || url.hostname!==HOST || url.port || url.username || url.password)
          return deny(403,'DENIED');
        if(request.method!=='GET')return deny(405,'METHOD_NOT_ALLOWED');
        if(url.pathname!=='/auth-check')return deny(404,'NOT_FOUND');
        if(url.search)return deny(400,'INVALID_REQUEST');
        return await verifier.fetch(request);
      }catch{return deny(403,'DENIED');}
    }
  });
}
