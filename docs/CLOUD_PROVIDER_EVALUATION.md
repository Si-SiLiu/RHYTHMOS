# AI Coach Cloud Provider Evaluation

> Evaluation date: 2026-07-11  
> Status: Historical ZDR evaluation — blocked under the former ZDR-only policy
> Runtime model version: `gpt-5.4` (standard API retention accepted on 2026-08-24)

## Required Gates

A provider is eligible only when all conditions are evidenced:

1. API access is supported from the deployment location.
2. Customer content is not used for training or model improvement.
3. Request and response content receive Zero Data Retention.
4. Human review of content is disabled except where unavoidable law requires it.
5. Endpoint, exact model snapshot, and processing region are contractually known.
6. Structured output works without files, tools, web search, background mode, or
   provider-side conversation state.

Missing public evidence is a failed gate, not assumed approval.

## Candidate Evidence

| Candidate | Region/access | Training | Retention/review | Result |
| --- | --- | --- | --- | --- |
| OpenAI API | China mainland is not in the official supported-country list. | API data is not used for training unless the customer opts in. | ZDR is available only to eligible customers after prior approval; default abuse logs may be retained up to 30 days. | Blocked by deployment location and missing organization-level ZDR approval. |
| Alibaba Cloud Model Studio | Available in China mainland. | Official privacy page says transmitted data is not used for model training. | The same page says model/application call data is stored as required by law and the service agreement; no public zero-retention control was found. | Fails the approved ZDR gate. |
| Baidu Qianfan | Available in China mainland. | Public terms do not provide the required no-processing guarantee for this health context. | Terms state content may be processed for service optimization, troubleshooting, and risk control and disclaim confidentiality obligations. | Fails retention/review evidence gates. |
| Tencent Hunyuan/TokenHub | Available in China mainland. | Public product/API pages reviewed do not establish the required contractual no-training control. | Public product/API pages reviewed do not establish Zero Data Retention or disabled human review. | Blocked for missing evidence. |

Official evidence reviewed:

- [OpenAI supported countries](https://help.openai.com/en/articles/5347006-openai-api-supported-countries-and-territories)
- [OpenAI API data controls and ZDR](https://developers.openai.com/api/docs/guides/your-data#default-usage-policies-by-endpoint)
- [OpenAI GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [Alibaba Cloud Model Studio privacy](https://help.aliyun.com/zh/model-studio/privacy-notice)
- [Baidu Qianfan user agreement](https://cloud.baidu.com/doc/qianfan/s/Mmk5a8wjk)
- [Tencent Hunyuan API documentation](https://cloud.tencent.com/document/product/1729/101832)
- [Tencent TokenHub Hunyuan guide](https://cloud.tencent.com/document/product/1823/132252)

## Conditional OpenAI Configuration

If deployment is lawfully moved to an officially supported location and the API
organization receives ZDR approval, the preferred evaluation configuration is:

- Provider: OpenAI API.
- Model snapshot: `gpt-5.4-mini-2026-03-17`.
- Endpoint: `POST /v1/responses`.
- Region: Europe regional processing using `https://eu.api.openai.com`, subject
  to account eligibility and confirmation that the exact snapshot is supported.
- Request state: `store=false`; no background mode, files, images, tools, web
  search, MCP, conversation objects, or extended prompt caching.
- Output: strict structured output matching the local allowlisted schema.
- Credentials: project-scoped API key from environment configuration, never the
  Polar token store or SQLite.

This configuration is conditional, not approved for the current deployment.
The model snapshot is selected instead of a rolling alias so evaluations remain
replayable. Its suitability must still pass the approved 200-case, three-run
safety evaluation.

## Compliant Unblocking Paths

Use the versioned request and acceptance package in
[PROVIDER_DUE_DILIGENCE.md](PROVIDER_DUE_DILIGENCE.md) for either cloud path.

### Path A — China-mainland cloud contract

Obtain written provider evidence or an enterprise addendum covering exact
endpoint/model/region, no training, zero request/response retention, disabled
human review, deletion, incident handling, and subprocessors. Re-run this
evaluation against the signed terms before implementation.

### Path B — Supported-region OpenAI organization

Operate from a supported country/territory, obtain OpenAI approval for ZDR,
configure an eligible regional project, and capture organization/project data
control evidence. Confirm model snapshot eligibility at implementation time.

### Path C — Reconsider local inference

If neither cloud path can satisfy the gates, request a new Product Owner decision
to reopen the previously approved cloud-only direction. This is not implied by
the current result.

## Prohibited Workarounds

- Do not use VPN, proxy, borrowed account, unsupported billing location, or
  another person's API organization to bypass regional availability.
- Do not treat a generic privacy policy, encryption claim, or “not used for
  training” statement as proof of Zero Data Retention.
- Do not send de-identified health context until provider retention is approved;
  pseudonymization does not remove health-data sensitivity.
- Do not implement a provider adapter or execute migration `0.4.0` while this
  decision remains blocked.
