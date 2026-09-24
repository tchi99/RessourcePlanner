# ADR-009 — Persistent cancellation intent before destructive planning changes

Status: Accepted
Date: 2026-09-23

## Context

A `WorkforceRequest` can remain active while its approved work is already materialized as human `Shift` rows or non-human `AssetAllocation` rows. Directly changing the request status to `Annulée` is not sufficient in that case: the cancellation becomes a business intent that must be reviewed before any destructive planning mutation occurs.

The request aggregate already owns `aggregate_version` for request-level optimistic concurrency, while ADR-006 owns the separate global `planning_version` used by planning mutations. ADR-007 also requires human and non-human planning structures to stay distinct even when they participate in the same orchestration.

The cancellation workflow therefore needs a durable identity, an auditable lifecycle and one authoritative backend policy without conflating request concurrency with planning concurrency.

## Decision

1. The current cancellation cycle is persisted directly on `WorkforceRequest`, not in a new cancellation aggregate. It carries:
   - a stable UUID `cancellation_request_id`;
   - a nullable lifecycle state `PENDING | REJECTED | ACCEPTED`;
   - requester identity, timestamp and reason;
   - resolver identity, timestamp and resolution comment.

2. `WorkforceRequestHistory` remains the durable chronological audit. Every request and resolution records the cycle UUID and relevant request/resolution metadata so earlier cycles remain reconstructible after a later cycle replaces the current fields.

3. Cancellation eligibility is decided by one backend policy using the real materialized state:
   - active human decisions are detected through `ResourceRequirement → Shift`;
   - active non-human decisions are detected through `AssetRequirement → AssetAllocation`;
   - the primary request status alone is not sufficient to decide whether direct cancellation is safe.

4. The same policy is projected to demand detail, workflow actions and demand lists. Frontends consume this decision rather than reproducing cancellation rules locally.

5. Requesting or rejecting cancellation:
   - keeps the primary `WorkforceRequest.status` unchanged;
   - uses a real SQL CAS on `WorkforceRequest.aggregate_version`;
   - does not mutate `planning_version`;
   - does not rebuild or otherwise mutate the materialized plan.

6. Resolving a materialized cancellation requires coordinator-level planning authority. The application policy requires both demand approval and planning-management permissions for resolution actions.

7. Acceptance of a pending cancellation is a separate destructive planning command. When implemented, it must combine request-cycle/version validation with ADR-006 planning concurrency, revalidate the fresh materialized scope, release/delete the relevant human and asset allocations atomically, and complete the request state in the same transaction. A global rebuild is not the authority for this cleanup.

## Alternatives considered

### Encode cancellation only in the primary request status

Rejected. A pending cancellation would become indistinguishable from an accepted cancellation and would make it impossible to preserve the existing active plan while the coordinator decides.

### Create a dedicated persistent cancellation aggregate

Rejected for the current requirements. Only one current cancellation cycle is actionable and the existing request history already preserves prior cycles. A separate aggregate would add identity, lifecycle and joining complexity without providing a required capability.

### Use `planning_version` for request and rejection

Rejected. Those operations intentionally do not change the active plan. Advancing the global planning revision would create false planning conflicts and would mix two distinct concurrency domains.

### Infer materialization from request status

Rejected. The approved status does not prove that `Shift` or `AssetAllocation` rows exist, and it cannot distinguish an unmaterialized request from one carrying concrete operational decisions.

## Consequences

### Positive

- cancellation intent survives process restarts and concurrent UI sessions;
- every cycle has a stable identity and reconstructible audit;
- stale request/rejection commands fail at the request aggregate boundary;
- planning concurrency remains unchanged until a planning mutation actually occurs;
- humans and assets remain separate persistent models while sharing one cancellation workflow policy;
- detail, workflow and list surfaces cannot legitimately disagree about direct versus requested cancellation.

### Trade-offs / negative

- cancellation reads must inspect actual materialized planning rows;
- `WorkforceRequest` gains a small nullable sub-state in addition to its primary lifecycle status;
- acceptance is necessarily more complex than request/rejection because it crosses the request and planning concurrency domains;
- old direct-cancellation behavior for a materialized request is intentionally no longer valid.

## Implementation notes

The #399A slice introduces the persistent cycle, common policy, request/reject commands and audit without changing the plan. The destructive acceptance transaction is intentionally deferred to the subsequent #399 slices.

The materialization read should be batchable for list projections so the shared policy does not introduce N+1 SQL reads.

## References

- GitHub Issue #399
- PR #413
- ADR-004 — separate candidate request, approval and active plan
- ADR-006 — global planning mutation version
- ADR-007 — reservable non-human resources
