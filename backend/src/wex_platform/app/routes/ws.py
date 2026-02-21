"""WebSocket handler for real-time chat with AI agents and admin dashboard."""

import json
import logging
import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from wex_platform.infra.database import async_session
from wex_platform.domain.models import (
    Warehouse,
    TruthCore,
    ContextualMemory,
    SupplierAgreement,
    ToggleHistory,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages WebSocket connections with group support.

    Connections can belong to named groups (e.g. "admin", "activation_<id>").
    Broadcasting targets a specific group so unrelated clients are not affected.
    """

    def __init__(self):
        # client_id -> WebSocket (for direct messaging)
        self.active_connections: dict[str, WebSocket] = {}
        # group_name -> set of client_ids
        self.groups: dict[str, set[str]] = {}

    async def connect(
        self, websocket: WebSocket, client_id: str, group: Optional[str] = None
    ):
        """Accept a WebSocket and optionally add it to a group."""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        if group:
            self.add_to_group(client_id, group)

    def add_to_group(self, client_id: str, group: str):
        """Add a client to a named group."""
        if group not in self.groups:
            self.groups[group] = set()
        self.groups[group].add(client_id)

    def disconnect(self, client_id: str):
        """Remove a client from all groups and drop its connection."""
        self.active_connections.pop(client_id, None)
        for group_members in self.groups.values():
            group_members.discard(client_id)

    async def send_json(self, client_id: str, data: dict):
        """Send JSON to a specific client."""
        ws = self.active_connections.get(client_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                logger.warning("Failed to send to client %s, removing", client_id)
                self.disconnect(client_id)

    async def broadcast_to_group(self, group: str, data: dict):
        """Broadcast a JSON message to every client in a group."""
        client_ids = list(self.groups.get(group, set()))
        disconnected: list[str] = []
        for cid in client_ids:
            ws = self.active_connections.get(cid)
            if ws:
                try:
                    await ws.send_json(data)
                except Exception:
                    logger.warning("Broadcast failed for %s, removing", cid)
                    disconnected.append(cid)
        for cid in disconnected:
            self.disconnect(cid)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Admin dashboard WebSocket
# ---------------------------------------------------------------------------

ADMIN_EVENT_TYPES = {
    "deal_update",
    "match_created",
    "agent_activity",
    "toggle_update",
    "ledger_entry",
}


async def broadcast_admin_event(event_type: str, data: dict):
    """Push a real-time event to all connected admin dashboard clients.

    This function is safe to call from anywhere in the backend (route
    handlers, agents, background tasks, etc.).

    Args:
        event_type: One of the ADMIN_EVENT_TYPES constants.
        data: Arbitrary JSON-serialisable payload.
    """
    if event_type not in ADMIN_EVENT_TYPES:
        logger.warning("Unknown admin event type: %s", event_type)
    message = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await manager.broadcast_to_group("admin", message)


@router.websocket("/ws/admin")
async def admin_dashboard(websocket: WebSocket):
    """WebSocket endpoint for admin dashboard real-time updates.

    Clients simply connect; the server pushes events as they occur.
    Supported incoming messages:
        {"type": "ping"}  ->  server replies {"type": "pong"}
    """
    client_id = f"admin_{uuid_mod.uuid4().hex[:8]}"
    await manager.connect(websocket, client_id, group="admin")
    logger.info("Admin client connected: %s", client_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            # Handle ping / keep-alive
            if msg.get("type") == "ping":
                await manager.send_json(client_id, {"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info("Admin client disconnected: %s", client_id)
    except Exception as e:
        logger.error("Admin WebSocket error for %s: %s", client_id, e)
        manager.disconnect(client_id)


@router.websocket("/ws/activation/{warehouse_id}")
async def activation_chat(websocket: WebSocket, warehouse_id: str):
    """WebSocket endpoint for activation agent chat.

    Protocol:
    - Client sends: {"message": "owner's text"}
    - Server sends: {"type": "agent_response", "data": {...}}
    - Server sends: {"type": "truth_core_update", "data": {...}} when fields are extracted
    - Server sends: {"type": "pricing_guidance", "data": {...}} at step 5
    - Server sends: {"type": "activation_complete", "data": {...}} when done
    """
    client_id = f"activation_{warehouse_id}"
    await manager.connect(websocket, client_id, group=f"activation_{warehouse_id}")

    # Initialize conversation state
    conversation_history: list[dict] = []
    current_step = 1
    extracted_fields: dict = {}
    building_data: Optional[dict] = None

    try:
        # Load building data from DB
        async with async_session() as session:
            warehouse = await session.get(Warehouse, warehouse_id)
            if warehouse:
                building_data = {
                    "address": warehouse.address,
                    "city": warehouse.city,
                    "state": warehouse.state,
                    "building_size_sqft": warehouse.building_size_sqft,
                    "year_built": warehouse.year_built,
                    "construction_type": warehouse.construction_type,
                }
                # Load existing truth core if any
                result = await session.execute(
                    select(TruthCore).where(TruthCore.warehouse_id == warehouse_id)
                )
                truth_core = result.scalar_one_or_none()
                if truth_core:
                    building_data.update({
                        "dock_doors_receiving": truth_core.dock_doors_receiving,
                        "drive_in_bays": truth_core.drive_in_bays,
                        "parking_spaces": truth_core.parking_spaces,
                        "clear_height_ft": truth_core.clear_height_ft,
                        "has_office_space": truth_core.has_office_space,
                        "has_sprinkler": truth_core.has_sprinkler,
                    })

                # Load memories
                mem_result = await session.execute(
                    select(ContextualMemory).where(
                        ContextualMemory.warehouse_id == warehouse_id
                    )
                )
                memories = mem_result.scalars().all()
                building_data["memories"] = [m.content for m in memories]

        # Send initial message
        from wex_platform.agents.activation_agent import ActivationAgent

        agent = ActivationAgent()

        initial = await agent.generate_initial_message(building_data=building_data)
        if initial.ok:
            try:
                initial_data = (
                    json.loads(initial.data)
                    if isinstance(initial.data, str)
                    else initial.data
                )
            except (json.JSONDecodeError, TypeError):
                initial_data = {"message": initial.data, "current_step": 1}

            await websocket.send_json({
                "type": "agent_response",
                "data": initial_data,
            })

            if building_data:
                await websocket.send_json({
                    "type": "building_data",
                    "data": building_data,
                })

        # Chat loop
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")

            if not user_message:
                continue

            # Add user message to history
            conversation_history.append({"role": "user", "content": user_message})

            # Check if we need pricing at step 5
            pricing_data = None
            if (
                current_step >= 4
                and "supplier_rate_per_sqft" not in extracted_fields
            ):
                # Get pricing guidance
                try:
                    from wex_platform.agents.pricing_agent import PricingAgent

                    pricing_agent = PricingAgent()

                    pricing_result = await pricing_agent.get_rate_guidance(
                        warehouse_data={**(building_data or {}), **extracted_fields},
                        contextual_memories=(
                            building_data.get("memories", [])
                            if building_data
                            else []
                        ),
                    )
                    if pricing_result.ok:
                        pricing_data = pricing_result.data
                        await websocket.send_json({
                            "type": "pricing_guidance",
                            "data": pricing_data,
                        })
                except Exception as e:
                    logger.warning("Pricing guidance unavailable: %s", e)

            # Process with activation agent
            result = await agent.process_message(
                warehouse_id=warehouse_id,
                user_message=user_message,
                conversation_history=conversation_history,
                building_data=building_data,
                current_step=current_step,
                extracted_fields=extracted_fields,
            )

            if result.ok:
                response_data = result.data

                # Update state
                current_step = response_data.get("current_step", current_step)
                extracted_fields = response_data.get(
                    "extracted_fields", extracted_fields
                )

                # Add agent response to history
                agent_msg = response_data.get("message", "")
                conversation_history.append(
                    {"role": "model", "content": agent_msg}
                )

                # Send response
                await websocket.send_json({
                    "type": "agent_response",
                    "data": response_data,
                })

                # Send truth core update if fields were extracted
                if extracted_fields:
                    await websocket.send_json({
                        "type": "truth_core_update",
                        "data": extracted_fields,
                    })

                # Check if activation is complete
                if response_data.get("all_steps_complete"):
                    # Create truth core in DB
                    await _finalize_activation(
                        warehouse_id, extracted_fields, conversation_history
                    )

                    await websocket.send_json({
                        "type": "activation_complete",
                        "data": {
                            "warehouse_id": warehouse_id,
                            "truth_core": extracted_fields,
                            "message": "Warehouse activated successfully!",
                        },
                    })
            else:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": result.error},
                })

    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info("Client disconnected: %s", client_id)
    except Exception as e:
        logger.error("WebSocket error for %s: %s", client_id, e)
        manager.disconnect(client_id)


async def _finalize_activation(
    warehouse_id: str,
    extracted_fields: dict,
    conversation: list,
):
    """Create/update truth core and related records after activation completes."""
    async with async_session() as session:
        # Check for existing truth core
        result = await session.execute(
            select(TruthCore).where(TruthCore.warehouse_id == warehouse_id)
        )
        truth_core = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if truth_core:
            # Update existing
            for key, value in extracted_fields.items():
                if hasattr(truth_core, key) and value is not None:
                    setattr(truth_core, key, value)
            truth_core.activation_status = "on"
            truth_core.toggled_at = now
        else:
            # Build kwargs for creation, only setting attributes that exist on the model
            extra_kwargs = {}
            skip_keys = {
                "min_sqft",
                "max_sqft",
                "activity_tier",
                "supplier_rate_per_sqft",
                "constraints",
            }
            for k, v in extracted_fields.items():
                if k not in skip_keys and hasattr(TruthCore, k) and v is not None:
                    extra_kwargs[k] = v

            truth_core = TruthCore(
                id=str(uuid_mod.uuid4()),
                warehouse_id=warehouse_id,
                min_sqft=extracted_fields.get("min_sqft", 0),
                max_sqft=extracted_fields.get("max_sqft", 0),
                activity_tier=extracted_fields.get("activity_tier", "storage_only"),
                supplier_rate_per_sqft=extracted_fields.get(
                    "supplier_rate_per_sqft", 0
                ),
                constraints=extracted_fields.get("constraints", {}),
                activation_status="on",
                toggled_at=now,
                **extra_kwargs,
            )
            session.add(truth_core)

        # Flush to ensure truth_core.id is available
        await session.flush()

        # Create toggle history
        toggle = ToggleHistory(
            id=str(uuid_mod.uuid4()),
            warehouse_id=warehouse_id,
            previous_status="off",
            new_status="on",
            reason="Activation completed via chat",
        )
        session.add(toggle)

        # Create supplier agreement
        agreement = SupplierAgreement(
            id=str(uuid_mod.uuid4()),
            warehouse_id=warehouse_id,
            truth_core_id=truth_core.id,
            status="active",
            terms_json=extracted_fields,
            signed_at=now,
        )
        session.add(agreement)

        await session.commit()

    # Extract memories from conversation (non-blocking)
    try:
        from wex_platform.agents.memory_agent import MemoryAgent

        memory_agent = MemoryAgent()
        mem_result = await memory_agent.extract_from_conversation(
            conversation=conversation,
            warehouse_id=warehouse_id,
        )
        if mem_result.ok and isinstance(mem_result.data, list):
            async with async_session() as session:
                for mem in mem_result.data:
                    cm = ContextualMemory(
                        id=str(uuid_mod.uuid4()),
                        warehouse_id=warehouse_id,
                        memory_type=mem.get(
                            "memory_type", "feature_intelligence"
                        ),
                        content=mem.get("content", ""),
                        source=mem.get("source", "activation_chat"),
                        confidence=mem.get("confidence", 0.8),
                    )
                    session.add(cm)
                await session.commit()
    except Exception as e:
        logger.error("Memory extraction failed: %s", e)
