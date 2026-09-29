#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FastKaggricultureEnv — 100% faithful, framework-free driver for the OFFICIAL
Kaggriculture interpreter (kaggle-environments 1.32.7).

WHY THIS EXISTS
===============
`kaggle_environments.make("kaggriculture").step()` spends most of its time in
the generic framework wrapper, not the game:

  measured (720-turn game, pass actions):
    official env.step ........... 1.01 s/game
    interpreter called directly .. 0.03 s/game   (33x faster)

Per step the framework does, on top of the interpreter:
  1. structify(state) — full recursive rebuild of the whole game state into
     Struct objects — TWICE per step (in and out of __loop_through_interpreter).
  2. process_schema(action) — jsonschema validation of both players' actions.
  3. StringIO + redirect_stdout/redirect_stderr context managers per step.
  4. replay `steps` list / logs bookkeeping.

This module drives the very same interpreter function
(`kaggle_environments.envs.kaggriculture.kaggriculture.interpreter`) on plain
dicts with the same step/status bookkeeping as `kaggle_environments.Core.step`,
so the game is faithful BY CONSTRUCTION: same code, same RNG, same rules.
Everything skipped is framework overhead only. Verified bit-exact against the
official path by scripts/test_fast_env_parity.py (deep state compare on every
step, fresh seeds, both seats, market-heavy action streams).

SEED SEMANTICS (matches the real competition)
=============================================
On Kaggle every episode runs on a FRESH env object, so a fresh episode seed is
resolved from configuration/entropy. `reset()` here clears `env.info["seed"]`
to reproduce exactly that (fresh seed per episode). NOTE: the official
`Environment` object *reused* across episodes keeps `env.info["seed"]` forever
(resolve_episode_seed reads env.info first), so setting
`configuration["seed"]` on a reused official env does NOT change the seed —
that bug silently pinned every "fresh" training episode to the first seed
(verified in scripts/check_seed_bug.py).

API (subset used by real_env_day_wrapper / calibrate / tests):
    env = FastKaggricultureEnv(configuration={"seed": 123})
    env.reset(2)
    env.state[seat].observation       # Struct: dict AND attribute access
    env.step([action0, action1])      # action = {"farmer":..., "hands":..., "market":...}
    env.done, env.configuration, env.info
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from kaggle_environments.utils import Struct
from kaggle_environments.envs.kaggriculture import kaggriculture as _KG

__all__ = ["FastKaggricultureEnv", "FastKaggrEnvPy", "FastKaggrEnvCpp",
           "assert_official_env", "cpp_available"]


def assert_official_env():
    """Hard-fail unless the installed env has 1.32.7 competition semantics."""
    assert _KG.ANIMALS["COW"]["cost"] == 400, "OLD ENV: COW cost != 400"
    assert _KG.MARKET_PARAMS["CARROT"]["below_func"] == "hinge", "OLD ENV: CARROT"
    assert _KG.MARKET_PARAMS["MELON"]["above_target"] == 3.6, "OLD ENV: MELON"
    assert _KG.MARKET_PARAMS["STRAWBERRY"]["above_target"] == 1.6, "OLD ENV: STRAW"
    return True


class _State:
    """Interpreter-facing per-agent state. The official framework uses a
    Struct here; the interpreter only touches these four fields (status,
    reward, action, observation), so slots are equivalent and faster."""
    __slots__ = ("observation", "action", "status", "reward")


