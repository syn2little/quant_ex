from __future__ import annotations

import json
from typing import Any, Callable, Dict, Iterable, List, Optional

from .llm import OpenAICompatibleChatClient
from .prompt_loader import load_prompt
from .schemas import AgentRole, ChairDecision, RoleReport, StrategyProjectContext
from .validation import attach_role_metadata


def _is_rejecting_research_verdict(verdict: str) -> bool:
    value = verdict.lower()
    return any(token in value for token in ["reject", "block", "kill", "do_not", "degraded", "refute"])


def _fallback_focus(role_name: str, reports: List[RoleReport]) -> str:
    if role_name == "data_factor_analyst":
        return "Identify whether the objective needs data/factor evidence before any model or execution work."
    if role_name == "backtest_analyst":
        return "Define the minimum comparable validation path and control arm."
    if role_name == "bear_researcher":
        return "Attack the current proposal and name kill tests."
    if role_name == "experiment_designer":
        return "Convert the strongest surviving idea into one-variable experiment arms."
    if role_name == "research_portfolio_manager":
        return "Decide whether the discussion is ready for a bounded experiment plan."
    if reports:
        return f"Respond to the latest uncertainty raised by {reports[-1].role}."
    return "Contribute only the perspective needed for the current objective."


DEFAULT_ROLES: List[AgentRole] = [
    AgentRole(
        name="data_factor_analyst",
        mission="Audit data coverage, factor redundancy, lag safety, and orthogonal evidence opportunities.",
        perspective="Data-centric quant analyst influenced by RD-Agent's factor trace discipline.",
        required_outputs=["findings", "hypotheses", "screening plan", "leakage risks"],
    ),
    AgentRole(
        name="model_analyst",
        mission="Judge whether model changes are justified versus data, factor, or hyperparameter causes.",
        perspective="Quant model reviewer focused on avoiding costly architecture churn without evidence.",
        required_outputs=["diagnosis", "model hypotheses", "training risks"],
    ),
    AgentRole(
        name="backtest_analyst",
        mission="Protect experimental comparability across benchmark, rank metric, deal price, cost, and time windows.",
        perspective="Validation specialist who assumes apparent gains may be measurement artifacts.",
        required_outputs=["comparability checks", "control arm", "validation ladder"],
    ),
    AgentRole(
        name="execution_analyst",
        mission="Review implementation risk around turnover, concentration, liquidity, rebalance, and notification flows.",
        perspective="Execution engineer who protects real-world operability.",
        required_outputs=["execution constraints", "risk controls", "approval gates"],
    ),
    AgentRole(
        name="bull_researcher",
        mission="Make the strongest case for the most promising strategy upgrade path.",
        perspective="Debate role inspired by TradingAgents-ex bull researcher.",
        required_outputs=["supporting case", "expected upside", "why now"],
    ),
    AgentRole(
        name="bear_researcher",
        mission="Attack the proposal for overfit, leakage, redundancy, regime fragility, and operational traps.",
        perspective="Debate role inspired by TradingAgents-ex bear researcher.",
        required_outputs=["failure modes", "kill tests", "do-not-promote conditions"],
    ),
    AgentRole(
        name="research_manager",
        mission="Turn analyst and debate output into a compact research rating and experiment brief.",
        perspective="Research judge using explicit promotion criteria instead of vibes.",
        model_tier="deep",
        required_outputs=["rating", "why", "preferred directions"],
    ),
    AgentRole(
        name="experiment_designer",
        mission="Translate the research brief into a control arm and narrowly-scoped treatment arms.",
        perspective="Experiment designer who enforces one-major-variable-per-arm.",
        required_outputs=["control arm", "treatment arms", "commands", "success criteria"],
    ),
    AgentRole(
        name="aggressive_risk_reviewer",
        mission="Argue why a bolder experiment is worth the research budget.",
        perspective="High-upside risk reviewer from the aggressive side of the risk triangle.",
        required_outputs=["upside justification", "acceptable risks", "expansion triggers"],
    ),
    AgentRole(
        name="conservative_risk_reviewer",
        mission="Argue why the plan should be scaled back, delayed, or rejected.",
        perspective="Capital-preserving risk reviewer from the conservative side of the risk triangle.",
        required_outputs=["blockers", "downside scenarios", "approval blockers"],
    ),
    AgentRole(
        name="neutral_risk_reviewer",
        mission="Find the smallest reliable validation path between ambition and caution.",
        perspective="Balanced risk reviewer looking for cheaper and cleaner evidence.",
        required_outputs=["compromise path", "phased validation", "decision conditions"],
    ),
    AgentRole(
        name="research_portfolio_manager",
        mission="Make the final research-capital allocation decision and choose approved experiment arms.",
        perspective="Portfolio manager for strategy research effort, not live trading capital.",
        model_tier="deep",
        required_outputs=["decision", "approved arms", "blocked arms", "validation ladder"],
    ),
]
ProgressCallback = Callable[..., None]


