# Pulso canonical ragdoll checkpoint

- Accepted seed: `20260733`
- Accepted by the user without further visual retouching.
- Final static scene: `pulso_ragdoll_canonical.blend`
- Reproducible falling-rubble scene: `pulso_ragdoll_canonical_simulation.blend`
- Final frame: `720`
- Physics status: settled, no escaped bodies, no residual contact jitter.
- Neck continuity: A `0.000009 m`; B `0.000010 m`.
- Entrapment:
  - A: `29 kg` primary slab plus `24 kg` secondary slab; validated projected load on chest, pelvis, both arms and both legs.
  - B: `29 kg` primary slab; validated projected load on both lower legs.
- Injury cue: non-graphic blood stain and trail adjacent to survivor B's head.
- Pose authorship: final body and debris transforms are Bullet physics outcomes; cameras and medical cue are added only after the simulation settles.

SHA-256:

- `pulso_ragdoll_canonical.blend`: `c7eb0b4c8fae95e5e1ce4b226e9055f141e3670eee866172102d74f44582beaa`
- `pulso_ragdoll_canonical_simulation.blend`: `c95d7c1690e00dbbefae589aa500d4df5ab5c3aa0aa04f35b9f3a438532525e1`
- `renders/pulso_ragdoll_canonical_A.png`: `ca960e5833ff8aad0ec689cc9871abdb13aaa020979250ec9190724f9f43d429`
- `renders/pulso_ragdoll_canonical_B.png`: `7ab75c8fe63d3c5560ead64d3b42f611655a392bc259483f8b8db82f80c941c0`
