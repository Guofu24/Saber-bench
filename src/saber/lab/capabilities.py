"""Executable role capabilities; the planner and executor use the same registry."""

CLIENT = {
    "login",
    "browse",
    "read_document",
    "write_document",
    "share",
    "read_messages",
    "windows_work",
    "windows_job_status",
}
RED = {
    "login",
    "browse",
    "read_document",
    "collect",
    "share",
    "read_messages",
    "windows_recon",
    "windows_failed_logon",
    "windows_job_status",
}
READ = {
    "query_events",
    "query_siem",
    "investigate",
    "share",
    "read_messages",
    "windows_job_status",
    "list_samples",
    "tool_status",
    "analysis_status",
    "soar_status",
    "run_playbook",
}
SPECIALIST = {
    "lead": {"assign_case", "review_cases"},
    "monitor": {"triage_cases"},
    "hunter": {"hunt"},
    "dfir": {"export_case", "timeline", "windows_collect_evidence", "analyze_sample"},
    "ir": {"contain", "release", "contain_domain_user"},
    "content": {"evaluate_rule", "publish_rule", "patch", "unpatch"},
    "malware": {"analyze_evidence", "analyze_sample"},
    "network": {"network_hunt", "analyze_sample"},
    "intel": {"correlate_indicator"},
    "platform": {"sensor_health", "windows_inventory"},
    "identity": {"identity_hunt"},
    "recovery": {"verify_recovery"},
}
ARTIFACTS = (
    "browser.png",
    "read-document.txt",
    "collected.txt",
    "evidence.json",
    "analysis.json",
    "case-evidence.json",
    "case-timeline.json",
    "rule-evaluation.json",
)
TOOLS = {"client": CLIENT, "red": RED, "blue": READ | set().union(*SPECIALIST.values())}


def allowed(team: str, role: str, specialties: tuple[str, ...] = ()) -> set[str]:
    if team != "blue":
        return set(TOOLS[team])
    result = set(READ)
    for name in (role, *specialties):
        result.update(SPECIALIST[name])
    if role == "lead":
        result.update({"contain", "release", "patch", "unpatch", "contain_domain_user"})
    return result
