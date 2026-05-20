# Where the Quantum Lives in D-Wave Hybrid Portfolio Optimization

```yaml
idea_id: 20260519_where-the-quantum-lives-in-d-wave-hybrid-portfol
source_url: https://arxiv.org/abs/2605.17623v1
source_type: arxiv
source_name: arxiv_qfin_pm
retrieved_at: 2026-05-19T15:53:16Z
access: open_or_metadata
asset_class_fit: a_share_equity
horizon_fit: daily_or_low_frequency
quant_ex_fit_score: 3
novelty_score: 3
evidence_score: 4
implementation_cost: low
recommended_action: summarize
risk_flags: []
```

## Claim
We audit how much of D-Wave's hybrid quantum-classical portfolio-optimization service is actually quantum. On cardinality-constrained mean-variance-turnover instances spanning N equal to 10 to 640 with a Gurobi MIQP optimality anchor, the constraint-native LeapHybridCQM service matches Gurobi's proven optimum on all 54 instances where Gurobi proves optimality, but the mean QPU access time is only 0.034 seconds out of a 5-second wall-clock budget, roughly 0.7 percent of the run. The remaining roughly 99 percent is the service's classical decomposition, sub-problem assembly, and feasibility-aware reassembly, so the reported D-Wave hybrid win on this problem class is a constraint-native classical pipeline with a small QPU contribution rather than a quantum-sampling win. Two structural results sharpen this audit. First, the cardinality penalty contributes a dense rank-one term that makes the penalty-encoded logical graph fully connected regardless of the original covariance density, collapsing the intended density benchmark axis for all penalty-encoded paths while leaving the constraint-native sparsity intact. Second, the constraint-native service returns identical solutions at every tested wall-clock budget from 5 to 300 seconds and across 10 repeated calls, a determinism property of the service on this problem class. Together with two classical baselines, namely Gurobi MIQP and simulated annealing, and a comparison against the penalty-encoded hybrid interface, these results extend the prior constraint-native versus penalty-encoded observation of Sakuler et al. from the statement that the constraint-native interface handles constraints natively to the operational decomposition of where the win actually originates, a finding that reframes how D-Wave hybrid performance should be reported in quantum-finance benchmarks.

## Mechanism
External research mechanism requires manual interpretation before local validation.

## Evidence
Academic metadata/abstract from arXiv. Treat as hypothesis until replicated locally.

## Mapping to quant_ex
- backtest/ and strategy/: portfolio construction, regime, or risk overlay diagnostic

## Validation Ladder
- Summarize mechanism and compare against existing rejected/promising research threads.
- Map the idea to one minimal feature/model/backtest change with a fixed control arm.
- Run a cheap same-model or small-window diagnostic only if implementation cost is low/medium.
- Promote to WFV only if the diagnostic improves IR/Sharpe without worsening drawdown controls.
- Require promotion report and human approval before touching strategy_candidates or rebalance configs.

## Kill Criteria
- Do not ingest external market/fundamental time-series data; reject ideas that require it outside approved data sources.
- Reject if it cannot define a comparable control arm and rank metric.
- Kill if early diagnostic breaks current drawdown/positive-fold constraints.

## References
- https://arxiv.org/abs/2605.17623v1
