"""Fixed-parameter mono/cross-camera residuals; no calibration optimization."""
import numpy as np


def stats(vectors):
    a = np.asarray(vectors, dtype=float).reshape(-1, 2)
    if len(a) == 0:
        return {'count': 0}
    if not np.isfinite(a).all():
        raise ValueError('Non-finite residuals')
    norms = np.linalg.norm(a, axis=1)
    return {'count': len(a), 'mean_xy_px': a.mean(axis=0).tolist(),
            'std_xy_px': a.std(axis=0).tolist(), 'rms_l2_px': float(np.sqrt(np.mean(norms**2))),
            'median_l2_px': float(np.median(norms)), 'p95_l2_px': float(np.percentile(norms, 95)),
            'max_l2_px': float(norms.max())}


def cross_residuals(obs_a, obs_b, geometry_b, transform_b_a):
    """A's independently estimated board pose + fixed stereo transform predicts B."""
    ids_a = np.asarray(obs_a.getCornersIdx()).reshape(-1)
    ids_b = np.asarray(obs_b.getCornersIdx()).reshape(-1)
    if len(set(ids_a)) != len(ids_a) or len(set(ids_b)) != len(ids_b):
        raise ValueError('Duplicate corner identifiers')
    xyz_a = np.asarray(obs_a.getCornersTargetFrame()).reshape(-1, 3)
    uv_b = np.asarray(obs_b.getCornersImageFrame()).reshape(-1, 2)
    if len(ids_a) != len(xyz_a) or len(ids_b) != len(uv_b):
        raise ValueError('Corner array size mismatch')
    target_to_b = transform_b_a * obs_a.T_t_c().inverse()
    rotation = np.asarray(target_to_b.C()).reshape(3, 3)
    translation = np.asarray(target_to_b.t()).reshape(3)
    common = sorted(set(ids_a).intersection(ids_b))
    index_a, index_b = {v:i for i,v in enumerate(ids_a)}, {v:i for i,v in enumerate(ids_b)}
    rows = []
    for corner_id in common:
        point_b = rotation @ xyz_a[index_a[corner_id]] + translation
        projected = np.asarray(geometry_b.euclideanToKeypoint(point_b)).reshape(2)
        observed = uv_b[index_b[corner_id]]
        if not np.isfinite(projected).all():
            raise ValueError('Non-finite cross-camera projection')
        rows.append((int(corner_id), observed, projected, projected-observed))
    return rows


def coverage(corners, width, height, cols=8, rows=6):
    grid = np.zeros((rows, cols), dtype=int)
    outside = 0
    for x, y in np.asarray(corners).reshape(-1, 2):
        if not (np.isfinite(x) and np.isfinite(y)):
            raise ValueError('Non-finite detected pixel')
        if not (0 <= x < width and 0 <= y < height):
            outside += 1
            continue
        grid[min(rows-1,int(y*rows/height)), min(cols-1,int(x*cols/width))] += 1
    return grid, outside
