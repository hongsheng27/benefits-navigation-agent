# 接住 — Benefits Navigation Agent

A privacy-preserving, policy-governed benefits navigation agent built for the
2026 Taiwan Generative AI Application Hackathon.

## Problem

People who need social benefits often do not know which programs exist,
which agencies administer them, or which documents they need.

## Solution

Users describe a life event in natural language. The system expands related
entitlements, asks for missing non-identifying information, retrieves official
government sources, evaluates structured eligibility rules, and produces an
action checklist.

## Architecture

- Amazon Bedrock
- Amazon Bedrock AgentCore
- Curated entitlement graph
- Source-grounded RAG
- Deterministic eligibility rules
- Human-in-the-loop confirmation

## MVP Scenario

Spouse death:

1. Death registration
2. Funeral benefit
3. Survivor pension
4. National Health Insurance status change

## Privacy Boundary

Real personal information remains on the user's device. Only de-identified
eligibility attributes are sent to cloud services.

## Status

Planning and architecture phase.
