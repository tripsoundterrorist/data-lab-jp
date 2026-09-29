import { handleAffiliatePagesCandidate } from "../../../runtime-candidates/affiliate-pages-entrypoint-candidate.mjs";

// This scope is intentionally narrower than a global Publication Gate unlock.
// D1 remains the final exact-one-row-per-request runtime eligibility boundary.
export const ACTIVATION_SCOPE = Object.freeze({
  candidateSha256: "364b74f359abbdbf1675ff030818b6e140c7a5a9c37d36df67503612ad102137",
  artifactSha256: "364b74f359abbdbf1675ff030818b6e140c7a5a9c37d36df67503612ad102137",
  sourceSha256: "564bbeaf628de624e816ff8f2b4a3824119e338d3052e8d2594a084f06ef2e85",
  publicSurface: "/items/",
  routePrefix: "/go/",
  maximumCtaCount: 4,
  itemCount: 100,
  relayOperationGuaranteed: false,
  affiliateOutcomeGuaranteed: false,
});

export const RELEASE_FACTS = Object.freeze({
  officialAnswerCandidate: true,
  publicationGateEligible: true,
  runtimeChainConnected: true,
  rateLimitAllowed: true,
  prDisclosureAvailable: true,
});

export default {
  async fetch(request, env) {
    return handleAffiliatePagesCandidate({ request, env }, RELEASE_FACTS);
  },
};
