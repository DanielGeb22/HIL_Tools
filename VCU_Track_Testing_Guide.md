# VCU Track Testing Guide - TEST Branch
**Date**: Pre-Track Testing Session
**Branch**: TEST (Integration of PL_main, LC_main, Eff_main, Regen_main)
**Authors**: Akash Karthik (PL/Eff), Launch Control Team, Vern Toor (Regen)
**Vehicle**: Spartan Racing Electric Formula SAE

---

## Executive Summary

The TEST branch integrates four major feature branches into a comprehensive control system for tomorrow's track testing:

1. **Power Limiting (PL_main)** - Caps power consumption to configurable limits (20-80kW)
2. **Efficiency (Eff_main)** - Energy budgeting algorithm for endurance racing
3. **Launch Control (LC_main)** - Traction control via slip ratio management
4. **Regenerative Braking (Regen_main)** - Multiple regen modes with proportional valve implementation

All systems run on the **10ms control loop (100Hz)** and communicate via dual CAN buses.

---

## System 1: Power Limiting (PL_main)

### Purpose
Prevents the car from exceeding a configurable power limit by dynamically reducing motor torque. Critical for:
- Staying within FSAE energy limits
- Preventing battery over-discharge
- Managing thermal constraints
- Optimizing lap time vs energy consumption

### How It Works

**Algorithm**: PID-based power control with two modes

#### Mode 1: Torque PID (Currently Inactive)
- Calculates torque setpoint from power target and motor RPM
- Formula: `torqueSetpoint = (targetPower - 2.0) * (9549.0 / motorRPM)`
- PID adjusts torque to maintain power limit

#### Mode 2: Power PID (Currently Active - DEFAULT)
- Directly measures instantaneous power: `drawnPower = (voltage × current) / 1000`
- PID compares actual vs target power
- Converts power correction to torque command: `torque = (pidOutput + drawnPower) * (9549 / motorRPM)`

### Current Configuration
```c
PID Tuning:   Kp=10, Ki=0, Kd=0     // Pure proportional control
Mode:         2 (Power PID)
Target:       80 kW (hardcoded in powerLimit.c:31)
Always On:    TRUE                   // Stays active once triggered
Clamping:     4 (power-based anti-windup)
Init Thresh:  75 kW                  // Target - 5kW buffer
```

### Activation Logic
1. **Entry Conditions**:
   - `plToggle = TRUE` (enabled)
   - Current power > `initializationThreshold` (75kW)
   - Throttle > 0% and power > 0

2. **Exit Conditions**:
   - Throttle released (APPS = 0)
   - Power drops to 0 or negative
   - System reset via PID reset

3. **Always-On Mode**:
   - Once activated, stays on until throttle released
   - Prevents oscillation at power threshold

### Rotary Switch Power Levels (Currently Commented Out)
The code supports driver-selectable power limits via rotary knob:
- **PL_MODE_OFF**: Power limiting disabled
- **PL_MODE_20**: 20 kW limit
- **PL_MODE_30**: 30 kW limit
- **PL_MODE_40**: 40 kW limit
- **PL_MODE_50**: 50 kW limit
- **PL_MODE_60**: 60 kW limit

**NOTE**: Rotary switch code is commented out (line 126, 128). Currently fixed at 80kW.

### What to Test
1. **Activation behavior**:
   - Does PL activate when power exceeds 75kW?
   - Does it stay active during full-throttle straights?
   - Does it deactivate cleanly when throttle lifted?

2. **Power tracking**:
   - Monitor CAN telemetry for `plStatus` (ON/OFF)
   - Check `plTorqueCommand` vs `appsTorqueCommand`
   - Verify actual power stays below 80kW limit

3. **PID response**:
   - Is power regulation smooth or oscillating?
   - Check for overshoot/undershoot
   - Monitor `pid->proportional` output on CAN

4. **Edge cases**:
   - Rapid throttle changes
   - Low RPM / high torque scenarios (may saturate)
   - Does it interfere with Launch Control?

### Integration Points
- **Input**: Motor voltage/current (from MCM), motor RPM
- **Output**: `plTorqueCommand` sent to motor controller
- **Interacts with**: Efficiency module (reads `plStatus`)

### Key Files
- `dev/powerLimit.c` (270 lines)
- `dev/powerLimit.h` (92 lines)
- `dev/PID.c` (shared PID implementation)

---

## System 2: Efficiency / Energy Budgeting (Eff_main)

### Purpose
Optimizes energy usage for endurance events by dynamically adjusting power limits based on real-time energy consumption. Maximizes available power in straights while conserving energy in corners.

### How It Works

**Algorithm**: Adaptive per-lap energy budgeting with carryover

#### Concept
1. Allocate fixed energy budget per lap (6.6kWh total / 22 laps = 0.3kWh/lap)
2. Track energy usage separately for straights vs corners
3. At lap completion, calculate unused energy (carryover)
4. Adjust next lap's power limit to use budget + carryover optimally

