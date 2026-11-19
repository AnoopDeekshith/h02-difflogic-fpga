"""Validation selection contracts. Activity here is settled logical activity, not energy."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from . import hard

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "train_validation_selection_v2"
SOURCE_FILES = ("scripts/train.py", "dlgn/experiment.py", "dlgn/data.py",
                "dlgn/model.py", "dlgn/hard.py", "dlgn/gates.py",
                "scripts/select_validation_models.py", "scripts/evaluate_selected_model.py")
MATCHED_ARGS = ("dataset", "pool", "width", "depth", "tau", "epochs", "bs", "lr",
                "act_mode", "seed", "split_seed", "val_frac", "device")
RUN_FILES = ("model.json", "checkpoint.pt", "metrics.json", "protocol.json",
             "selection_policy.json",
             "split_indices.npz", "x_validation_bits.npy", "y_validation.npy",
             "validation_scores.npy", "validation_classes.npy")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_identity(value):
    a = np.ascontiguousarray(value)
    header = json.dumps(dict(shape=list(a.shape), dtype=a.dtype.str), sort_keys=True).encode()
    return hashlib.sha256(header + b"\n" + a.tobytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def validate_policy(policy):
    if policy.get("schema") != "validation_selection_policy_v1":
        raise ValueError("Unsupported selection policy")
    drop = policy.get("max_accuracy_drop_pp")
    if type(drop) not in (int, float) or not math.isfinite(drop) or not 0 <= drop <= 100:
        raise ValueError("Accuracy budget must be finite percentage points from 0 to 100")
    if policy.get("ranking") != "min_switching_then_max_accuracy_then_min_lambda_then_model_hash":
        raise ValueError("Unsupported selection ranking")
    return drop


def source_hashes():
    return {name: digest(ROOT / name) for name in SOURCE_FILES}


def hard_metrics(net, x, y):
    """Integer score/class reference and exact adjacent-image count/denominator."""
    if len(x) < 2:
        raise ValueError("Activity requires at least two ordered validation images")
    states = np.concatenate(hard.forward_bits(net, x), axis=1)
    changes = int(np.count_nonzero(states[1:] != states[:-1]))
    opportunities = int((len(x) - 1) * states.shape[1])
    scores = hard.scores(net, x)
    classes = scores.argmax(1)
    return dict(ref_acc=float((classes == y).mean()),
                ref_toggle_rate=changes / opportunities, changes=changes,
                opportunities=opportunities, image_pairs=len(x) - 1,
                n_gates=int(states.shape[1])), scores, classes


def seal_run(folder, initial_sources):
    if source_hashes() != initial_sources:
        raise ValueError("Training sources changed during the run")
    manifest = dict(schema=SCHEMA, source_sha256=initial_sources,
                    files_sha256={name: digest(folder / name) for name in RUN_FILES})
    # Test artifacts are optional; validation-only runs must not produce them.
    for name in ("x_test_bits.npy", "y_test.npy"):
        if (folder / name).exists():
            manifest["files_sha256"][name] = digest(folder / name)
    write_json(folder / "manifest.json", manifest)
    write_json(folder / "status.json", dict(status="passed", manifest_sha256=digest(folder / "manifest.json")))


def read_validation_run(folder):
    """Recheck archived artifacts and recompute selection quantities from NumPy."""
    folder = Path(folder).resolve()
    status = json.loads((folder / "status.json").read_text())
    if status.get("status") != "passed" or status.get("manifest_sha256") != digest(folder / "manifest.json"):
        raise ValueError(f"Run is incomplete or its manifest changed: {folder}")
    manifest = json.loads((folder / "manifest.json").read_text())
    if manifest.get("schema") != SCHEMA or set(manifest["files_sha256"]) != set(RUN_FILES):
        raise ValueError("Selection requires a complete validation-only run")
    for name, expected in manifest["files_sha256"].items():
        if digest(folder / name) != expected:
            raise ValueError(f"Changed training artifact: {name}")
    metrics = json.loads((folder / "metrics.json").read_text())
    protocol = json.loads((folder / "protocol.json").read_text())
    policy = json.loads((folder / "selection_policy.json").read_text())
    validate_policy(policy)
    if protocol["selection_policy_sha256"] != digest(folder / "selection_policy.json"):
        raise ValueError("Run's predeclared selection policy changed")
    if (metrics.get("evaluation_protocol") != SCHEMA or metrics.get("test_evaluated") is not False
            or not metrics["args"].get("defer_test") or metrics["args"] != protocol["args"]):
        raise ValueError("Candidate must defer test evaluation and retain matching configuration")
    if any(metrics.get(k) is not None for k in ("soft_acc", "hard_acc", "ref_acc", "ref_toggle_rate", "discretization_gap")):
        raise ValueError("Validation-only candidate contains test results")
    x = np.load(folder / "x_validation_bits.npy", allow_pickle=False)
    y = np.load(folder / "y_validation.npy", allow_pickle=False)
    if x.dtype != np.bool_ or y.ndim != 1 or len(x) != len(y):
        raise ValueError("Invalid archived validation workload")
    if (array_identity(x) != protocol["validation_inputs_identity"]
            or array_identity(y) != protocol["validation_labels_identity"]):
        raise ValueError("Validation data identity mismatch")
    net = hard.load(folder / "model.json")
    with np.load(folder / "split_indices.npz", allow_pickle=False) as indices:
        if protocol["split_identity"] != {k: array_identity(indices[k]) for k in ("train", "validation")}:
            raise ValueError("Archived split indices disagree with protocol")
        tr, va = indices["train"], indices["validation"]
        if (len(va) != len(x) or len(tr) != metrics["n_train"]
                or len(np.unique(np.concatenate([tr, va]))) != len(tr) + len(va)
                or set(np.concatenate([tr, va]).tolist()) != set(range(len(tr) + len(va)))):
            raise ValueError("Split indices are not disjoint and complete")
    for key in ("width", "depth", "tau", "seed"):
        if net[key] != metrics["args"][key]:
            raise ValueError(f"Model configuration mismatch: {key}")
    reference, scores, classes = hard_metrics(net, x, y)
    if metrics["validation"] != reference:
        raise ValueError("Validation metrics disagree with fresh NumPy reference")
    if not np.array_equal(scores, np.load(folder / "validation_scores.npy", allow_pickle=False)):
        raise ValueError("Archived validation scores disagree")
    if not np.array_equal(classes, np.load(folder / "validation_classes.npy", allow_pickle=False)):
        raise ValueError("Archived validation classes disagree")
    if not metrics.get("validation_torch_vs_ref_scores_match") or not metrics.get("validation_torch_vs_ref_classes_match"):
        raise ValueError("Hard PyTorch/NumPy comparison did not pass")
    return dict(directory=str(folder), manifest_sha256=digest(folder / "manifest.json"),
                model_sha256=digest(folder / "model.json"), metrics=metrics,
                protocol=protocol, source_sha256=manifest["source_sha256"])


def select_validation(control_folder, candidate_folders, policy):
    """One matched model seed per selection; include the control in the choice."""
    drop = validate_policy(policy)
    control = read_validation_run(control_folder)
    if control["metrics"]["args"]["act_weight"] != 0:
        raise ValueError("Control must have lambda zero")
    runs = [control]
    for folder in candidate_folders:
        candidate = read_validation_run(folder)
        if candidate["directory"] in {r["directory"] for r in runs}:
            raise ValueError("Duplicate run in selection")
        runs.append(candidate)
    floor = control["metrics"]["validation"]["ref_acc"] - drop / 100
    for run in runs:
        if json.loads((Path(run["directory"]) / "selection_policy.json").read_text()) != policy:
            raise ValueError("Selection policy differs from the one saved before training")
        a, b = control["metrics"]["args"], run["metrics"]["args"]
        if any(a[key] != b[key] for key in MATCHED_ARGS):
            raise ValueError("Unmatched architecture, seed, budget, or training settings")
        for key in ("train_inputs_identity", "train_labels_identity", "validation_inputs_identity",
                    "validation_labels_identity", "split_identity", "versions", "dataset_partition_seed"):
            if run["protocol"][key] != control["protocol"][key]:
                raise ValueError(f"Unmatched data/protocol: {key}")
        if run["source_sha256"] != control["source_sha256"]:
            raise ValueError("Unmatched training source code")
        weight = b["act_weight"]
        if type(weight) not in (int, float) or not math.isfinite(weight) or weight < 0:
            raise ValueError("Invalid penalty strength")
        run["eligible"] = run["metrics"]["validation"]["ref_acc"] + 1e-12 >= floor
    eligible = [r for r in runs if r["eligible"]]
    winner = min(eligible, key=lambda r: (r["metrics"]["validation"]["ref_toggle_rate"],
                                         -r["metrics"]["validation"]["ref_acc"],
                                         r["metrics"]["args"]["act_weight"], r["model_sha256"]))
    rows = [dict(directory=r["directory"], manifest_sha256=r["manifest_sha256"],
                 model_sha256=r["model_sha256"], eligible=r["eligible"],
                 act_weight=r["metrics"]["args"]["act_weight"], **r["metrics"]["validation"])
            for r in runs]
    return dict(schema="validation_selection_v1", policy=policy, accuracy_floor=floor,
                control_directory=control["directory"], selected_directory=winner["directory"],
                selected_model_sha256=winner["model_sha256"], candidates=rows,
                scope="One matched seed; settled validation switching only; not hardware energy")
