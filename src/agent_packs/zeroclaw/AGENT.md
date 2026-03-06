# Zeroclaw Test Agent

A minimal agent pack scaffold for Zeroclaw end-to-end testing.

## Purpose

This agent pack validates the Zeroclaw execution path:
- Infrastructure provisioning
- Sandbox spawn
- Gateway execution via /webhook
- Multi-user -> multi-sandbox behavior

## Capabilities

- Responds to health checks
- Accepts webhook execution requests
- Returns structured responses

## Usage

Register with:
```bash
minerva register src/agent_packs/zeroclaw
```

## Identity

- **Name**: Zeroclaw Test Agent
- **Version**: 1.0.0
- **Purpose**: E2E validation and integration testing