#### Formula (efficiency.c:68)
```c
nextLapPowerLimit = (energyBudget + carryOverEnergy - energySpentInCorners) / timeInStraights
```

**Logic**:
- Corners require full power (no PL intervention)
- Straights can be power-limited without losing time
- Use remaining energy budget in straights to go faster

### Current Configuration
```c
Total Event Energy:   6.6 kWh
Laps per Event:       22
Energy per Lap:       0.3 kWh (6.6/22)
Cycle Time:           10ms (0.01s)
Lap Detection:        Distance > 1.0 km
```

### Algorithm Steps (Every 10ms)

1. **Measure Current Power**:
   ```c
   currentPower_kW = (voltage * current) / 1000
   energyThisCycle = (currentPower * 0.01s) / 3600  // Convert to kWh
   ```

2. **Classify Driving Segment**:
   - **Straight**: PL is active AND PL torque < APPS torque
   - **Corner**: PL inactive OR driver not limited

   Accumulate time and energy for each segment type.

3. **Track Lap Distance**:
   ```c
   distance_this_cycle = wheelSpeed_kph * (0.01s / 3600)
   totalLapDistance += distance_this_cycle
   ```

4. **Lap Completion** (when `totalLapDistance > 1.0 km`):
   - Calculate carryover: `carryOver = budget - actualUsed`
   - Compute new power limit for next lap
   - Reset all lap counters

### What to Test

1. **Lap Detection**:
   - Does lap counter increment after ~1km?
   - Check `lapCounter` on CAN telemetry
   - Verify reset happens cleanly

2. **Energy Tracking**:
   - Monitor `lapEnergySpent_kWh` during lap
   - Does it track realistically? (should be ~0.3kWh/lap)
   - Check `energySpentInCorners` vs `energySpentInStraights`

3. **Segment Classification**:
   - Are straights/corners detected correctly?
   - Check `timeInStraights_s` and `timeInCorners_s`
   - Verify PL status is used correctly for classification

4. **Power Limit Adjustment**:
   - After lap 1 completes, does `plTargetPower` update?
   - Is new limit reasonable? (should be 30-80kW range)
   - Monitor `carryOverEnergy_kWh` (can be positive or negative)

5. **Edge Cases**:
   - What if driver runs out of energy budget early?
   - Division by zero protection if no straight time logged
   - Behavior on first lap (no carryover yet)

### Integration Points
- **Requires**: PowerLimit object (reads `plStatus`, writes `plTargetPower`)
- **Requires**: MotorController (reads voltage, current, speed)
- **Toggle**: `efficiencyToggle` flag (enable/disable entire system)

### Potential Issues to Watch
- **Lap detection**: 1km may not match actual track length (tune if needed)
- **Segment classification**: Assumes PL torque < APPS means "straight" (may misclassify)
- **First lap**: No historical data, uses default 80kW limit
- **Energy budget**: 6.6kWh / 22 laps assumes endurance event (adjust for other events)

### Key Files
- `dev/efficiency.c` (137 lines)
- `dev/efficiency.h` (40 lines)

---

## System 3: Launch Control (LC_main)

### Purpose
Maximizes acceleration from standstill by preventing wheel spin through slip ratio control. Automates optimal traction management during launches.

### How It Works

**Algorithm**: 3-phase slip ratio control with PID feedback

#### Phase 1: RAMP (Initial Launch)
- Applied when wheel speed sensors read zero (car nearly stationary)
- Uses exponential torque ramp-up curve
- Formula: `torque = k * maxTorque + (1-k) * prevTorque`
- Default: `k = 0.6`, `initialTorque = 240 dNm`, `maxTorque = 240 dNm`
- Ramps smoothly to prevent sudden wheelspin

#### Phase 2: NONLINEAR (High Slip)
- Activated when `slipRatio > 0.2`
- PID with **integral disabled** (Kp=50, Ki=0, Kd=0)
- Prevents integral windup during aggressive slip
- Aggressively corrects excessive wheelspin

#### Phase 3: LINEAR (Controlled Slip)
- Activated when `slipRatio < 0.2`
- Full PID enabled (Kp=50, Ki=20, Kd=0)
- Smooth tracking of target slip ratio
- Switches back to NONLINEAR if slip exceeds 0.25

### Slip Ratio Calculation
```c
slipRatio = (fastestRearWheelRPM / avgFrontWheelRPM) - 1.0

Target: 0.2 (20% slip)
```

**Example**: If front wheels = 1000 RPM, rear = 1200 RPM → slip = 0.2 (perfect)

### State Machine

#### State 1: IDLE
- Default state, LC not active
- Monitoring button and vehicle conditions

#### State 2: READY
- **Entry**: LC button held + speed < 1 KPH + brake < 5%
- Driver can press throttle without torque being sent
- LC absorbs throttle input (sends 0 torque to motor)
- Ready to launch when button released

