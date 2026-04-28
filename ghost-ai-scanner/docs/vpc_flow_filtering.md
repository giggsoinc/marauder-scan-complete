# PatronAI — VPC Flow Log ENI Filtering

**Version:** 1.0.0  
**Updated:** 2026-04-19  
**Owner:** Giggso Inc  
**Status:** Implemented — Phase 1  
**Merge target:** patronai-spec.docx § Cloud Layer

---

## Problem

VPC Flow Logs capture traffic for **every ENI in the VPC** — including AWS-managed infrastructure ENIs that will never produce AI signals. In a typical enterprise VPC with EFS, NAT Gateways, VPC Endpoints, ALBs and Lambda functions, 30–60% of flow log volume is pure noise.

Confirmed example from customer environment:
- `eni-01e3b69272285a061` — EFS mount target for `fs-0aa9f0a411ce090be`
- `RequesterManaged=True`, `RequesterId=641247547298`
- 100% of rows: `log-status=NODATA`
- Cost: S3 GET + scanner CPU on every 5-minute scan cycle

---

## Solution

A 5-type ENI denylist applied **before normalisation** in `src/normalizer/flow_log.py`. Each flow log row costs one dict lookup against a cached metadata map. Denied rows return `None` at the earliest possible point — no parsing, no schema allocation, no matcher call.

---

## The 5 Denylist Rules

### Rule 1 — EFS Mount Targets

| Match field | Value |
|---|---|
| `Description` prefix | `"EFS mount target"` |
| `RequesterId` | `641247547298` (AWS EFS service account) |
| `reason` label | `efs` |

EFS mount targets are AWS-managed storage endpoints. All flow log rows are `NODATA` — no real traffic crosses them at the network layer visible to flow logs. Both match conditions are checked (either is sufficient) to handle edge cases where AWS changes the description format.

### Rule 2 — NAT Gateways

| Match field | Value |
|---|---|
| `InterfaceType` | `nat_gateway` |
| `reason` label | `nat` |

NAT Gateway ENIs appear as the source in flow logs for all traffic that exits private subnets. PatronAI matches on destination domain — by the time traffic reaches the NAT ENI, the originating EC2 identity is already lost. Filtering NAT ENIs removes noise without losing any attributable events.

### Rule 3 — VPC Endpoints

| Match field | Value |
|---|---|
| `InterfaceType` | `vpc_endpoint` |
| `reason` label | `vpce` |

VPC Endpoints carry AWS PrivateLink traffic that stays within the AWS backbone (S3, ECR, SSM, STS etc). These destinations are never external AI providers. VPC Endpoint flow volume is typically 15–25% of total VPC traffic in AWS-native environments.

### Rule 4 — Load Balancers

| Match field | Value |
|---|---|
| `Description` prefix | `"ELB "` |
| `reason` label | `elb` |

Application and Network Load Balancer ENIs handle inbound traffic distribution. The actual client is the originating device — the ELB ENI is the forwarding hop. PatronAI needs the originating `src_ip` for identity resolution, not the load balancer hop.

### Rule 5 — Lambda Idle ENIs

| Match field | Value |
|---|---|
| `Description` prefix | `"AWS Lambda VPC ENI"` |
| `reason` label | `lambda` |

Lambda VPC ENIs are created by AWS when a Lambda function is attached to a VPC. When the function is idle they emit continuous `NODATA` flow records. Active Lambda invocations are server-side code — outbound AI provider calls from Lambda are a separate detection surface handled by the code analyser, not the network normaliser.

---

## Keep Rule

After all deny rules pass, ENIs are accepted only if:
- `RequesterManaged=False` (customer-owned, not AWS-managed)
- `OwnerId` matches the customer AWS account ID (`AWS_ACCOUNT_ID` env var)

Any ENI where the metadata cache has no entry (cache miss) is **failed open** — the flow is passed through to normalisation. This ensures we never silently drop events from new ENIs that haven't been catalogued yet.

---

## Implementation Files

| File | Purpose |
|---|---|
| `config/eni_denylist.yaml` | 5 rule definitions — edit here to add new ENI types |
| `src/normalizer/eni_filter.py` | `load_eni_patterns()`, `is_denied_eni()`, `enrich_with_metadata()`, cache management |
| `src/normalizer/flow_log.py` | Filter called at top of `parse_vpc()` before any other work |
| `scripts/refresh_eni_cache.py` | Standalone script — fetches all ENI metadata, writes to S3 |
| `tests/unit/test_eni_filter.py` | 8 unit tests — all 5 deny rules + keep case + cache-miss fail-open |

---

## ENI Metadata Cache

**Location:** `s3://{MARAUDER_SCAN_BUCKET}/cache/eni_metadata.json`

**Format:**
```json
{
  "_meta": {
    "fetched_at": "2026-04-19T14:00:00Z",
    "account_id": "324037322652",
    "eni_count": 47,
    "region": "us-east-1"
  },
  "enis": {
    "eni-01e3b69272285a061": {
      "Description": "EFS mount target for fs-0aa9f0a411ce090be",
      "InterfaceType": "interface",
      "RequesterManaged": true,
      "RequesterId": "641247547298",
      "OwnerId": "324037322652",
      "Status": "in-use"
    }
  }
}
```

**Refresh cadence:** Every 6 hours — checked inline by `eni_filter.cache_is_stale()` on every `parse_vpc()` call. No new thread or cron job required.

**Manual refresh:**
```bash
MARAUDER_SCAN_BUCKET=marauder-scan-giggso python3 scripts/refresh_eni_cache.py
```

---

## Observability

Filter counts are accumulated in `eni_filter.eni_filtered_total` (a `collections.Counter`) and logged every 1,000 rows processed:

```
eni_filtered_total: {'efs': 342, 'nat': 1204, 'vpce': 891, 'elb': 67, 'lambda': 23}
```

Counter keys match Prometheus label convention (`eni_filtered_total{reason="efs"}`). Swap `collections.Counter` for `prometheus_client.Counter` when that dependency is added — the naming is pre-aligned.

---

## Phase 2 Considerations

- **File-level skipping**: VPC Flow Log filenames in S3 include the ENI ID. The S3 walker (`src/ingestor/s3_walker.py`) could skip entire files for known-denied ENIs before downloading. Reduces S3 GET cost further (Phase 1 only eliminates CPU cost after the GET).
- **New ENI types**: Add a new row to `config/eni_denylist.yaml` — no code change required.
- **Prometheus metrics**: Add `prometheus_client` to `requirements.txt` and replace the `Counter` in `eni_filter.py`.

---

*Giggso Inc × TrinityOps.ai × AIRTaaS*
