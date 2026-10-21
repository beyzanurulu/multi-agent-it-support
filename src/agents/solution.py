"""Solution agent.

Week 1 placeholder: proposes a canned answer per intent. Week 2 replaces this
with ChromaDB RAG search through the FastMCP `search_knowledge_base` tool.
"""

from langchain_core.messages import AIMessage

from src.agents.state import AgentState

CANNED_SOLUTIONS = {
    "password_reset": "Self-servis portalından (https://reset.example.local) şifrenizi "
    "sıfırlayabilirsiniz. Hesap kilitliyse 15 dakika bekleyip tekrar deneyin.",
    "software_install": "Şirket yazılım merkezinden (Software Center) uygulamayı "
    "seçip 'Yükle'ye tıklayın. Lisanslı yazılımlar için yönetici onayı gerekir.",
    "network": "VPN istemcisini yeniden başlatın, internet bağlantınızı kontrol edin ve "
    "sertifikanızın güncel olduğundan emin olun.",
    "email": "Outlook'u güvenli modda açın (outlook.exe /safe) ve profilinizi onarın.",
    "hardware": "Cihazı yeniden başlatın ve kabloları kontrol edin.",
    "access_request": "Erişim talebinizi yöneticinizin onayıyla IAM portalından iletin.",
}


def solution_node(state: AgentState) -> dict:
    solution = CANNED_SOLUTIONS.get(state.get("intent", ""))
    if solution is None:
        # Nothing to propose — let the supervisor hand over to the ticket agent.
        return {"current_agent": "solution", "proposed_solution": "", "solution_accepted": False,
                "kb_results": [], "human_requested": True}
    return {
        "current_agent": "solution",
        "kb_results": [],
        "proposed_solution": solution,
        "messages": [AIMessage(content=solution, name="solution")],
    }
