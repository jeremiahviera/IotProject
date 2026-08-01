"""
hipot_tester.py

Hi-pot (dielectric withstand) test station, built on the shared Machine
base class.

Two data streams, same distinction as before:
  - test_results  -> event-driven, product/quality data, defined ONLY here
                      (this machine's own event method + record shape).
  - machine_health -> time-driven, inherited from Machine.sample_health();
                      this file only supplies _collect_metrics(), i.e.
                      what "health" specifically means for a hi-pot
                      tester (ramp time drift + internal temp).
"""

from __future__ import annotations

import random
import threading
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional
import time

from simulators.base_machine import Machine, MachineState

class TestResultStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ABORTED = "ABORTED"


@dataclass
class TestResult:
    """Event-driven record: one per unit tested. This is the
    product/quality stream -- it answers 'is this unit safe to ship?'
    and has nothing to do with the tester's own condition."""
    test_id: str
    station_id: str
    unit_serial: str
    job_order_id: str
    timestamp_start: str
    timestamp_end: str
    test_voltage_target_v: float
    test_voltage_actual_v: float
    dwell_time_s: float
    leakage_current_ma: float
    leakage_threshold_ma: float
    result: str
    fail_reason: Optional[str]
    operator_id: str

    def to_dict(self) -> dict:
        return asdict(self)


