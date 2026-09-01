# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import os
from collections.abc import AsyncIterator, Callable
from uuid import UUID

from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner

from app.app_utils import services
from app.app_utils.a2a import attach_a2a_routes
from app.scout_schedule_models import (
    ScoutScheduleCreateRequest,
    ScoutScheduleListResponse,
    ScoutScheduleRecord,
)
from app.scout_schedule_repository import (
    DuplicateScheduleError,
    ScheduleNotFoundError,
    ScheduleTransitionError,
)
from app.scout_schedule_service import (
    ScheduleRegistrationError,
    ScoutScheduleService,
    build_scout_schedule_service,
)

load_dotenv()
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app(
    *,
    scout_service_factory: Callable[[], ScoutScheduleService] | None = None,
) -> FastAPI:
    service_factory = scout_service_factory or build_scout_schedule_service

    @contextlib.asynccontextmanager
    async def lifespan(api: FastAPI) -> AsyncIterator[None]:
        from app import scheduler_service as legacy_scheduler_service
        from app.agent import app as adk_app
        from app.agent import root_agent

        legacy_scheduler_owned = False
        scout_service: ScoutScheduleService | None = None
        scout_service_started = False
        try:
            if not legacy_scheduler_service.scheduler.running:
                legacy_scheduler_owned = True
                legacy_scheduler_service.scheduler.start()

            scout_service = service_factory()
            scout_service.start()
            scout_service_started = True
            api.state.scout_schedule_service = scout_service

            runner = Runner(
                app=adk_app,
                session_service=services.get_session_service(),
                artifact_service=services.get_artifact_service(),
                auto_create_session=True,
            )
            api.state.runner = runner
            api.state.agent_app_name = adk_app.name
            await attach_a2a_routes(
                api,
                agent=root_agent,
                runner=runner,
                task_store=InMemoryTaskStore(),
                rpc_path=f"/a2a/{adk_app.name}",
            )
            yield
        finally:
            try:
                if scout_service_started and scout_service is not None:
                    scout_service.shutdown()
            finally:
                if (
                    legacy_scheduler_owned
                    and legacy_scheduler_service.scheduler.running
                ):
                    legacy_scheduler_service.scheduler.shutdown(wait=True)

    api: FastAPI = get_fast_api_app(
        agents_dir=AGENT_DIR,
        web=True,
        artifact_service_uri=services.ARTIFACT_SERVICE_URI,
        allow_origins=allow_origins,
        session_service_uri=services.SESSION_SERVICE_URI,
        otel_to_cloud=os.getenv("INTEGRATION_TEST") != "TRUE",
        lifespan=lifespan,
    )
    api.title = "scheduling-agent"
    api.description = "Scheduling Agent APIs, including persistent Scout schedules."

    @api.post(
        "/v1/scout/schedules",
        response_model=ScoutScheduleRecord,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_scout_schedule(
        request: ScoutScheduleCreateRequest,
    ) -> ScoutScheduleRecord:
        service = _get_scout_service(api)
        try:
            return service.create_schedule(request)
        except DuplicateScheduleError:
            raise HTTPException(
                status_code=409,
                detail="An identical pending Scout schedule already exists.",
            ) from None
        except ScheduleRegistrationError:
            raise HTTPException(
                status_code=503,
                detail="The Scout schedule could not be registered.",
            ) from None

    @api.get(
        "/v1/scout/schedules",
        response_model=ScoutScheduleListResponse,
    )
    async def list_scout_schedules() -> ScoutScheduleListResponse:
        return _get_scout_service(api).list_schedules()

    @api.delete(
        "/v1/scout/schedules/{schedule_id}",
        response_model=ScoutScheduleRecord,
    )
    async def cancel_scout_schedule(schedule_id: UUID) -> ScoutScheduleRecord:
        service = _get_scout_service(api)
        try:
            return service.cancel_schedule(schedule_id)
        except ScheduleNotFoundError:
            raise HTTPException(status_code=404, detail="Schedule not found.") from None
        except ScheduleTransitionError:
            raise HTTPException(
                status_code=409,
                detail="Only a pending schedule may be cancelled.",
            ) from None

    return api


def _get_scout_service(api: FastAPI) -> ScoutScheduleService:
    service = getattr(api.state, "scout_schedule_service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="Scout scheduling service is not available.",
        )
    return service


app = create_app()


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("SCHEDULING_API_HOST", "0.0.0.0"),
        port=int(os.getenv("SCHEDULING_API_PORT", "8092")),
    )
