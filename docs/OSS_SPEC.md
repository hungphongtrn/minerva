# Minerva OSS Specification

## Mission (One Line)
Enable teams to run ZeroClaw agents for many users safely, with isolated workspaces and a simple self-hosted API.

## Problem Statement
Running agent workloads for multiple users is risky and operationally heavy: workspaces can leak data, runs can collide, and teams must build orchestration from scratch. Minerva provides a secure, repeatable way to execute agents with strong isolation, persistence, and predictable integration.

## Core Value Proposition
- Safe multi-user execution with strong sandbox and workspace isolation.
- Simple API to start runs and consume runtime events.
- Durable user workspaces with checkpoint/restore for continuity.
- Portable "agent packs" that run locally or on your infrastructure.
- Policy controls that default to deny and fail closed.

## Target Users
Engineering teams who want to self-host a multi-tenant agent runtime for their product or internal tools. Operators bring their own infrastructure and identity model.

## Key Capabilities
- Authenticate requests and resolve end-user identity
- Isolated sandbox per workspace; prevent cross-user leakage
- One persistent workspace per user across sessions
- Bootstrap and register agent packs from files
- Run agent packs locally or on your infrastructure
- Persist run logs; checkpoint workspaces; restore on cold start
- Stream typed run events to clients in order

## Out of Scope
- Hosted SaaS control plane, billing, or enterprise org tenancy
- Business UX for procedure distillation or agent marketplaces
- Full observability suite (tracing, detailed cost analytics)
- Non-filesystem agent formats that break ZeroClaw semantics
- Long-term guest data retention (guest runs are ephemeral)

## Success Criteria
- New operator runs Minerva locally in under 30 minutes.
- A user cannot read/write another user's workspace in tests.
- Cold-start restore rehydrates latest checkpoint successfully.
- One workspace processes runs in strict request order.
- Event stream delivers typed events with <1s median latency.
