// LOCAL_ONLY composition. Never supplies ambient network transport or a Worker entrypoint.
import {createAuthOnlyLocalWorker} from './admin-auth-only-jose-local-worker.mjs';
import {createBoundedPublicKeyLoader} from './access-public-key-loader.mjs';
export function createBoundedPublicJwksLoader(options={}) {
  if(options===null || typeof options!=='object' || Array.isArray(options) || options.mode!=='LOCAL_ONLY')
    return async()=>{throw Error('PUBLIC_KEY_UNAVAILABLE');};
  const {mode,...settings}=options;
  return createBoundedPublicKeyLoader(settings);
}
export function createAuthOnlyTransportCandidate({config,fetchPublicKeys,clock,transport={}}={}){
  let pinned;
  try{pinned=structuredClone(config);}catch{pinned=null;}
  const loadJwks=createBoundedPublicJwksLoader({...transport,mode:pinned?.mode,
    issuer:pinned?.issuer,fetchPublicKeys,clock});
  return createAuthOnlyLocalWorker({config:pinned,clock,loadJwks,keyLoadTimeoutMs:1000});
}
