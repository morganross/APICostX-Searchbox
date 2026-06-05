# Quotas and Cooldowns

Searchbox enforces provider limits locally.

## Daily Quotas

Daily usage is persisted by UTC date.

## Monthly Quotas

Monthly usage is persisted by UTC month. This is used for providers such as SerpApi when the account limit is monthly.

## Reservation

Quota is reserved before the external call to avoid concurrent overuse.

## Cooldowns

Cooldowns are applied after throttling, payment/account errors, provider failures, and timeouts.

## Visibility

Use `/config` and `/health/monitor` to inspect usage and cooldown state.
