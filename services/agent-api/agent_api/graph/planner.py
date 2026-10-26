"""Plan-and-execute: turn NLU output into ordered steps, revise them as the turn goes on."""

from agent_api.graph.state import PlanStep

# Lower runs first: connectivity problems often cause the others (VPN down -> Outlook fails).
PRIORITY = {"network_issue": 0, "vpn_issue": 1, "account_locked": 2, "password_reset": 3,
            "email_issue": 4, "access_request": 5, "software_install": 6, "hardware_issue": 7,
            "printer_issue": 8, "ticket_status": 9, "report_request": 10, "other": 11}
CATEGORY = {"password_reset": "account", "account_locked": "account", "vpn_issue": "vpn",
            "email_issue": "email", "software_install": "software", "hardware_issue": "hardware",
            "network_issue": "network", "access_request": "access", "printer_issue": "printer",
            "ticket_status": "general", "report_request": "general", "other": "general"}
FIRST_AGENT = {"ticket_status": "ticket", "report_request": "analytics", "other": "supervisor"}
REASON = {
    "network_issue": "ağ sorunu diğer sorunlara yol açıyor olabilir, önce o",
    "vpn_issue": "VPN kesintisi e-posta/erişim sorunlarına yol açabilir, önce o",
}


def build_plan(intents: list[dict], start_id: int = 1, text: str = "",
               entities: list[dict] | None = None) -> list[PlanStep]:
    labels = [i["label"] for i in intents] or ["other"]
    if len(labels) > 1 and "other" in labels:
        labels.remove("other")
    ordered = sorted(dict.fromkeys(labels), key=lambda x: PRIORITY.get(x, 99))
    steps: list[PlanStep] = []
    for offset, intent in enumerate(ordered):
        agent = FIRST_AGENT.get(intent, "triage")
        steps.append(PlanStep(
            id=start_id + offset, intent=intent, agent=agent, text=text,
            entities=entities or [],
            stage="ticket" if agent == "ticket" else "triage",
            category=CATEGORY.get(intent, "general"),
            note=REASON.get(intent, "") if len(ordered) > 1 and offset == 0 else "",
        ))
    return steps


def next_step(plan: list[PlanStep]) -> PlanStep | None:
    for step in plan:
        if step["stage"] not in ("done", "feedback", "info"):
            return step
    return None


def update_step(plan: list[PlanStep], step_id: int, **changes) -> list[PlanStep]:
    return [{**s, **changes} if s["id"] == step_id else s for s in plan]


def describe(plan: list[PlanStep]) -> str:
    return " → ".join(f"{s['id']}. {s['intent']}" for s in plan)
