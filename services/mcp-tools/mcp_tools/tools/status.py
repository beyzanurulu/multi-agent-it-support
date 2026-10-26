from mcp_tools.db import get_pool


async def check_system_status(service_name: str) -> dict:
    """Operational status of a corporate service (vpn, email, wifi, sso, fileserver, erp...)."""
    async with get_pool().connection() as conn:
        row = await (await conn.execute(
            "SELECT service, status, note, updated_at::text AS updated_at "
            "FROM system_status WHERE service = %s", (service_name.lower(),),
        )).fetchone()
    return row or {"service": service_name.lower(), "status": "unknown"}