#### State 3: ACTIVE
- **Entry**: LC button released + throttle > 90% + brake < 5%
- LC takes over torque control
- Follows 3-phase algorithm
- **Exit**: Throttle < 90% OR brake > 5%

### Operational Procedure (For Driver)
1. **Prepare**: Hold LC button, ensure car stationary, brake off
2. **Ready**: Floor throttle pedal (100%) while holding LC button
3. **Launch**: Release LC button → LC activates instantly
4. **Control**: LC manages torque automatically until throttle lifted

### Current Configuration
```c
PID Tuning:        Kp=50, Ki=20, Kd=0
Target Slip:       0.2 (20%)
Max Torque:        240 dNm (24 Nm)
Initial Torque:    240 dNm
Ramp Factor (k):   0.6
Filter RPM Thresh: 1000 RPM (enables wheel speed filtering)
```

### Wheel Speed Filtering
- Below 1000 motor RPM: Raw wheel speeds used
- Above 1000 motor RPM: Filtered wheel speeds used
- Reduces noise at higher speeds

### Torque Clamping (Recent Addition)
- LC torque command clamped to `[0, 231]` dNm
- Prevents negative torque or excessive commands
- Commit: "clamp lc torque command" (05d2f88)

### What to Test

1. **State Transitions**:
   - Does IDLE → READY work when button held + stationary?
   - Does READY → ACTIVE trigger on button release?
   - Does it abort correctly if throttle not floored?
   - Monitor `LC_State` on CAN

2. **Slip Ratio Control**:
   - Does slip stabilize around 0.2 during launch?
   - Check `currentSlipRatio` telemetry
   - Watch for oscillations or overshoot
   - Verify rear wheels spin ~20% faster than front

3. **Phase Transitions**:
   - RAMP → NONLINEAR/LINEAR when wheels start moving
   - NONLINEAR ↔ LINEAR transitions at 0.2/0.25 thresholds
   - Check `LC_Phase` on CAN

4. **Torque Commands**:
   - Monitor `lcTorqueCommand` during active launch
   - Should ramp up smoothly in RAMP phase
   - Should modulate in LINEAR/NONLINEAR phases
   - Compare to `appsTorqueCommand`

5. **Edge Cases**:
   - Multiple launch attempts (does reset work?)
   - Abort mid-launch (lift throttle at 50%)
   - Brake during active LC
   - Wheel speed sensor failures

6. **Driver Feedback**:
   - Does launch feel smooth or jerky?
   - Wheel spin audible/visible?
   - Acceleration compared to manual launch?

### Integration Points
- **Input**: Throttle position, brake pressure, wheel speeds, motor RPM
- **Output**: `lcTorqueCommand` to motor controller
- **Conflicts**: May interact with Power Limit (LC takes priority if both active)

### Safety Features
- Automatic abort if brake applied (> 5% pressure)
- Automatic abort if throttle lifted (< 90%)
- Requires near-standstill (< 1 KPH) to arm
- Button must be released with throttle floored (prevents accidental activation)

### Key Files
- `dev/LaunchControl.c` (243 lines)
- `dev/LaunchControl.h` (76 lines)

---

## System 4: Regenerative Braking (Regen_main)

### Purpose
Recovers kinetic energy during braking by using the motor as a generator. Extends range and provides additional braking force. Uses **proportional valve** to calculate regen based on actual brake pressure differential.

### How It Works

**Algorithm**: Proportional brake pressure to motor torque conversion

#### Brake Pressure Formula (regen.c:100)
```c
bpsTorqueNm = ((bps0_PSI - bps1_PSI) * PSI_TO_N_PER_mm² * padFriction
               * REAR_PISTON_AREA * ROTOR_RADIUS) / GEAR_RATIO

Constants:
- GEAR_RATIO = 2.7
- REAR_PISTON_AREA = 2 × 791.73 mm²
- ROTOR_RADIUS = 74.17 mm
- PSI_TO_N_PER_mm² = 0.006895
- Pad Friction (μ) = 0.5
```

**Logic**:
- Measures pressure differential across proportional valve
- Converts to equivalent braking torque at wheels
- Commands motor to generate same torque via regen
- Seamless blend of friction + regen braking

#### Final Torque Command (regen.c:102)
```c
regenTorqueCommand = (appsTorque / 10) - bpsTorqueNm

Clamped to: [-150, 231] dNm
```

### Regen Modes

#### Mode 1: FORMULAE (Default - Line 24)
- **Behavior**: Regen only on brake pedal
- **Settings**:
  - Max regen torque: 500 dNm (50 Nm)
  - Regen at zero pedal: 0 dNm (no engine braking)
  - Throttle coast threshold: 0%
  - Brake for max regen: 30% pedal travel
- **Feel**: Traditional race car (coast when off throttle)

#### Mode 2: TESLA
- **Behavior**: Regen on throttle lift (one-pedal driving)
- **Settings**:
  - Max regen torque: 500 dNm
  - Regen at zero pedal: 500 dNm (full engine braking)
  - Throttle coast threshold: 10%
  - Brake for max regen: 0% (brake pedal adds friction brakes)
