# Risk Register

| Risk | Trigger | Mitigation |
|---|---|---|
| Low PR merge rate | Acceptance rate < 40% for 2 weeks | Reduce task scope, improve acceptance commands, tighten prompts |
| Operator overload | Median approval latency > 12h | Priority queueing, notification throttling, auto-defer low-impact jobs |
| Desktop SPOF | >2 downtime incidents/month | Migrate control-plane to Pis, keep spare image and daily backups |
| API provider disruption | Provider errors >10% for 30 min | Enable multi-provider LiteLLM routing and fallback profiles |
| Scope drift to self-improvement | External-output job share <80% for 2 weeks | Enforce policy quota and weekly governance review |