class FastKaggrEnvPy:
    """Official interpreter, driven directly (pure Python). 1:1 trajectory
    parity with kaggle_environments.make("kaggriculture") on the same seed.
    Kept as the reference/fallback implementation."""

    id = "kaggriculture"

    def __init__(self, configuration=None, debug=False):
        assert_official_env()
        spec_cfg = _KG.specification.get("configuration", {})
        base = {}
        for k, v in spec_cfg.items():
            try:
                base[k] = v.get("default")
            except Exception:
                base[k] = v
        if configuration:
            base.update(dict(configuration))
        self.configuration = Struct(**base)
        self.info = {}
        self.debug = debug
        self.state = None
        self.steps = []
        self.logs = []

    # ------------------------------------------------------------------ done
    @property
    def done(self) -> bool:
        """Mirror of Core.done: True when no agent is ACTIVE."""
        return all(s.status != "ACTIVE" for s in self.state)

    # ----------------------------------------------------------------- reset
    def reset(self, num_agents: int | None = None):
        """Fresh episode. Mirrors Core.reset + fresh per-episode seed
        (clears info['seed'] so configuration['seed'] / entropy is used)."""
        if num_agents is None:
            num_agents = _KG.specification["agents"][0]
        self.info = {}                     # fresh episode => fresh seed (Kaggle semantics)
        states = []
        for i in range(num_agents):
            s = _State()
            s.observation = Struct(player=i, farms=[], market=None, town=None,
                                   private=None, day=0, hour=0, step=0)
            s.action = None
            # Core.reset builds fresh states from the schema, whose status
            # default is ACTIVE ("status": {"defaults": ["ACTIVE", ...]}).
            s.status = "ACTIVE"
            s.reward = 0
            states.append(s)
        # Core.reset: capture statuses, force INACTIVE, run interpreter
        # (its `if env.done` guard sits BELOW the init branch, so init runs),
        # then restore the captured statuses.
        for s in states:
            s.status = "INACTIVE"
        _KG.interpreter(states, self)
        # Core.__loop_through_interpreter: step = 0 if self.done else len(steps).
        # During reset statuses are INACTIVE => done path => step 0.
        # The official runner (__get_shared_state) also injects `step` into
        # every seat's obs at call time — mirror it so agents on seat 1 see
        # the same step counter they would see under env.run().
        for s in states:
            s.observation.step = 0
        for s in states:
            s.status = "ACTIVE"
        self.state = states
        self.steps = [self.state]
        return self.state

    # ------------------------------------------------------------------ step
    def step(self, actions, logs=None):
        """One official turn. actions: [action_per_agent]. Same bookkeeping
        as Core.step: interpreter -> step counter -> DONE at episodeSteps-1."""
        if self.done:
            raise RuntimeError("Environment done, reset required.")
        if not actions or len(actions) != len(self.state):
            raise ValueError("%d actions required." % len(self.state))

        # Core.step builds action_state = [{**state_i, "action": ...}]. The
        # official framework additionally runs jsonschema validation on each
        # action (type=object only — the inner structure is NOT validated;
        # the interpreter silently no-ops malformed ops). The adapter only
        # emits well-formed actions, so we assign them directly on the state
        # objects (the interpreter never reads anything but action/status/
        # reward/observation, all present).
        was_done = all(s.status != "ACTIVE" for s in self.state)
        n_recorded = len(self.steps)
        for i, action in enumerate(actions):
            s = self.state[i]
            if isinstance(action, BaseException):
                s.action = None
                s.status = "ERROR"
            else:
                s.action = action

        new_state = _KG.interpreter(self.state, self)

        # Core.__loop_through_interpreter step-line (state[0]), mirrored on
        # every seat: the official runner injects step into each agent's obs
        # via __get_shared_state, so seat-1 agents see the live counter.
        new_step = 0 if was_done else n_recorded
        for s in new_state:
            s.observation.step = new_step
        obs0 = new_state[0].observation

        # Core.step: max steps reached -> mark ACTIVE/INACTIVE as DONE.
        if obs0.step >= self.configuration.episodeSteps - 1:
            for s in new_state:
                if s.status in ("ACTIVE", "INACTIVE"):
                    s.status = "DONE"

        self.state = new_state
        self.steps.append(self.state)
        return self.state


# ---------------------------------------------------------------------------
# C++ backend (v3) — kaggr_core.FastEnv wrapped in the exact same API.
# The interpreter (game rules + RNG) is the SAME code path that the parity
# gate verified bit-identical to the official env (scripts/test_cpp_parity.py
# GATE 1). Used automatically when the extension builds; pure-Python class
# above remains the fallback and reference.
# ---------------------------------------------------------------------------

_CPP = None
_CPP_TRIED = False


