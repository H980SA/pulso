# ExoMy gateway overlay

This directory owns the PULSO-specific policy delta on top of the installed
`pulso-rover-sdk==0.1.0`. It intentionally leaves the gateway in `SHADOW` after
deployment. `GROUND` is a separate operator action and requires all of:

- `PULSO_STAGE=GROUND`
- `PULSO_ALLOW_ACTUATION=true`
- `PULSO_EXCLUSIVE_CONTROL_CONFIRMED=true`
- `PULSO_GROUND_SUPERVISED_CONFIRMED=true`
- `PULSO_MAX_DURATION_MS=150`

Ground motion accepts only the CREEP profile, a matching lease holder, and a
1–150 ms timed pulse. ROS and motor watchdogs remain independent. The rover has
no physical obstacle sensor or wheel feedback; achievement is always
`UNVERIFIED` and a human must remain at the power cutoff.
