from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from .clients import RecipeClient
from .models import (
    ControlRunRequest,
    ControlRunResponse,
    ControlStepRequest,
    ControlStepState,
    InitialObservation,
)
from .logic import compute_step


@dataclass
class LoopState:
    commanded_x: float
    commanded_y: float
    perturb_x: float = 0.0
    perturb_y: float = 0.0


def _extract_spot(sim_data: dict[str, Any]) -> tuple[float, float, float | None]:
    return (
        float(sim_data["spot_center_x"]),
        float(sim_data["spot_center_y"]),
        float(sim_data["spot_rms_radius"]) if sim_data.get("spot_rms_radius") is not None else None,
    )


async def run_control_loop(request: ControlRunRequest, client: RecipeClient) -> ControlRunResponse:
    rng = random.Random(request.random_seed)

    control_payload: dict[str, Any] = {
        "algorithm": request.algorithm,
        "config": request.config.model_dump(),
        "target": request.target.model_dump(),
        "initial_coll": request.initial_coll.model_dump(),
        "max_steps": request.max_steps,
        "tolerance": request.tolerance,
        "random_seed": request.random_seed,
    }
    trial = await client.create_trial(request.experiment_id, control_payload)
    trial_id = str(trial["trial_id"])

    # Step 0: initial observation (not counted in max_steps)
    step0 = await client.execute_step(
        request.experiment_id,
        trial_id,
        request.initial_coll.coll_x,
        request.initial_coll.coll_y,
    )

    pre_x0, pre_y0, _ = _extract_spot(step0["sim_after_position"])
    post_x0, post_y0, post_rms0 = _extract_spot(step0["sim_after_bolt"])

    boot_correction_x = (request.target.spot_center_x - pre_x0) / request.config.spot_to_coll_scale_x
    boot_correction_y = (request.target.spot_center_y - pre_y0) / request.config.spot_to_coll_scale_y

    state = LoopState(
        commanded_x=request.initial_coll.coll_x + boot_correction_x,
        commanded_y=request.initial_coll.coll_y + boot_correction_y,
    )

    initial_observation = InitialObservation(
        step_index=int(step0["step_index"]),
        initial_coll_x=request.initial_coll.coll_x,
        initial_coll_y=request.initial_coll.coll_y,
        spot_pre_x=pre_x0,
        spot_pre_y=pre_y0,
        spot_post_x=post_x0,
        spot_post_y=post_y0,
        boot_correction_x=boot_correction_x,
        boot_correction_y=boot_correction_y,
    )

    # Default final values from step 0 in case max_steps=0
    final_post_x = post_x0
    final_post_y = post_y0
    final_post_rms = post_rms0
    final_distance = math.hypot(
        request.target.spot_center_x - final_post_x,
        request.target.spot_center_y - final_post_y,
    )
    converged = final_distance < request.tolerance

    last_step = step0
    steps_executed = 0

    for _ in range(request.max_steps):
        pre_x, pre_y, _ = _extract_spot(last_step["sim_after_position"])
        post_x_prev, post_y_prev, _ = _extract_spot(last_step["sim_after_bolt"])

        step_req = ControlStepRequest(
            algorithm=request.algorithm,
            config=request.config,
            state=ControlStepState(
                target_spot_center_x=request.target.spot_center_x,
                target_spot_center_y=request.target.spot_center_y,
                current_coll_x=state.commanded_x,
                current_coll_y=state.commanded_y,
                spot_pre_x=pre_x + state.perturb_x,
                spot_pre_y=pre_y + state.perturb_y,
                spot_post_x=post_x_prev,
                spot_post_y=post_y_prev,
                step_index=steps_executed,
                history=[],
            ),
        )
        action = compute_step(step_req, tolerance=request.tolerance)

        state.commanded_x = action.next_coll_x
        state.commanded_y = action.next_coll_y

        step_result = await client.execute_step(
            request.experiment_id,
            trial_id,
            state.commanded_x,
            state.commanded_y,
        )
        steps_executed += 1
        last_step = step_result

        final_post_x, final_post_y, final_post_rms = _extract_spot(step_result["sim_after_bolt"])
        final_distance = math.hypot(
            request.target.spot_center_x - final_post_x,
            request.target.spot_center_y - final_post_y,
        )
        converged = final_distance < request.tolerance
        if converged:
            break

        # Release-time perturbation for next cycle pre-spot
        state.perturb_x = rng.gauss(0.0, request.config.release_perturbation.std_x)
        state.perturb_y = rng.gauss(0.0, request.config.release_perturbation.std_y)

    await client.complete_trial(request.experiment_id, trial_id)

    return ControlRunResponse(
        trial_id=trial_id,
        algorithm=request.algorithm,
        converged=converged,
        steps=steps_executed,
        initial_observation=initial_observation,
        final_spot_center_x=final_post_x,
        final_spot_center_y=final_post_y,
        final_spot_rms_radius=final_post_rms,
        final_distance=final_distance,
    )
