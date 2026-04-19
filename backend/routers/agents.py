"""Agent system + Vibe Coder + Agent Store endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from models.agent import AgentRecord, AgentRun, AgentInstall, AgentCreate, AgentResponse, AgentStatus, UserLayout
from models.user import UserRecord
from services.agent_runtime import run_agent
from services.vibe_coder_v2 import process_vibe_request
from services.auth import require_user

router = APIRouter(tags=["agents"])


async def get_db():
    from main import async_session
    async with async_session() as session:
        yield session


# --- Agents ---

@router.post("/api/agents/create", response_model=AgentResponse)
async def create_agent(req: AgentCreate, user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """Create a new agent."""
    agent = AgentRecord(
        user_id=user.id,
        name=req.name,
        description=req.description,
        trigger=req.trigger,
        steps=req.steps,
        status=AgentStatus.active,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return AgentResponse.model_validate(agent)


@router.get("/api/agents/")
async def list_agents(user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """List user's agents."""
    result = await db.execute(
        select(AgentRecord).where(AgentRecord.user_id == user.id)
    )
    agents = result.scalars().all()
    return [AgentResponse.model_validate(a) for a in agents]


@router.get("/api/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """Get agent details. Owner only (or published store agent)."""
    agent = await db.get(AgentRecord, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.user_id != user.id and not agent.is_published:
        raise HTTPException(status_code=403, detail="Not your agent")
    return AgentResponse.model_validate(agent)


@router.post("/api/agents/{agent_id}/run")
async def run_agent_endpoint(agent_id: str, user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """Run an agent manually. Owner only."""
    agent = await db.get(AgentRecord, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your agent")

    result = await run_agent(
        agent_id=agent_id,
        user_id=user.id,
        steps=agent.steps,
        trigger_event={"type": "manual"},
        db=db,
    )
    return result


@router.get("/api/agents/{agent_id}/runs")
async def list_runs(agent_id: str, user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """List run history for an agent. Owner only."""
    agent = await db.get(AgentRecord, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your agent")
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.agent_id == agent_id)
        .order_by(AgentRun.started_at.desc())
        .limit(20)
    )
    runs = result.scalars().all()
    return [
        {
            "id": r.id,
            "status": r.status.value,
            "steps_completed": len(r.steps_log or []),
            "started_at": r.started_at.isoformat(),
            "error": r.error,
        }
        for r in runs
    ]


# --- Agent Store ---

@router.get("/api/store/agents")
async def browse_store(
    category: str = None,
    sort: str = "popular",
    db: AsyncSession = Depends(get_db),
):
    """Browse published agents in the store."""
    query = select(AgentRecord).where(AgentRecord.is_published == True)
    if sort == "popular":
        query = query.order_by(AgentRecord.install_count.desc())
    elif sort == "rating":
        query = query.order_by(AgentRecord.rating.desc())
    else:
        query = query.order_by(AgentRecord.created_at.desc())

    result = await db.execute(query.limit(50))
    agents = result.scalars().all()

    return [
        {
            "id": a.id,
            "name": a.name,
            "description": a.description,
            "installs": a.install_count,
            "rating": a.rating,
            "price": a.price,
            "creator_id": a.user_id,
        }
        for a in agents
    ]


@router.post("/api/store/agents/{agent_id}/install")
async def install_agent(agent_id: str, user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """Install an agent from the store."""
    agent = await db.get(AgentRecord, agent_id)
    if not agent or not agent.is_published:
        raise HTTPException(status_code=404, detail="Agent not found in store")

    install = AgentInstall(agent_id=agent_id, user_id=user.id)
    db.add(install)
    agent.install_count += 1
    await db.commit()

    return {"installed": True, "agent_id": agent_id}


# --- Vibe Coder ---

@router.post("/api/vibe/customize")
async def customize_layout(
    prompt: str = Query(..., description="Natural language customization request"),
    user: UserRecord = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Customize app layout via natural language."""
    # Get current layout
    result = await db.execute(
        select(UserLayout).where(UserLayout.user_id == user.id)
    )
    layout = result.scalar_one_or_none()
    current_config = layout.layout_config if layout else None

    # Process vibe request
    new_config = await process_vibe_request(prompt, current_config)

    if layout:
        layout.layout_config = new_config
        layout.prompt_history = (layout.prompt_history or []) + [prompt]
        flag_modified(layout, "layout_config")
        flag_modified(layout, "prompt_history")
    else:
        layout = UserLayout(
            user_id=user.id,
            layout_config=new_config,
            prompt_history=[prompt],
        )
        db.add(layout)

    await db.commit()
    return {"layout": new_config}


@router.get("/api/vibe/layout")
async def get_layout(user: UserRecord = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """Get user's current layout config."""
    result = await db.execute(
        select(UserLayout).where(UserLayout.user_id == user.id)
    )
    layout = result.scalar_one_or_none()
    if not layout:
        from services.vibe_coder_v2 import DEFAULT_CONFIG
        return {"layout": DEFAULT_CONFIG}
    return {"layout": layout.layout_config}
