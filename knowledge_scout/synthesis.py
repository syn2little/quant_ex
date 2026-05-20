from __future__ import annotations

from .publisher import render_weekly_brief
from .schemas import ScoutBrief


def build_synthesis_prompt(brief: ScoutBrief, source_report: str = "") -> str:
    """Build a Chinese guidance prompt for LLM-based research synthesis."""
    return f"""你是 quant_ex 的外部研究知识分析员。请基于以下 Knowledge Scout 结果输出中文深度解析。

要求：
- 输出中文指导性研究 memo，不要只复述标题。
- 不要输出实盘信号，不要建议直接调仓。
- 不要引入外部行情/基本面数据采集需求。
- 每个方向必须映射到 quant_ex 的最小验证实验。
- 明确与 Phase7 attribution / experiment budget gate 的关系。
- 给出 kill criteria，避免为了迭代而迭代。

结构：
1. 本期结论
2. 最值得投入的 3 个方向
3. 每个方向的机制解释、适配性、最小验证实验、风险和放弃条件
4. 不建议做的方向
5. 下一轮 agent strategy iteration 建议

Knowledge Scout Brief:
{render_weekly_brief(brief)}

Source Report:
{source_report}
"""


def render_rule_based_synthesis(brief: ScoutBrief) -> str:
    """Fallback synthesis when no LLM call is requested or available."""
    lines = [
        f"# External Knowledge Scout Synthesis: {brief.generated_at[:10]}",
        "",
        "## 本期结论",
        "本报告是规则生成的保底深度解析草稿。它只提供研究假设，不构成策略晋升证据，也不允许直接生成实盘信号。",
        "",
        "## 最值得投入的方向",
    ]
    for idx, card in enumerate(brief.idea_cards[:3], start=1):
        lines.extend(
            [
                f"### {idx}. {card.title}",
                f"- 推荐动作：{card.score.recommended_action}",
                f"- 适配评分：{card.score.quant_ex_fit_score}/5，证据评分：{card.score.evidence_score}/5，新颖度：{card.score.novelty_score}/5",
                f"- 核心机制：{card.mechanism}",
                f"- quant_ex 映射：{'; '.join(card.mapping_to_quant_ex)}",
                "- 最小验证实验：先做离线诊断或小窗口 backtest，对照当前 baseline/control arm；只有通过 Phase7 attribution 和 experiment budget gate 才进入 WFV。",
                "- 放弃条件：无法定义 rank metric/control arm、需要新增外部行情或基本面数据、或初筛恶化 drawdown/positive-fold 约束。",
                "",
            ]
        )
    lines.extend(
        [
            "## 不建议做的方向",
            "- 需要高频盘口、tick、未授权基本面或外部实时行情的数据型 idea。",
            "- 只有模型复杂度、没有可比较 control arm 的深度模型 idea。",
            "- 与 A 股低频选股/组合风控无关的泛机器学习论文。",
            "",
            "## 下一轮 agent strategy iteration 建议",
            "优先选择 1 个 low/medium cost prototype，加 1 个 cheap diagnostic；不要同时展开多个高成本模型方向。",
            "",
        ]
    )
    return "\n".join(lines)
