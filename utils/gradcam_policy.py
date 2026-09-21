"""Explicit Grad-CAM execution policy, independent of torch and camera modules."""


def gradcam_mode(value: str) -> str:
    mode = str(value or 'always').strip().lower()
    if mode not in ('always', 'off', 'on_demand'):
        raise ValueError('GRADCAM_MODE must be always, off, or on_demand')
    return mode


def should_generate_gradcam(mode: str, *, on_demand: bool = False) -> bool:
    mode = gradcam_mode(mode)
    return mode == 'always' or (mode == 'on_demand' and on_demand)


def gradcam_result_state(mode: str, has_heatmap: bool) -> str:
    if has_heatmap:
        return 'generated'
    mode = gradcam_mode(mode)
    if mode == 'off':
        return 'disabled'
    if mode == 'on_demand':
        return 'available_on_demand'
    return 'generation_failed'
