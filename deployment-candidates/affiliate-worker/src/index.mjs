import { handleAffiliatePagesCandidate } from "../../../runtime-candidates/affiliate-pages-entrypoint-candidate.mjs";

// This scope is intentionally narrower than a global Publication Gate unlock.
// D1 remains the final exact-one-row runtime eligibility boundary.
export const ACTIVATION_SCOPE = Object.freeze({
  candidateSha256: "62ad8f93cc91769b5c92854bc4ff2ccb6bb4e939d8791a8b36245d4c93878374",
  artifactSha256: "10aafd067419cfec813ed9614db33407833fc577fb44365bc55080df354095b9",
  sourceSha256: "564bbeaf628de624e816ff8f2b4a3824119e338d3052e8d2594a084f06ef2e85",
  publicSurface: "/items/",
  routePrefix: "/go/",
  maximumCtaCount: 1,
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
