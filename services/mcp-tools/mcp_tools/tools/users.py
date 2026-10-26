from mcp_tools.db import get_pool


async def get_user_info(user_id: str) -> dict:
    """User profile (department, role, VIP) and their 10 most recent tickets."""
    async with get_pool().connection() as conn:
        user = await (await conn.execute(
            "SELECT u.id, u.full_name, u.role, u.vip, d.name AS department "
            "FROM users u LEFT JOIN departments d ON d.id = u.department_id WHERE u.id = %s",
            (user_id,),
        )).fetchone()
        if user is None:
            return {"id": user_id, "found": False, "tickets": []}
        tickets = await (await conn.execute(
            "SELECT ticket_no, title, status, severity, created_at::text AS created_at "
            "FROM tickets WHERE user_id = %s ORDER BY created_at DESC LIMIT 10", (user_id,),
        )).fetchall()
    return {**user, "found": True, "tickets": tickets}