class RoleRunner:
    """Runs strategy roles with optional LLM calls and deterministic fallback."""

    def __init__(
        self,
        roles: Optional[Iterable[AgentRole]] = None,
        *,
        llm_config: Optional[Dict[str, Any]] = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.roles = list(roles or DEFAULT_ROLES)
        self.llm_config = llm_config or {}
        self.progress_callback = progress_callback
        self.traces: List[Dict[str, Any]] = []
        self.discussion_trace: List[Dict[str, Any]] = []
        self.chair_decisions: List[ChairDecision] = []

    def run_all(
        self,
        context: StrategyProjectContext,
        *,
        use_llm: bool = False,
    ) -> List[RoleReport]:
        self.traces = []
        self.discussion_trace = []
        self.chair_decisions = []
        reports: List[RoleReport] = []
        total = len(self.roles)
        for index, role in enumerate(self.roles, start=1):
            self._emit_progress(
                "role_start",
                message=f"Running role {role.name}.",
                role=role.name,
                model_tier=role.model_tier,
                index=index,
                total=total,
                use_llm=use_llm,
                discussion_mode="sequential",
            )
            report = self.run_role(role, context, reports, use_llm=use_llm)
            reports.append(report)
            self._emit_progress(
                "role_done",
                message=f"Role {role.name} completed.",
                role=role.name,
                verdict=report.verdict,
                confidence=report.confidence,
                index=index,
                total=total,
                discussion_mode="sequential",
            )
        return reports

    def run_meeting(
        self,
        context: StrategyProjectContext,
        *,
        use_llm: bool = False,
        max_turns: int = 8,
        min_turns: int = 4,
        max_roles_per_turn: int = 1,
        allow_repeat_roles: bool = False,
    ) -> List[RoleReport]:
        """Run an adaptive virtual meeting chaired by an LLM when configured.

        The chair decides which role is needed next and when the discussion is
        sufficiently converged. Offline mode uses a compact deterministic agenda
        so tests and local dry runs remain reproducible.
        """

        self.traces = []
        self.discussion_trace = []
        self.chair_decisions = []
        reports: List[RoleReport] = []
        called_roles: set[str] = set()
        max_turns = max(1, int(max_turns))
        min_turns = max(1, int(min_turns))
        max_roles_per_turn = max(1, min(int(max_roles_per_turn), len(self.roles)))

        for turn_index in range(1, max_turns + 1):
            self._emit_progress(
                "chair_start",
                message=f"Meeting chair is selecting role(s) for round {turn_index}.",
                turn_index=turn_index,
                max_turns=max_turns,
                reports_count=len(reports),
                discussion_mode="meeting",
            )
            decision = self._chair_decide(
                context,
                reports,
                turn_index=turn_index,
                use_llm=use_llm,
                min_turns=min_turns,
                max_turns=max_turns,
                max_roles_per_turn=max_roles_per_turn,
                called_roles=called_roles,
                allow_repeat_roles=allow_repeat_roles,
            )
            self._emit_progress(
                "chair_done",
                message=f"Chair decision for round {turn_index}: {decision.action}.",
                turn_index=turn_index,
                action=decision.action,
                next_role=decision.next_role,
                next_roles=decision.next_roles,
                focus=decision.focus,
                discussion_mode="meeting",
            )
            if decision.action == "final" and len(reports) >= min_turns:
                self.chair_decisions.append(decision)
                self.discussion_trace.append(
                    {
                        "turn_index": turn_index,
                        "chair_decision": decision.to_dict(),
                        "used_llm": use_llm,
                        "called_role": None,
                    }
                )
                break

            roles_to_call = self._roles_for_decision(
                decision,
                called_roles=called_roles,
                reports=reports,
                max_roles_per_turn=max_roles_per_turn,
                allow_repeat_roles=allow_repeat_roles,
            )
            if not roles_to_call:
                decision.action = "final"
                self.chair_decisions.append(decision)
                self.discussion_trace.append(
                    {
                        "turn_index": turn_index,
                        "chair_decision": decision.to_dict(),
                        "used_llm": use_llm,
                        "called_role": None,
                    }
                )
                break

            decision.action = "call_role"
            decision.next_roles = [role.name for role in roles_to_call]
            decision.next_role = decision.next_roles[0]
            self.chair_decisions.append(decision)
            called_this_turn: list[str] = []
            for role_index, role in enumerate(roles_to_call, start=1):
                self._emit_progress(
                    "role_start",
                    message=f"Round {turn_index}: running role {role.name}.",
                    role=role.name,
                    model_tier=role.model_tier,
                    turn_index=turn_index,
                    index=role_index,
                    total=len(roles_to_call),
                    use_llm=use_llm,
                    discussion_mode="meeting",
                )
                report = self.run_role(role, context, reports, use_llm=use_llm, chair_focus=decision.focus)
                reports.append(report)
                called_roles.add(role.name)
                called_this_turn.append(role.name)
                self._emit_progress(
                    "role_done",
                    message=f"Round {turn_index}: role {role.name} completed.",
                    role=role.name,
                    verdict=report.verdict,
                    confidence=report.confidence,
                    turn_index=turn_index,
                    index=role_index,
                    total=len(roles_to_call),
                    discussion_mode="meeting",
                )
            self.discussion_trace.append(
                {
                    "turn_index": turn_index,
                    "chair_decision": decision.to_dict(),
                    "used_llm": use_llm,
                    "called_role": called_this_turn[0] if called_this_turn else None,
                    "called_roles": called_this_turn,
                }
            )

        if not any(item.action == "final" for item in self.chair_decisions):
            final = ChairDecision(
                turn_index=len(self.chair_decisions) + 1,
                action="final",
                decision="continue",
                rationale="Reached the configured meeting turn budget.",
                final_summary="Meeting stopped at the configured max_turns; use the collected reports for synthesis.",
                confidence=0.6,
            )
            self.chair_decisions.append(final)
            self.discussion_trace.append(
                {
                    "turn_index": final.turn_index,
                    "chair_decision": final.to_dict(),
                    "used_llm": use_llm,
                    "called_role": None,
                }
            )

        return reports

    def run_role(
        self,
        role: AgentRole,
        context: StrategyProjectContext,
        prior_reports: List[RoleReport],
        *,
        use_llm: bool = False,
        chair_focus: str = "",
    ) -> RoleReport:
        system, user = self._build_prompt(role, context, prior_reports, chair_focus=chair_focus)
        if use_llm:
            client = OpenAICompatibleChatClient.from_env(model_tier=role.model_tier, llm_config=self.llm_config)
            if client.is_configured:
                self._emit_progress(
                    "role_llm_start",
                    message=f"Calling LLM for role {role.name}.",
                    role=role.name,
                    model=client.model,
                    model_tier=role.model_tier,
                    reasoning_effort=client.reasoning_effort,
                )
                try:
                    payload = client.complete_json(system=system, user=user)
                    report = RoleReport.from_dict(
                        role.name,
                        payload,
                        raw_response=json.dumps(payload, ensure_ascii=False),
                    )
                    report = attach_role_metadata(role, report, prior_reports)
                    self.traces.append(
                        self._build_trace(
                            role=role,
                            prior_reports=prior_reports,
                            system_prompt=system,
                            user_prompt=user,
                            report=report,
                            used_llm=True,
                            client=client,
                            chair_focus=chair_focus,
                        )
                    )
                    self._emit_progress(
                        "role_llm_done",
                        message=f"LLM response received for role {role.name}.",
                        role=role.name,
                        model=client.model,
                    )
                    return report
                except Exception as exc:
                    self._emit_progress(
                        "role_llm_error",
                        message=f"LLM call failed for role {role.name}; falling back to offline role logic.",
                        role=role.name,
                        model=client.model,
                        error=str(exc),
                    )
        report = attach_role_metadata(role, self._fallback_report(role, context, prior_reports), prior_reports)
        self.traces.append(
            self._build_trace(
                role=role,
                prior_reports=prior_reports,
                system_prompt=system,
                user_prompt=user,
                report=report,
                used_llm=False,
                client=None,
                chair_focus=chair_focus,
            )
        )
        return report

    def _emit_progress(self, stage: str, **payload) -> None:
        if not self.progress_callback:
            return
        try:
            self.progress_callback("progress", stage=stage, **payload)
        except Exception:
            pass

    def _chair_decide(
        self,
        context: StrategyProjectContext,
        reports: List[RoleReport],
        *,
        turn_index: int,
        use_llm: bool,
        min_turns: int,
        max_turns: int,
        max_roles_per_turn: int,
        called_roles: set[str],
        allow_repeat_roles: bool,
    ) -> ChairDecision:
        if use_llm:
            client = OpenAICompatibleChatClient.from_env(model_tier="deep", llm_config=self.llm_config)
            if client.is_configured:
                system, user = self._build_chair_prompt(
                    context,
                    reports,
                    turn_index=turn_index,
                    min_turns=min_turns,
                    max_turns=max_turns,
                    max_roles_per_turn=max_roles_per_turn,
                    called_roles=called_roles,
                    allow_repeat_roles=allow_repeat_roles,
                )
                try:
                    payload = client.complete_json(system=system, user=user, max_tokens=min(client.max_tokens, 1200))
                    decision = ChairDecision.from_dict(turn_index, payload)
                    return self._normalize_chair_decision(
                        decision,
                        reports=reports,
                        called_roles=called_roles,
                        min_turns=min_turns,
                        allow_repeat_roles=allow_repeat_roles,
                        max_roles_per_turn=max_roles_per_turn,
                    )
                except Exception as exc:
                    self._emit_progress(
                        "chair_llm_error",
                        message="Meeting chair LLM call failed; using offline chair fallback.",
                        turn_index=turn_index,
                        model=client.model,
                        error=str(exc),
                    )
        return self._fallback_chair_decision(
            reports,
            turn_index=turn_index,
            min_turns=min_turns,
            called_roles=called_roles,
            max_roles_per_turn=max_roles_per_turn,
        )

    def _normalize_chair_decision(
        self,
        decision: ChairDecision,
        *,
        reports: List[RoleReport],
        called_roles: set[str],
        min_turns: int,
        allow_repeat_roles: bool,
        max_roles_per_turn: int,
    ) -> ChairDecision:
        decision.action = decision.action if decision.action in {"call_role", "final"} else "call_role"
        if decision.action == "final" and len(reports) < min_turns:
            decision.action = "call_role"
            decision.rationale = (decision.rationale + " " if decision.rationale else "") + (
                "Minimum meeting turns have not been reached."
            )
        roles = self._roles_for_decision(
            decision,
            called_roles=called_roles,
            reports=reports,
            max_roles_per_turn=max_roles_per_turn,
            allow_repeat_roles=allow_repeat_roles,
        )
        if decision.action == "call_role":
            decision.next_roles = [role.name for role in roles]
            decision.next_role = decision.next_roles[0] if decision.next_roles else ""
            if len(decision.next_roles) == 0:
                decision.rationale = (decision.rationale + " " if decision.rationale else "") + (
                    "No valid role remained for this round."
                )
        return decision

    def _fallback_chair_decision(
        self,
        reports: List[RoleReport],
        *,
        turn_index: int,
        min_turns: int,
        called_roles: set[str],
        max_roles_per_turn: int,
    ) -> ChairDecision:
        if len(reports) >= min_turns and "research_portfolio_manager" in called_roles:
            return ChairDecision(
                turn_index=turn_index,
                action="final",
                decision="continue",
                rationale="Offline meeting reached minimum coverage and has a decision-capable report.",
                final_summary="Offline fallback meeting completed with enough analyst, adversarial, and decision context.",
                confidence=0.7,
            )
        roles = self._fallback_next_roles(called_roles, reports, limit=max_roles_per_turn)
        return ChairDecision(
            turn_index=turn_index,
            action="call_role",
            next_role=roles[0].name if roles else "",
            next_roles=[role.name for role in roles],
            rationale="Offline fallback selected the next role needed for balanced coverage.",
            focus=_fallback_focus(roles[0].name if roles else "", reports),
            decision="continue",
            confidence=0.65,
        )

    def _roles_for_decision(
        self,
        decision: ChairDecision,
        *,
        called_roles: set[str],
        reports: List[RoleReport],
        max_roles_per_turn: int,
        allow_repeat_roles: bool,
    ) -> List[AgentRole]:
        requested = decision.next_roles or ([decision.next_role] if decision.next_role else [])
        roles: list[AgentRole] = []
        seen: set[str] = set()
        for name in requested:
            role = self._role_by_name(name)
            if role is None or role.name in seen:
                continue
            if not allow_repeat_roles and role.name in called_roles:
                continue
            roles.append(role)
            seen.add(role.name)
            if len(roles) >= max_roles_per_turn:
                break
        if roles:
            return roles

        fallback_roles = self._fallback_next_roles(called_roles, reports, limit=max_roles_per_turn)
        if fallback_roles and not decision.rationale:
            decision.rationale = "Fallback selected the next uncovered role(s)."
        return fallback_roles

    def _fallback_next_role(self, called_roles: set[str], reports: List[RoleReport]) -> Optional[AgentRole]:
        preferred = [
            "data_factor_analyst",
            "backtest_analyst",
            "bear_researcher",
            "experiment_designer",
            "research_portfolio_manager",
        ]
        if any(_is_rejecting_research_verdict(report.verdict) for report in reports):
            preferred = ["bear_researcher", "conservative_risk_reviewer", "research_portfolio_manager"]
        for name in preferred:
            role = self._role_by_name(name)
            if role and role.name not in called_roles:
                return role
        return next((role for role in self.roles if role.name not in called_roles), None)

    def _fallback_next_roles(self, called_roles: set[str], reports: List[RoleReport], *, limit: int) -> List[AgentRole]:
        roles: list[AgentRole] = []
        while len(roles) < limit:
            shadow_called = called_roles | {role.name for role in roles}
            role = self._fallback_next_role(shadow_called, reports)
            if role is None:
                break
            roles.append(role)
            if role.name == "research_portfolio_manager":
                break
        return roles

    def _role_by_name(self, name: str) -> Optional[AgentRole]:
        return next((role for role in self.roles if role.name == name), None)

    @staticmethod
    def _build_trace(
        *,
        role: AgentRole,
        prior_reports: List[RoleReport],
        system_prompt: str,
        user_prompt: str,
        report: RoleReport,
        used_llm: bool,
        client: Optional[OpenAICompatibleChatClient],
        chair_focus: str = "",
    ) -> Dict[str, Any]:
        return {
            "role": role.name,
            "model_tier": role.model_tier,
            "used_llm": used_llm,
            "model": client.model if client else None,
            "reasoning_effort": client.reasoning_effort if client else None,
            "temperature": client.temperature if client else None,
            "max_tokens": client.max_tokens if client else None,
            "stream": client.stream if client else None,
            "upstream_roles": [item.role for item in prior_reports],
            "chair_focus": chair_focus,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "raw_response": report.raw_response,
            "parsed_report": report.to_dict(),
        }

    @staticmethod
    def _build_prompt(
        role: AgentRole,
        context: StrategyProjectContext,
        prior_reports: List[RoleReport],
        *,
        chair_focus: str = "",
    ) -> tuple[str, str]:
        system = (
            load_prompt("shared_system").strip()
            + "\n\n"
            + load_prompt(role.name).strip()
            + "\n\nOutput strictly valid JSON with keys: role, thesis, evidence, proposals, risks, verdict, confidence, next_actions, prompt_name. "
            "Keep proposals testable and compatible with the local framework."
        )
        user = json.dumps(
            {
                "role": role.to_dict(),
                "context": context.to_prompt_dict(),
                "prior_reports": [r.to_dict() for r in prior_reports],
                "upstream_role_order": [r.role for r in prior_reports],
                "chair_focus": chair_focus,
            },
            ensure_ascii=False,
            default=str,
        )
        return system, user

    def _build_chair_prompt(
        self,
        context: StrategyProjectContext,
        reports: List[RoleReport],
        *,
        turn_index: int,
        min_turns: int,
        max_turns: int,
        max_roles_per_turn: int,
        called_roles: set[str],
        allow_repeat_roles: bool,
    ) -> tuple[str, str]:
        system = (
            "You are the virtual meeting chair for a quant strategy-iteration agent team. "
            "Decide which specialist role should speak next, or finish the meeting when enough evidence exists. "
            "Do not call every role mechanically. Call a role only if its perspective is useful for the current uncertainty. "
            "You may call multiple roles in the same round, but never exceed max_roles_per_round. "
            "Finish only when the discussion has enough data/factor, validation, risk, and decision coverage. "
            "Output strictly valid JSON with keys: action, next_roles, rationale, focus, decision, final_summary, confidence. "
            "action must be call_role or final."
        )
        available_roles = [
            role.to_dict()
            for role in self.roles
            if allow_repeat_roles or role.name not in called_roles
        ]
        user = json.dumps(
            {
                "objective": context.objective,
                "turn_index": turn_index,
                "min_turns": min_turns,
                "max_turns": max_turns,
                "max_roles_per_round": max_roles_per_turn,
                "allow_repeat_roles": allow_repeat_roles,
                "available_roles": available_roles,
                "called_roles": sorted(called_roles),
                "prior_reports": [report.to_dict() for report in reports],
                "context_brief": {
                    "selected_candidates": (context.candidate_summary or {}).get("selected", {}),
                    "recent_memory": context.memory_context[-3:],
                    "constraints": context.constraints,
                    "repo_capabilities": context.repo_capabilities[:20],
                },
            },
            ensure_ascii=False,
            default=str,
        )
        return system, user

    @staticmethod
    def _fallback_report(
        role: AgentRole,
        context: StrategyProjectContext,
        prior_reports: List[RoleReport],
    ) -> RoleReport:
        selected = context.candidate_summary.get("selected", {}) if context.candidate_summary else {}
        control = selected.get("conservative_candidate") or selected.get("stability_candidate") or "csi1000_balanced"
        active = selected.get("stability_candidate") or selected.get("active_candidate") or control
        memory_note = context.memory_context[-1].splitlines()[0] if context.memory_context else "no prior agent memory"
        backtest_count = len(context.artifact_summaries.get("recent_backtests", []))

        templates: Dict[str, RoleReport] = {
            "data_factor_analyst": RoleReport(
                role=role.name,
                prompt_name=role.name,
                thesis="The next durable alpha improvement is more likely to come from orthogonal evidence than from more Alpha158-like feature churn.",
                evidence=[
                    "Recent logs show repeated same-model uplifts that did not survive WFV.",
                    "The project already contains broad factor families and a factor screener.",
                    "Fundamental gating experiments demonstrated how easy it is to overread same-model improvements.",
                    f"Phase 2 context includes {backtest_count} recent backtest artifact summaries.",
                ],
                proposals=[
                    "Prioritize proposals that specify point-in-time lag, cache policy, and redundancy checks.",
                    "Do not promote any new factor family without an explicit IC/ICIR and correlation screening plan.",
                    "Keep news/sentiment or alternative data as future plugin roles instead of first-pass hard dependencies.",
                ],
                risks=[
                    "Agent-generated factor ideas can duplicate Alpha158 signals under new names.",
                    "Coverage gaps and lag mistakes are more dangerous than missing a fashionable factor family.",
                ],
                verdict="continue",
                confidence=0.77,
                next_actions=["Require each future factor proposal to include orthogonality and lag claims."],
            ),
            "model_analyst": RoleReport(
                role=role.name,
                prompt_name=role.name,
                thesis="Model changes should stay secondary until there is concrete evidence that the current LGBM line is the bottleneck.",
                evidence=[
                    "Past system iterations found LGBM plus Alpha158 to be the most validated line so far.",
                    "Alternative models and extra factors already degraded WFV in several recent cycles.",
                    f"Current durable controls include {control} and {active}.",
                ],
                proposals=[
                    "Keep model experiments narrow: hyperparameters, ranking objective, or stability checks before architecture changes.",
                    "Require a diagnosis explaining why a model change is needed instead of a data or execution change.",
                ],
                risks=[
                    "A larger model can increase training cost without improving generalization.",
                    "Model experiments easily mask comparability issues when dates or cost assumptions shift.",
                ],
                verdict="continue",
                confidence=0.72,
                next_actions=["Default the first agentic loop to planning and validation, not model rewrites."],
            ),
            "backtest_analyst": RoleReport(
                role=role.name,
                prompt_name=role.name,
                thesis="The fastest way to destroy signal quality is to compare non-equivalent backtests and mistake the delta for alpha.",
                evidence=[
                    "This repo already treats benchmark-aware IR ranking and deal_price consistency as first-class concerns.",
                    "Recent conclusions explicitly warn against mixing Sharpe-only and IR-ranked results.",
                    "The Phase 2 context pack carries CSV summaries instead of only file paths.",
                ],
                proposals=[
                    "Every plan must define control, metric priority, benchmark, rank_metric, deal_price, cost, and slippage.",
                    "Same-model backtest remains a filter only; promotion evidence comes from WFV after approval.",
                ],
                risks=["Without a hard control arm, multi-role output becomes prose with no experiment value."],
                verdict="continue",
                confidence=0.85,
                next_actions=["Encode comparability checks into every saved agent plan."],
            ),
            "execution_analyst": RoleReport(
                role=role.name,
                prompt_name=role.name,
                thesis="Execution and rebalance semantics deserve their own review before any experiment is considered promotable.",
                evidence=[
                    "Overlay branches have already shown concentration and regime sensitivity.",
                    "Scheduled rebalance, hold protection, and reminders can have external effects or misleading dry-run assumptions.",
                    f"Latest agent memory marker: {memory_note}.",
                ],
                proposals=[
                    "Tag any plan that touches scheduled rebalance, live-like reminders, or data updates as approval-gated.",
                    "Require concentration, turnover, cost, and liquidity notes alongside Sharpe and IR.",
                ],
                risks=["A planner must never imply it can safely trigger live notifications or trading semantics."],
                verdict="continue",
                confidence=0.81,
                next_actions=["Make approval flags explicit in every experiment arm."],
            ),
            "bull_researcher": RoleReport(
                role=role.name,
                prompt_name=role.name,
                thesis="A role-based research layer can raise experiment quality without forcing a wholesale framework rewrite.",
                evidence=[
                    "RD-Agent contributes a stronger hypothesis-feedback discipline than the current manual iteration loop.",
                    "TradingAgents-ex contributes structured adversarial review before the final decision.",
                    f"The bull role receives {len(prior_reports)} upstream reports.",
                ],
                proposals=[
                    "Use the agent layer to surface better experiments before spending WFV budget.",
                    "Keep the underlying quant_ex execution path unchanged for trust and reuse.",
                ],
                risks=["Process quality improves immediately, but alpha improves only if execution discipline stays strict."],
                verdict="support",
                confidence=0.78,
                next_actions=["Approve Phase 1 infrastructure so later experiments are cleaner."],
            ),
            "bear_researcher": RoleReport(
                role=role.name,
                prompt_name=role.name,
                thesis="The easiest failure mode is letting convincing multi-agent prose outrun actual validation evidence.",
                evidence=[
                    "This project already has evidence that same-model improvements often fail WFV.",
                    "Role systems can drift into non-comparable bundles when each role proposes different changes.",
                    f"The bear role can inspect {len(prior_reports)} upstream reports before objecting.",
                ],
                proposals=[
                    "Require one-major-variable-per-arm and an explicit kill test for each treatment.",
                    "Do not let Phase 1 execute expensive commands automatically.",
                ],
                risks=[
                    "Memory logs can create false confidence if they are confused with durable strategy evidence.",
                    "A planner that writes no prompts and no context pack will be hard to audit later.",
                ],
                verdict="continue_with_gates",
                confidence=0.86,
                next_actions=["Bake approval gates and context snapshots into the saved run bundle."],
            ),
            "research_manager": RoleReport(
                role=role.name,
                prompt_name=role.name,
                thesis="The proposal earns a `CompareNext` style research rating: valuable enough to integrate as infrastructure, but not yet evidence of strategy improvement.",
                evidence=[
                    "All analyst and debate roles point toward the same near-term need: a disciplined planning layer.",
                    "No role argues for immediate autonomous execution or model rewriting.",
                    f"Upstream role count at manager stage: {len(prior_reports)}.",
                ],
                proposals=[
                    "Implement Phase 1 as offline planner plus prompt system, memory log, CLI, and tests.",
                    "Delay expensive execution hooks until the planner proves stable.",
                ],
                risks=["Infrastructure progress should not be logged as alpha progress."],
                verdict="compare_next",
                confidence=0.84,
                next_actions=["Translate this brief into a concrete phased implementation plan."],
            ),
            "experiment_designer": RoleReport(
                role=role.name,
                prompt_name=role.name,
                thesis="The first phase should implement planning artifacts, not live experiment execution automation.",
                evidence=[
                    "The repo already has stable training/backtest/WFV commands to reference in generated plans.",
                    "A run bundle with prompts, context, plan, and memory is enough to test the research layer.",
                    "Schema warnings are retained in role reports instead of being discarded.",
                ],
                proposals=[
                    "Create one control arm and three infrastructure-oriented treatment arms for the agent layer itself.",
                    "Save JSON, Markdown, context pack, and prompt catalog per run.",
                ],
                risks=["If Phase 1 tries to run experiments, it will inherit too many approval and cost concerns."],
                verdict="continue",
                confidence=0.82,
                next_actions=["Implement CLI and save-run bundle before any execution adapters."],
            ),
            "aggressive_risk_reviewer": RoleReport(
                role=role.name,
                prompt_name=role.name,
                thesis="It is worth spending engineering effort now because the research layer can improve every future iteration cycle.",
                evidence=[
                    "The current strategy process already has enough history to benefit from structured memory.",
                    "Prompted adversarial review can prevent wasting future WFV cycles.",
                    f"Aggressive review receives {len(prior_reports)} upstream reports.",
                ],
                proposals=[
                    "Land prompt files and memory now, so later LLM use has a disciplined frame.",
                    "Keep optional LLM support available behind explicit flags.",
                ],
                risks=["There is moderate implementation cost, but little market or data risk in Phase 1."],
                verdict="support",
                confidence=0.74,
                next_actions=["Include the prompt catalog in the run bundle for auditability."],
            ),
            "conservative_risk_reviewer": RoleReport(
                role=role.name,
                prompt_name=role.name,
                thesis="The safe path is to keep Phase 1 offline, deterministic where possible, and locally testable.",
                evidence=[
                    "No new runtime should be introduced beyond the existing repo dependencies.",
                    "LLM calls are optional and must never write secrets to disk.",
                    "Role schema validation is warning-only in Phase 2, keeping offline planning resilient.",
                ],
                proposals=[
                    "Persist only local context and plan outputs.",
                    "Add tests before any future execution adapters are considered.",
                ],
                risks=["Even infrastructure changes can become noisy if run bundles are inconsistent."],
                verdict="support_with_limits",
                confidence=0.88,
                next_actions=["Add deterministic tests around context, save-run, and memory append."],
            ),
            "neutral_risk_reviewer": RoleReport(
                role=role.name,
                prompt_name=role.name,
                thesis="The balanced path is a phased rollout: planning first, optional LLM second, execution adapters later.",
                evidence=[
                    "This captures the best of both source projects while staying small.",
                    "The repo already has enough local context to make an offline planner useful immediately.",
                    "Phase 2 adds richer context without coupling to expensive command execution.",
                ],
                proposals=[
                    "Document the implementation phases inside the repo.",
                    "Use the CLI itself as the first integration boundary.",
                ],
                risks=["Skipping the phased rollout would couple planning, execution, and validation too early."],
                verdict="support",
                confidence=0.90,
                next_actions=["Ship an implementation roadmap alongside the code."],
            ),
            "research_portfolio_manager": RoleReport(
                role=role.name,
                prompt_name=role.name,
                thesis="Approve Phase 1 infrastructure and block anything resembling autonomous expensive execution.",
                evidence=[
                    "The plan is modular, testable, and consistent with the repo's current validation discipline.",
                    "All major risks can be contained with offline defaults and explicit approval gates.",
                    f"Final decision sees {len(prior_reports)} upstream role reports and preserved schema warnings.",
                ],
                proposals=[
                    "Land implementation plan, prompt system, context builder, memory log, CLI, and tests.",
                    "Record the system iteration as an infrastructure cycle with no expected Sharpe change.",
                ],
                risks=["Research memory must stay advisory until fed by validated outcomes."],
                verdict="approve_phase1",
                confidence=0.91,
                next_actions=["Save a sample run bundle and update the system iteration log."],
            ),
        }
        return templates[role.name]
