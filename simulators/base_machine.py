"""
base_machine.py

Shared base class for every simulated machine on the floor (hi-pot tester,
punch press, CNC panel fab, torque station, paint oven).

WHAT LIVES HERE (shared, generic across all machines):
  - Identity, state, calibration/wear counters, uptime/downtime tracking
  - The health-sampling contract (time-driven, periodic, independent of
    production activity)

WHAT DOES NOT LIVE HERE (machine-specific, defined in each subclass):
  - The actual production event (a hi-pot test, a punch stroke, a fastening
    cycle...) -- these have genuinely different shapes and inputs per
    machine, so each subclass defines its own event method
    (e.g. run_test_cycle, run_punch_cycle) rather than forcing a fake
    shared "run_cycle()" signature.
  - The specific telemetry values that make up "health" for that machine
    (ramp time vs. hydraulic pressure vs. spindle load...). Subclasses
    supply these through _collect_metrics().
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional


class MachineState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    FAULT = "FAULT"
    DOWN = "DOWN"          # e.g. awaiting calibration/maintenance
    CALIBRATING = "CALIBRATING"


class SelfCheckStatus(Enum):
    OK = "OK"
    WARN = "WARN"
    FAULT = "FAULT"


@dataclass
class MachineHealth:
    """
    Generic health envelope, shared shape across every machine.

    `metrics` is intentionally a free-form dict rather than a fixed set of
    fields, because each machine's real telemetry is different (a hi-pot
    tester reports ramp_time_actual_s, a punch press reports
    hydraulic_pressure_psi, etc). This mirrors how real industrial
    telemetry is usually structured -- a common envelope (who, when, is
    it healthy) wrapping a machine-specific payload of tags/metrics --
    similar in spirit to how MQTT Sparkplug B or OPC-UA separate metadata
    from the actual tag values.
    """
    reading_id: str
    station_id: str
    timestamp: str
    cycles_since_calibration: int
    last_calibration_date: str
    self_check_status: str
    fault_code: Optional[str]
    total_cycle_count: int
    uptime_s: float
    downtime_s: float
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Machine(ABC):
    """
    Abstract base for all simulated floor equipment.

    Subclasses MUST implement:
      - _collect_metrics(): return a dict of machine-specific health
        values for this instant (this is where each machine's wear/drift
        signal gets reported).

    Subclasses typically ALSO define their own production event method
    (not enforced here on purpose -- see module docstring).
    """

    # Cycles before calibration is considered "due". Override per
    # subclass if a machine has a different real-world calibration
    # interval.
    CALIBRATION_CYCLE_LIMIT = 500

    def __init__(
        self,
        station_id: str,
        on_health_reading: Optional[Callable[[MachineHealth], None]] = None,
    ):
        self.station_id = station_id
        self.state = MachineState.IDLE

        # Wear / calibration tracking -- shared across every machine
        # because every real piece of floor equipment ages the same way
        # conceptually, even though the physical signal differs.
        self.total_cycle_count = 0
        self.cycles_since_calibration = 0
        self.last_calibration_date = datetime.now(timezone.utc).date().isoformat()

        # Availability tracking -- feeds OEE identically across machines.
        self.uptime_s = 0.0
        self.downtime_s = 0.0

        self._fault_code: Optional[str] = None
        self._on_health_reading = on_health_reading

    # ------------------------------------------------------------
    # Calibration / wear -- shared logic
    # ------------------------------------------------------------

    def is_overdue_for_calibration(self) -> bool:
        return self.cycles_since_calibration >= self.CALIBRATION_CYCLE_LIMIT

    def calibrate(self):
        """Represents a technician performing scheduled maintenance /
        recalibration. Resets wear counters; does not touch total
        lifetime cycle count."""
        self.cycles_since_calibration = 0
        self.last_calibration_date = datetime.now(timezone.utc).date().isoformat()
        self._fault_code = None
        if self.state in (MachineState.DOWN, MachineState.FAULT):
            self.state = MachineState.IDLE

    def set_fault(self, fault_code: str):
        self._fault_code = fault_code
        self.state = MachineState.FAULT

    def clear_fault(self):
        self._fault_code = None
        if self.state == MachineState.FAULT:
            self.state = MachineState.IDLE

    def self_check_status(self) -> SelfCheckStatus:
        if self._fault_code:
            return SelfCheckStatus.FAULT
        if self.is_overdue_for_calibration():
            return SelfCheckStatus.WARN
        return SelfCheckStatus.OK

    # ------------------------------------------------------------
    # Availability tracking -- shared logic
    # ------------------------------------------------------------

    def record_uptime(self, seconds: float):
        self.uptime_s += seconds

    def record_downtime(self, seconds: float):
        self.downtime_s += seconds

    # ------------------------------------------------------------
    # Cycle bookkeeping -- called by subclasses after a production event
    # ------------------------------------------------------------

    def _register_cycle(self):
        """Subclasses call this once per completed production event
        (test, stroke, fastening cycle, cure batch...) so wear counters
        stay consistent across all machine types without every subclass
        re-implementing the same increment logic."""
        self.total_cycle_count += 1
        self.cycles_since_calibration += 1

    # ------------------------------------------------------------
    # Health sampling -- shared envelope, machine-specific payload
    # ------------------------------------------------------------

    @abstractmethod
    def _collect_metrics(self) -> dict:
        """Return this machine's specific telemetry values for right
        now (e.g. {'ramp_time_actual_s': 8.1, 'internal_temp_c': 35.2}).
        This is where each subclass's real wear/drift signal shows up."""
        raise NotImplementedError

    def sample_health(self) -> MachineHealth:
        """Time-driven health snapshot. Call this on a fixed interval
        (e.g. every 60s) independent of whether a production event is
        currently running -- machine condition exists whether or not
        it's actively producing."""
        reading = MachineHealth(
            reading_id=str(uuid.uuid4()),
            station_id=self.station_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            cycles_since_calibration=self.cycles_since_calibration,
            last_calibration_date=self.last_calibration_date,
            self_check_status=self.self_check_status().value,
            fault_code=self._fault_code,
            total_cycle_count=self.total_cycle_count,
            uptime_s=self.uptime_s,
            downtime_s=self.downtime_s,
            metrics=self._collect_metrics(),
        )

        if self._on_health_reading:
            self._on_health_reading(reading)

        return reading
    
