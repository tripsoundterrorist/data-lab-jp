import { handleAffiliatePagesCandidate } from "../../../runtime-candidates/affiliate-pages-entrypoint-candidate.mjs";

// Every release fact remains closed in the inert deployment candidate. A later
// reviewed activation change must replace this object and add an explicit route.
const RELEASE_FACTS = Object.freeze({
  officialAnswerCandidate: false,
  publicationGateEligible: false,
  runtimeChainConnected: false,
  rateLimitAllowed: false,
  prDisclosureAvailable: false,
});

export default {
  async fetch(request, env) {
    return handleAffiliatePagesCandidate({ request, env }, RELEASE_FACTS);
  },
};
