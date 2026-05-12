# Billing and Organization Admin Plan

## Current State

The product has a billing foundation:

- Usage summaries.
- Invite quota checks.
- Plan-like fields.
- Billing dashboard panel.
- Razorpay parameter placeholders in SSM.

This is enough for MVP demonstration, but not final paid SaaS billing.

## Before Paid Pilot

Decide:

- Plan names.
- Monthly invite/interview limits.
- Trial duration.
- What happens when quota is exceeded.
- Whether billing is Razorpay, Stripe, manual invoice, or pilot-only.

## Recommended MVP Plans

| Plan | Use Case | Limits |
| --- | --- | --- |
| Trial | Demo/pilot | Small fixed interview limit |
| Starter | Small hiring team | Monthly interview cap |
| Growth | Campus/startup hiring | Higher cap and export features |
| Enterprise | Custom | Custom volume, retention, support |

## Organization Admin Features

Add later:

- Organization settings page.
- Recruiter team member invites.
- Recruiter role management.
- Plan display and quota warnings.
- Organization data retention setting.
- Billing contact email.

## Billing Enforcement Rules

Recommended behavior:

- Creating jobs should remain allowed.
- Uploading candidates can remain allowed.
- Sending invites should enforce quota.
- Retest invites should count against quota.
- Recruiter should see a clear upgrade/contact-admin message.