def _load_cpp():
    global _CPP, _CPP_TRIED
    if _CPP is None and not _CPP_TRIED:
        _CPP_TRIED = True
        try:
            import fast_env_build
            _CPP = fast_env_build.load(verbose=True)
        except Exception:
            _CPP = None
    return _CPP


def cpp_available() -> bool:
    return _load_cpp() is not None


class _CppState:
    """Mirrors the framework state object for one agent (status/reward are
    settable — calibrate_official.py marks crashed agents ERROR afterwards)."""

    def __init__(self, env, seat: int):
        self._env = env
        self._seat = int(seat)

    @property
    def observation(self):
        return Struct(**self._env._cpp.observation(self._seat))

    @property
    def status(self):
        ov = self._env._status_override.get(self._seat)
        if ov is not None:
            return ov
        s0, _r0, s1, _r1 = self._env._cpp.status_reward()
        return s0 if self._seat == 0 else s1

    @status.setter
    def status(self, value):
        self._env._status_override[self._seat] = value

    @property
    def reward(self):
        ov = self._env._reward_override.get(self._seat)
        if ov is not None:
            return ov
        _s0, r0, _s1, r1 = self._env._cpp.status_reward()
        return r0 if self._seat == 0 else r1

    @reward.setter
    def reward(self, value):
        self._env._reward_override[self._seat] = value

    @property
    def action(self):
        return None


class FastKaggrEnvCpp:
    """C++ FastKaggricultureEnv — same API, ~100x faster per step.

    The observation is built as a plain-dict tree in the official structure
    (wrapped in a Struct for attribute access) only when .state[seat]
    .observation is read — the day-wrapper no longer touches this path at
    all (it uses kaggr_core.DayEngine directly).
    """

    id = "kaggriculture"

    def __init__(self, configuration=None, debug=False):
        core = _load_cpp()
        if core is None:
            raise RuntimeError("kaggr_core unavailable (see fast_env_build.py)")
        self._cpp = core.FastEnv()
        self.configuration = {"episodeSteps": 720, "seed": None}
        if configuration:
            self.configuration.update(dict(configuration))
        self.info = {}
        self.debug = debug
        self.steps = []
        self.state = None   # mirrors FastKaggrEnvPy: created on first reset()
        self._status_override = {}
        self._reward_override = {}

    @property
    def done(self) -> bool:
        return self._cpp.done

    def reset(self, num_agents: int | None = None):
        # FastKaggrEnv.reset semantics: fresh episode -> info cleared, the
        # configuration seed (if set) is consumed and pinned to info.
        self.info = {}
        self._status_override = {}
        self._reward_override = {}
        seed = self.configuration.get("seed")
        resolved = self._cpp.reset(seed if seed is not None else None)
        self.configuration["seed"] = None
        self.info["seed"] = resolved
        self.state = [_CppState(self, 0), _CppState(self, 1)]
        self.steps = [self.state]
        return self.state

    def step(self, actions, logs=None):
        if self.done:
            raise RuntimeError("Environment done, reset required.")
        if not actions or len(actions) != len(self.state):
            raise ValueError("%d actions required." % len(self.state))
        self._cpp.step(actions)
        self.steps.append(self.state)
        return self.state



def _select_default_env_class():
    """Measurement backend is hard-pinned to pure-Python (Phase 0 / BUG-2):
    the C++ engine diverges from the Python driver on the same seed+agent
    (measured 111,923 py vs 111,914 cpp on seed 200001) and is NOT faster once
    the real agent drives it (7.48s vs 7.36s per game). It stays available for
    an explicit KAGGR_WORKER_BACKEND=cpp opt-in, but is never selected
    silently, so every delta this rig measures stays reproducible."""
    if os.environ.get("KAGGR_WORKER_BACKEND") == "cpp":
        try:
            if cpp_available():
                return FastKaggrEnvCpp
        except Exception:
            pass
    return FastKaggrEnvPy


# Import-time selection: every existing consumer of
# `from fast_kaggr_env import FastKaggricultureEnv` gets the fastest available
# engine with the identical API (parity-gated by scripts/test_cpp_parity.py).
FastKaggricultureEnv = _select_default_env_class()

