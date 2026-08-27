# Enhancements

The renderer intentionally supports only four stable choices: `speed` (synchronized `setpts` and `atempo`), `fade`, `flash`, and `hard`. `hard` records an intentional hard cut and adds no overlay. Do not promise xfade, crop, zoom, sharpening, vignette, drawbox, or other effects unless the renderer is extended and tested first. Keep the unmodified segment available; do not substitute an effect for a strong event selection.

Every enhancement proposal must use this exact format:

```
time range / effect / parameters / reason / expected impact
```

Example: `00:02:14.200-00:02:16.000 / setpts + atempo / 0.75x video and 1.333333x audio / make the final elimination readable / clearer payoff without changing pitch`.

For speed changes, state the synchronized speed multiplier. For fade or flash, state the affected range and duration. A hard cut is the normal join between approved segments; record `hard` only when the proposal needs to call out that choice. Do not render an enhancement until its proposal is approved and recorded in `effects`.