class HiPotTester(Machine):
    """
    Hi-pot test station.

    _collect_metrics() supplies this machine's specific wear/drift
    signal: ramp_time_actual_s. A healthy tester ramps to test voltage
    in a stable amount of time; a degrading transformer/relay makes
    that ramp take longer, which is the predictive-maintenance signal
    for this machine.
    """

    # Hi-pot testers are typically calibrated on a stricter interval
    # than general shop equipment -- override the base default.
    CALIBRATION_CYCLE_LIMIT = 500

    def __init__(
        self,
        station_id: str,
        rated_test_voltage_v: float = 2200.0,
        leakage_threshold_ma: float = 2.0,
        base_dwell_time_s: float = 2.0,
        base_ramp_time_s: float = 8.0,
        on_test_result: Optional[Callable[[TestResult], None]] = None,
        on_health_reading: Optional[Callable] = None,
    ):
        super().__init__(station_id=station_id, on_health_reading=on_health_reading)

        self.rated_test_voltage_v = rated_test_voltage_v
        self.leakage_threshold_ma = leakage_threshold_ma
        self.base_dwell_time_s = base_dwell_time_s
        self.base_ramp_time_s = base_ramp_time_s

        self._on_test_result = on_test_result

    # ------------------------------------------------------------
    # Load a new test recipe (mirrors a master writing setpoint
    # holding registers before Start Test on a real hi-pot tester --
    # only the fields provided are changed).
    # ------------------------------------------------------------

    def configure(
        self,
        test_voltage_v: Optional[float] = None,
        ramp_time_s: Optional[float] = None,
        dwell_time_s: Optional[float] = None,
        leakage_threshold_ma: Optional[float] = None,
    ):
        if test_voltage_v is not None:
            self.rated_test_voltage_v = test_voltage_v
        if ramp_time_s is not None:
            self.base_ramp_time_s = ramp_time_s
        if dwell_time_s is not None:
            self.base_dwell_time_s = dwell_time_s
        if leakage_threshold_ma is not None:
            self.leakage_threshold_ma = leakage_threshold_ma

    # ------------------------------------------------------------
    # Required by Machine: this station's specific health payload
    # ------------------------------------------------------------

    def _collect_metrics(self) -> dict:
        # Generate random temp. uses random for simplicity, may incorperate more realistic temps tied to wear in future
        temp = round(random.gauss(mu=35.0, sigma=2), 1) # Extremely rare chance of temp spike.
        if temp > 45.0 and self.state != MachineState.FAULT:
            self.set_fault("OVER_TEMP")
        return {
            "ramp_time_actual_s": round(self._current_ramp_time(), 3),
            "internal_temp_c": temp,
        }

    def _current_ramp_time(self) -> float:
        """Ramp time drifts upward as cycles_since_calibration grows --
        this is the wear model for this specific machine."""
        wear_drift = 0.01 * self.cycles_since_calibration
        noise = random.uniform(-0.2, 0.2)
        return max(1.0, self.base_ramp_time_s + wear_drift + noise)

    # ------------------------------------------------------------
    # This machine's own production event (not shared with other
    # machine types -- a hi-pot test has a different shape than a
    # punch stroke or a fastening cycle)
    # ------------------------------------------------------------

    def run_test_cycle(
        self,
        unit_serial: str,
        job_order_id: str,
        operator_id: str = "AUTO-01",
        on_progress: Optional[Callable[[float, float, float], None]] = None,  # (elapsed_s, live_voltage, live_current_ma)
        stop_event: Optional[threading.Event] = None
    ) -> TestResult:
        ts_start = datetime.now(timezone.utc)
        self.state = MachineState.RUNNING
        aborted = False

        ramp_time = self._current_ramp_time()
        dwell_time = self.base_dwell_time_s
        step_s = 0.5  # how often to report progress

        # Judged up front rather than after the loops: leakage is
        # roughly ohmic (I = V/R), so live current during ramp can
        # track this same value scaled by the live voltage fraction,
        # and dwell can hold at it -- instead of the live readings and
        # the final judged value coming from two separate random draws.
        noise_scale = 0.3 if not self.is_overdue_for_calibration() else 1.2
        leakage = max(0.0, random.gauss(mu=1.0, sigma=noise_scale))
        if random.random() < 0.03:
            leakage += random.uniform(1.5, 3.5)
        # Ramp is normally rock-stable at setpoint; instability (bad
        # connection / marginal contact) is a rare event, same modeling
        # approach as the leakage defect chance above -- not uniform
        # noise that happens to straddle the fail threshold.
        if random.random() < 0.02:
            voltage_actual = self.rated_test_voltage_v * random.uniform(0.90, 0.97)
        else:
            voltage_actual = self.rated_test_voltage_v * random.uniform(0.99, 1.0)

        elapsed = 0.0
        dwell_elapsed = 0.0
        while elapsed < ramp_time:
            if stop_event and stop_event.is_set():
                aborted = True
                break
            step = min(step_s, ramp_time - elapsed)
            time.sleep(step)
            elapsed += step
            if on_progress:
                live_voltage = self.rated_test_voltage_v * (elapsed / ramp_time)
                live_current = leakage * (elapsed / ramp_time)
                on_progress(elapsed, live_voltage, live_current)

        if not aborted:
            while dwell_elapsed < dwell_time:
                if stop_event and stop_event.is_set():
                    aborted = True
                    break
                step = min(step_s, dwell_time - dwell_elapsed)
                time.sleep(step)
                dwell_elapsed += step
                if on_progress:
                    live_current = max(0.0, leakage + random.uniform(-0.05, 0.05))
                    on_progress(ramp_time + dwell_elapsed, self.rated_test_voltage_v, live_current)

        self.state = MachineState.IDLE

        if aborted:
            record = TestResult(
            test_id=str(uuid.uuid4()),
            station_id=self.station_id,
            unit_serial=unit_serial,
            job_order_id=job_order_id,
            timestamp_start=ts_start.isoformat(),
            timestamp_end=datetime.now(timezone.utc).isoformat(),
            test_voltage_target_v=self.rated_test_voltage_v,
            test_voltage_actual_v=0.0,
            dwell_time_s=dwell_time,
            leakage_current_ma=0.0,
            leakage_threshold_ma=self.leakage_threshold_ma,
            result=TestResultStatus.ABORTED.value,
            fail_reason="USER_INTERRUPT",
            operator_id=operator_id,
        )
            if self._on_test_result:
                self._on_test_result(record)
            return record

        result_status = TestResultStatus.PASS
        fail_reason = None
        if leakage > self.leakage_threshold_ma:
            result_status = TestResultStatus.FAIL
            fail_reason = "LEAKAGE_EXCEEDED_THRESHOLD"
        elif voltage_actual < self.rated_test_voltage_v * 0.98:
            result_status = TestResultStatus.FAIL
            fail_reason = "VOLTAGE_RAMP_UNSTABLE"

        ts_end = datetime.now(timezone.utc)
        self._register_cycle()          # shared wear bookkeeping from Machine

        record = TestResult(
            test_id=str(uuid.uuid4()),
            station_id=self.station_id,
            unit_serial=unit_serial,
            job_order_id=job_order_id,
            timestamp_start=ts_start.isoformat(),
            timestamp_end=ts_end.isoformat(),
            test_voltage_target_v=self.rated_test_voltage_v,
            test_voltage_actual_v=round(voltage_actual, 1),
            dwell_time_s=dwell_time,
            leakage_current_ma=round(leakage, 3),
            leakage_threshold_ma=self.leakage_threshold_ma,
            result=result_status.value,
            fail_reason=fail_reason,
            operator_id=operator_id,
        )

        if self._on_test_result:
            self._on_test_result(record)

        return record


if __name__ == "__main__":
    tester = HiPotTester(
        station_id="HIPOT-01",
        on_test_result=lambda r: print("[TEST]  ", r.to_dict()),
        on_health_reading=lambda h: print("[HEALTH]", h.to_dict()),
    )

    for i in range(5):
        tester.run_test_cycle(unit_serial=f"SWB-2026-{1000+i}", job_order_id="JOB-4471")
        if i % 2 == 0:
            tester.sample_health()

    tester.cycles_since_calibration = tester.CALIBRATION_CYCLE_LIMIT + 10
    tester.sample_health()