- **Feel**: Strong engine braking like Tesla Model 3

#### Mode 3: HYBRID (Recently Implemented - Commit 162b6d6)
- **Behavior**: Light engine braking + brake regen
- **Settings**:
  - Max regen torque: 500 dNm
  - Regen at zero pedal: 150 dNm (30% of max)
  - Throttle coast threshold: 20%
  - Brake for max regen: 30%
- **Feel**: Mild engine braking for better corner entry

#### Mode 4: FIXED (Outdated)
- Fixed 250 dNm regen, 5% coast threshold

#### Mode 5: CUSTOM (Not Implemented)
- Placeholder for driver-configurable settings (Issue #97)

#### Mode 6: OFF
- Regen disabled

### Safety Features

1. **Minimum Speed**: 5 KPH
   - No regen below 5 KPH (prevents jerkiness at stop)
   - Ramps down between 5-10 KPH

2. **Current Limiting**: -72A maximum
   - If current exceeds -72A for 10 consecutive cycles (100ms), regen disabled
   - Prevents over-charging battery
   - Tick counter resets if current returns to safe range

3. **RPM Limiting**: Tapers above 2400 RPM
   - Formula: `torqueLimit = -0.022 * (RPM - 2400) + 750`
   - Prevents excessive regen at high speeds
   - Zero regen above ~36,000 RPM (unrealistic, effectively unlimited)

4. **Throttle Redundancy**:
   - If throttle > 0 in FORMULAE mode, no brake regen allowed
   - Prevents simultaneous accel + regen

### What to Test

1. **Activation Behavior**:
   - Does regen activate when brakes applied?
   - Check `regenActiveStatus` on CAN
   - Verify no regen below 5 KPH

2. **Brake Pressure Correlation**:
   - Monitor `bps0_PSI` and `bps1_PSI`
   - Does pressure differential increase with brake pedal?
   - Check `bpsTorqueNm` calculation on CAN
   - Does regen torque match pressure?

3. **Mode Comparison** (if selectable):
   - **FORMULAE**: Should coast freely off throttle
   - **HYBRID**: Should have light engine braking
   - **TESLA**: Should have strong engine braking
   - Driver preference feedback

4. **Current Limiting**:
   - Monitor `dcCurrent` during hard braking
   - Should never exceed -72A for >100ms
   - Check if regen shuts off during excessive current

5. **Torque Blending**:
   - Does regen + friction braking feel smooth?
   - Any jerky transitions?
   - Monitor `regenTorqueCommand` during brake application

6. **Edge Cases**:
   - Brake at very low speed (4-6 KPH range)
   - Brake during high-speed straight
   - Simultaneous throttle + brake (should prevent regen)
   - Battery at high state of charge (may limit regen)

### Integration Points
- **Input**: Brake pressure sensors (BPS0/BPS1), throttle position, motor RPM, DC current, ground speed
- **Output**: `regenTorqueCommand` (negative = regenerative braking)
- **Conflicts**: Interacts with safety checker (brake-throttle interlock)

### Recent Changes (Regen_main commits)
- **162b6d6**: Hybrid mode implementation
- **c00d614**: Regen on APPS + safety check
- **da400b1**: Cleaned up torque equation + clamping + new getter
- **6f3ecb8**: BPS pressure back-calculation
- **232e1aa**: Regen CAN messages added

### Key Files
- `dev/regen.c` (167 lines)
- `dev/regen.h` (48 lines)
- `dev/brakePressureSensor.c` (updated for PSI calculation)

---

## System Integration & Interactions

### Torque Arbitration Hierarchy

The VCU must decide which system controls motor torque. The hierarchy is:

1. **Safety Checker** (Highest Priority)
   - Can veto or reduce any torque command
   - APPS/BPS implausibility check
   - Brake-throttle interlock
   - Voltage/temperature limits

2. **Launch Control** (Active during launch)
   - Overrides normal throttle when `LC_State == ACTIVE`
   - Outputs `lcTorqueCommand`

3. **Power Limit** (Active during high power)
   - Caps torque when power > threshold
   - Outputs `plTorqueCommand`

4. **Regenerative Braking** (Active during braking)
   - Commands negative torque when brake applied
   - Outputs `regenTorqueCommand` (negative value)

5. **Throttle Encoder** (Baseline)
   - Driver's pedal input
   - Outputs `appsTorqueCommand`

### Control Flow (main.c)

```
Every 10ms cycle:

1. Read all sensors (TPS, BPS, WSS, voltage, current, etc.)
2. Read CAN messages

3. Calculate commands:
   - Launch Control updates (if enabled)
   - Efficiency calculates energy budget
   - Power Limit computes torque cap
   - Motor Controller processes all inputs
   - Regen calculates brake-based torque

4. Safety checks:
   - Verify APPS/BPS plausibility
   - Apply torque reductions if needed

5. Actuate:
   - MCM relay control (contactors)
   - MCM inverter control (final torque command)
   - BMS relay control
   - Send CAN telemetry

6. Wait for 10ms cycle completion
```

### Potential Conflicts to Monitor

1. **Launch Control + Power Limit**:
   - Both may try to limit torque simultaneously
   - LC has priority during launch phase
   - Monitor for unexpected torque reduction during launch

2. **Regenerative Braking + Safety Checker**:
   - Regen applies negative torque
   - Safety checker may interfere if it misinterprets as throttle
   - Check brake-throttle interlock logic

3. **Efficiency + Power Limit**:
   - Efficiency updates PL target power dynamically
   - PL may receive new target mid-lap
   - Verify smooth transition when target changes

4. **Regen + Launch Control**:
   - Should be mutually exclusive (launch = accel, regen = braking)
   - Verify no regen during LC active state

### CAN Message Traffic

**CAN0 (High Priority - 500 kbps, 50 msg limit)**:
- Motor controller commands (torque, relay control)
- BMS status (voltage, current, temperature)
- Safety-critical sensor data
- Launch Control status
- Power Limit status

**CAN1 (Low Priority DAQ - 500 kbps, 10 msg limit)**:
- Debug telemetry
- Efficiency metrics (energy, lap counter)
- PID internal states
- Regen torque details

### Shared Resources

- **PID Controllers**: Each system (PL, LC) has its own PID instance
- **Motor RPM**: Used by PL, Regen, LC, Efficiency
- **Ground Speed**: Used by Regen (safety), LC (entry condition), Efficiency (lap detection)
- **Torque Commands**: All systems write to MCM, MCM arbitrates final command

---

## Track Testing Checklist

### Pre-Track Preparation

**Firmware Verification**:
- [ ] Confirm TEST branch is flashed to VCU
- [ ] Verify build date in CAN telemetry matches latest TEST commit
- [ ] Check all module toggles enabled:
  - `plToggle = TRUE`
  - `efficiencyToggle = TRUE`
  - `lcToggle = TRUE`
  - `regenToggle = TRUE`

**Calibration**:
- [ ] TPS calibration (hold Eco button during startup)
- [ ] BPS calibration (verify 0% at rest, 100% at max)
- [ ] Wheel speed sensors reading correctly (all 4 wheels)
- [ ] Verify brake pressure sensors (BPS0, BPS1) reading PSI

**Telemetry Setup**:
- [ ] CAN logger connected and recording
- [ ] Monitor on laptop showing real-time data
- [ ] Dashboard displaying key metrics:
  - Motor RPM, voltage, current, power
  - Wheel speeds (FL, FR, RL, RR)
  - PL status, torque command
  - LC state, phase, slip ratio
  - Regen status, torque
  - Efficiency: lap counter, energy spent

**Safety Checks**:
- [ ] HVIL (High Voltage Interlock) connected
- [ ] Emergency stop tested
- [ ] Brake light functional
- [ ] RTD (Ready to Drive) sound working

### Test Session 1: Baseline (No Advanced Features)

**Goal**: Establish baseline performance and verify basic functionality

1. **Disable all advanced features** (set toggles to FALSE or use rotary knobs to "OFF"):
   - Power Limit: OFF
   - Launch Control: OFF
   - Efficiency: OFF (or accept it runs in background)
   - Regen: OFF

2. **Basic laps** (3-5 laps):
   - Gradual throttle application
   - Verify motor response is linear
   - Check brake feel (friction only, no regen)
   - Monitor all sensor readings for anomalies

3. **Data to capture**:
   - Lap times
   - Peak power usage
   - Energy consumption per lap
   - Throttle/brake/speed traces

### Test Session 2: Regenerative Braking

**Goal**: Test regen modes and verify brake feel

1. **Enable regen** (`regenToggle = TRUE` or rotary to FORMULAE mode)

2. **Static test** (car on stands, wheels free):
   - Apply brake pedal gradually
   - Verify `bps0_PSI` and `bps1_PSI` differential increases
   - Check `regenTorqueCommand` becomes negative
   - Verify motor spins backward (regen)

3. **Low-speed test** (parking lot or slow track):
   - Test minimum speed threshold (5 KPH)
   - Verify no regen below 5 KPH
   - Check ramp-down between 5-10 KPH

4. **Full lap test** (FORMULAE mode):
   - Normal braking for corners
   - Monitor `dcCurrent` (should go negative during braking)
   - Check for -72A current limiting
   - Driver feedback on brake feel

5. **Mode comparison** (if rotary switch available):
   - Compare FORMULAE vs HYBRID vs TESLA
   - Driver preference survey
   - Note any jerky transitions

6. **Data to capture**:
   - Brake pressure vs regen torque correlation
   - Energy recovered per lap
   - Peak regen current
   - Battery voltage during regen (watch for overvoltage)

### Test Session 3: Launch Control

**Goal**: Test launch control states and slip ratio control

**SAFETY NOTE**: Ensure clear, straight track section for launches. Have spotter confirm no obstacles.

1. **State machine test**:
   - Hold LC button at standstill → verify READY state
   - Release LC button with low throttle → should abort to IDLE
   - Hold LC button, floor throttle, release button → should enter ACTIVE

2. **Single launch test**:
   - Follow driver procedure (hold button → floor throttle → release button)
   - Monitor slip ratio in real-time
   - Target: `slipRatio ≈ 0.2`
   - Check phase transitions: RAMP → NONLINEAR/LINEAR

3. **Multiple launches** (3-5 attempts):
   - Verify repeatability
   - Check reset between launches
   - Compare LC-assisted vs manual launch (lap timer)

4. **Abort test**:
   - Activate LC, then lift throttle mid-launch → should abort cleanly
   - Activate LC, then apply brake → should abort immediately

5. **Data to capture**:
   - 0-60 time (or 0-40 if track limited)
   - Slip ratio traces (should stabilize at 0.2)
   - Rear vs front wheel speeds
   - LC torque command vs APPS torque
   - Phase duration (how long in RAMP, NONLINEAR, LINEAR)

### Test Session 4: Power Limiting

**Goal**: Test power capping and PID response

1. **Activation test**:
   - Full throttle on straight
   - Monitor power rising toward 80kW
   - Verify PL activates at ~75kW (initThreshold)
   - Check `plStatus` toggles TRUE

2. **Regulation test**:
   - Maintain full throttle
   - Verify power stays at or below 80kW
   - Check for oscillations or overshoot
   - Driver feedback: does torque reduction feel smooth?

3. **Deactivation test**:
   - Lift throttle partially
   - Verify PL status drops to FALSE
   - Re-apply throttle → should re-activate

4. **Different power levels** (if rotary available):
   - Test 40kW, 60kW, 80kW limits
   - Verify power tracks setpoint for each
   - Check PID reset when switching levels

5. **Data to capture**:
   - Power trace (should flatten at limit)
   - PL torque vs APPS torque
   - PID proportional/integral terms
   - Activation/deactivation timestamps

### Test Session 5: Efficiency Algorithm

**Goal**: Test energy budgeting and adaptive power limiting

**NOTE**: Requires multiple laps (at least 2) to see effect

1. **First lap** (baseline):
   - Complete full lap with PL and Efficiency enabled
   - Monitor `lapEnergySpent_kWh` (should reach ~0.3kWh)
   - Check `timeInStraights` vs `timeInCorners`
   - Note initial `plTargetPower` (should be 80kW)

2. **Lap completion**:
   - When `totalLapDistance > 1.0 km`, verify:
     - `lapCounter` increments
     - `carryOverEnergy` calculated (positive if under budget, negative if over)
     - `plTargetPower` updates for next lap
   - Check for clean lap reset

3. **Second lap** (adaptive):
   - Drive with updated power limit
   - Verify new `plTargetPower` is used
   - Monitor if energy usage changes

4. **Multiple laps** (3-5):
   - Observe power limit convergence
   - Should stabilize after 2-3 laps
   - Check if algorithm is too aggressive or conservative

5. **Edge cases**:
   - What if lap is shorter than 1km? (test on small track)
   - What if driver never triggers PL? (all corners, no straights)
   - Division by zero check (if `timeInStraights = 0`)

6. **Data to capture**:
   - Energy per lap (should average ~0.3kWh)
   - Carryover energy (lap-to-lap)
   - Power limit adjustments (lap-to-lap)
   - Segment classification accuracy (straight vs corner)

### Test Session 6: Integration (All Systems Enabled)

**Goal**: Test all systems working together

1. **Full feature lap** (PL + Eff + LC + Regen all ON):
   - Launch using LC
   - Accelerate normally
   - Enter straight → PL may activate
   - Brake for corner → Regen activates
   - Monitor for conflicts or unexpected behavior

2. **Endurance simulation** (5-10 laps):
   - Consistent pace, like an endurance event
   - Let Efficiency algorithm adapt
   - Monitor total energy consumption
   - Check if 6.6kWh budget is realistic for 22 laps

3. **Performance mode** (fast laps, 3-5):
   - Max attack, focus on lap time
   - Accept higher energy usage
   - Compare lap time vs energy tradeoff

4. **Data to capture**:
   - Lap times (compare to baseline Session 1)
   - Total energy used
   - System interaction logs (any conflicts?)
   - Driver feedback (feel, driveability)

### Post-Session Data Review

After each session, review:

1. **CAN logs**:
   - Any error codes or faults?
   - Unexpected torque commands?
   - Sensor anomalies?

2. **Plots to generate**:
   - Power vs time (overlay PL status)
   - Torque commands (APPS, LC, PL, Regen)
   - Slip ratio during launches
   - Energy per lap (across all laps)
   - Battery voltage/current (watch for overvoltage during regen)

3. **Driver debrief**:
   - Which systems felt good?
   - Any unexpected behavior?
   - Suggested tuning changes?

---

## Tuning Parameters & Where to Find Them

### Power Limit Tuning (dev/powerLimit.c)

| Parameter | Line | Default | Adjust For |
|-----------|------|---------|------------|
| PID Kp | 27 | 10 | Faster/slower response |
| PID Ki | 27 | 0 | Eliminate steady-state error (currently off) |
| PID Kd | 27 | 0 | Damping oscillations |
| plTargetPower | 31 | 80 kW | Lower for conservation, higher for performance |
| plThresholdDiscrepancy | 32 | 5 kW | Buffer before activation |
| clampingMethod | 34 | 4 | Anti-windup strategy |

### Efficiency Tuning (dev/efficiency.c)

| Parameter | Line | Default | Adjust For |
|-----------|------|---------|------------|
| TOTAL_ENERGY_BUDGET_KWH | 15 | 6.6 kWh | Match event rules (80kWh / number of events?) |
| Laps per event | 23 | 22 | Actual endurance lap count |
| Lap detection distance | 81 | 1.0 km | Match actual track length |

### Launch Control Tuning (dev/LaunchControl.c)

| Parameter | Line | Default | Adjust For |
|-----------|------|---------|------------|
| PID Kp | 26 | 50 | Slip ratio tracking speed |
| PID Ki | 27 | 20 | Integral response (only in LINEAR phase) |
| PID Kd | 28 | 0 | Damping (currently off) |
| slipRatioTarget | 30 | 0.2 | More slip = more wheelspin, less slip = slower launch |
| initialTorque | 36 | 240 dNm | Starting torque for RAMP phase |
| k (ramp factor) | 37 | 0.6 | Ramp-up aggressiveness (higher = faster) |
| LC_MIN_THROTTLE_THRESHOLD | 20 | 90% | Required throttle to activate |
| LC_MAX_BRAKE_THRESHOLD | 18 | 5% | Abort if brake exceeds this |

### Regen Tuning (dev/regen.c)

| Parameter | Line | Default | Adjust For |
|-----------|------|---------|------------|
| MIN_REGEN_SPEED_KPH | 9 | 5 KPH | Lower speed cutoff |
| REGEN_RAMPDOWN_START | 10 | 10 KPH | Where ramp-down starts |
| torqueLimitDNm (FORMULAE) | 120 | 500 dNm | Max regen in brake-only mode |
| torqueLimitDNm (HYBRID) | 134 | 500 dNm | Max regen in hybrid mode |
| torqueAtZeroPedalDNm (HYBRID) | 135 | 150 dNm | Engine braking strength |
| percentBPSForMaxRegen | 123/137 | 30% | Brake pedal travel for full regen |
| padMu (friction coeff) | 32 | 0.5 | Brake pad friction (tune to match hardware) |
| Current limit | 54 | -72A | Safety cutoff for regen current |

---

## Known Issues & Limitations

### Power Limit
1. **Rotary switch disabled**: Power level hardcoded to 80kW (lines 126, 128 commented out)
2. **No Ki tuning**: Integral term is zero (may have steady-state error)
3. **Low RPM saturation**: At low RPM, torque = power / RPM → may request impossible torque
4. **First activation**: PID starts with zero state (no pre-loading), may overshoot briefly

### Efficiency
1. **Lap detection crude**: Uses 1km distance, won't work on short test tracks
2. **Segment classification assumption**: Assumes PL active = straight (may misclassify)
3. **First lap blind**: No historical data, uses default 80kW
4. **Division by zero**: Protected (line 67), but may set unrealistic power if `timeInStraights ≈ 0`
5. **Energy budget hardcoded**: 6.6kWh may not match actual battery capacity or event rules

### Launch Control
1. **Wheel speed sensor dependency**: RAMP phase until WSS reads non-zero (may be delayed)
2. **Front/rear wheel comparison**: Assumes front = ground speed, rear = driven wheels (true for RWD)
3. **Single slip target**: No adaptive slip based on surface conditions
4. **Button-based activation**: Driver must hold button, floor throttle, release button (complex procedure)
5. **Torque clamp at 231 dNm**: May limit performance (max motor torque unknown)

### Regen
1. **Proportional valve assumptions**: Formula assumes specific brake hardware (REAR_PISTON_AREA, ROTOR_RADIUS)
2. **Pad friction hardcoded**: μ = 0.5 may not match actual brake pads
3. **Mode selection**: Unclear how driver switches modes (rotary knob? CAN command?)
4. **Current limiting simple**: -72A for 100ms is somewhat arbitrary
5. **No temperature monitoring**: Regen may overheat motor or battery if used excessively

### Integration
1. **Torque arbitration unclear**: Multiple systems write torque commands, priority not fully documented
2. **CAN bandwidth**: 50 msg limit on CAN0 may saturate with all systems sending telemetry
3. **10ms cycle time**: All computations must complete in 10ms (may be tight with all features enabled)
4. **No mode persistence**: If VCU resets, all settings return to hardcoded defaults

---

## Safety Considerations

### Critical Safety Systems (Always Active)

1. **APPS/BPS Implausibility** (safety.c):
   - Dual throttle sensors must agree within 10%
   - Dual brake sensors must agree
   - If disagreement > 100ms, torque zeroed

2. **Brake-Throttle Interlock**:
   - If brake > 25% AND throttle > 25%, torque reduced to zero
   - Prevents simultaneous accel/brake

3. **HVIL (High Voltage Interlock)**:
   - If HVIL opened, contactors open immediately
   - System shutdown

4. **Voltage/Temperature Limits** (BMS):
   - Cell overvoltage → shutdown
   - Cell undervoltage → shutdown
   - Overtemperature → shutdown

5. **Watchdog Timer**:
   - If VCU crashes, watchdog resets system
   - Contactors open on reset

### System-Specific Safety

**Power Limit**:
- Can only *reduce* torque, never increase (safe direction)
- Always respects safety checker overrides

**Launch Control**:
- Requires stationary + button held (prevents accidental activation)
- Auto-abort on brake or throttle lift
- Torque clamped to reasonable max

**Regen**:
- Current limited to -72A
- Disabled below 5 KPH
- Disabled if throttle pressed (in FORMULAE mode)

**Efficiency**:
- Only adjusts power limit (doesn't directly command torque)
- Cannot increase beyond hardcoded max (80kW)

### Emergency Procedures

**If car behaves unexpectedly**:
1. **Immediate**: Lift throttle → most systems deactivate
2. **If continues**: Press brake → triggers brake-throttle interlock
3. **If still active**: Press emergency stop button → kills all contactors
4. **Last resort**: Remove HVIL connector → immediate shutdown

**After incident**:
1. Do not restart until data reviewed
2. Check CAN logs for fault codes
3. Verify all sensors reading correctly
4. Test in bench mode before returning to track

---

## Quick Reference: CAN Message IDs

### Power Limit
- **511**: Power Limit Overview (status, mode, target, torque command)
- **512**: PID Output Details (P, I, D terms)
- **513**: LUT Parameters (unused in current code)
- **514**: PID Information (setpoint, Kp, Ki, Kd)

### Launch Control
- Monitor `LC_State`, `LC_Phase`, `lcTorqueCommand`, `currentSlipRatio`
- Check motor controller messages for engaged status

### Efficiency
- Monitor `lapCounter`, `lapEnergySpent_kWh`, `carryOverEnergy_kWh`, `plTargetPower`

### Regen
- Monitor `regenActiveStatus`, `regenTorqueCommand`, `bpsTorqueNm`, `bps0_PSI`, `bps1_PSI`

### Motor Controller
- Voltage, current, power, RPM, commanded torque, feedback torque

### BMS
- Pack voltage, pack current, SOC, cell voltages, temperatures

---

## Appendix: Branch Merge History

```
TEST Branch Composition:

PL_main (a50a16e) ──────┐
                        ├──→ TEST
LC_main (cb71fd9) ──────┤
                        │
Eff_main (5491f20) ─────┤
                        │
Regen_main (bae91b2) ───┘
  ├─ 162b6d6: Hybrid Mode implementation
  ├─ c00d614: regen on apps + safety check
  ├─ da400b1: Cleaned up torque equation + clamping
  ├─ 5cd71c5: Replace rotor diameter with rotor radius
  ├─ 232e1aa: Regen CAN Messages
  └─ fd99086: new regen implementation
```

---

## Contact Info (Code Authors)

- **Power Limit**: Akash Karthik, Aitrieus Wright (prev: Shaun Gilmore, Harleen Sandhu)
- **Efficiency**: Akash Karthik
- **Launch Control**: [Team - not specified in code]
- **Regenerative Braking**: Vern Toor, Shinika (APPS implementation)

For questions during testing, refer to respective branch owners.

---

## Final Notes for Track Testing

**Remember**:
- This is TEST branch - integration testing, not production
- Expect some rough edges or unexpected interactions
- Prioritize safety over performance
- Capture as much data as possible (CAN logs, video, driver notes)
- Not all features may work perfectly on first try

**Success Criteria**:
1. All systems activate/deactivate correctly
2. No safety faults or shutdowns
3. Driver feels confident and in control
4. Data logs confirm expected behavior
5. Lap times competitive (ideally better than baseline)
6. Energy consumption within budget (if testing endurance mode)

**Post-Testing**:
- Review all data with team
- Identify tuning adjustments needed
- Document any bugs or issues
- Decide which features to promote to main branch
- Plan next test session

---

**Good luck with testing! Drive safe and gather great data.**

---

*Document generated for Spartan Racing Electric track testing session*
*VCU Firmware Branch: TEST (integration of PL_main, LC_main, Eff_main, Regen_main)*
*Last Updated: Pre-track testing*
