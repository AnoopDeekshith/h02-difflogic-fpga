"""Datasets, binarized into bit vectors.

digits : scikit-learn's bundled 8x8 handwritten digits (1,797 images).
         Works offline, trains in about a minute on a laptop CPU. This is the
         toy task for confirming the whole flow.
mnist  : 28x28 MNIST via torchvision (downloads on first use).
         `pool=2` gives the 14x14 "reduced MNIST" option.

Encoding: thermometer code. For thresholds t1 < t2 < ..., each pixel
becomes bits [x > t1, x > t2, ...]. With one threshold at 0.5 this is
plain binarized MNIST, as in the paper.
"""
import numpy as np
import torch


def thermometer(x, thresholds):
    """x: (N, P) float in [0, 1]. Returns (N, P * len(thresholds)) float {0,1}."""
    bits = [(x > t) for t in thresholds]
    return np.stack(bits, axis=2).reshape(x.shape[0], -1).astype(np.float32)


def load_digits(thresholds=(0.25, 0.5, 0.75), test_frac=0.25, seed=0):
    from sklearn.datasets import load_digits as _ld
    from sklearn.model_selection import train_test_split
    d = _ld()
    x = d.data / 16.0
    xtr, xte, ytr, yte = train_test_split(
        x, d.target, test_size=test_frac, random_state=seed, stratify=d.target)
    return (thermometer(xtr, thresholds), ytr.astype(np.int64),
            thermometer(xte, thresholds), yte.astype(np.int64))


def load_mnist(root="data", thresholds=(0.5,), pool=1):
    from torchvision import datasets
    out = []
    for train in (True, False):
        ds = datasets.MNIST(root, train=train, download=True)
        x = ds.data.float() / 255.0
        if pool > 1:
            x = torch.nn.functional.avg_pool2d(x[:, None], pool)[:, 0]
        x = x.reshape(x.shape[0], -1).numpy()
        out += [thermometer(x, thresholds), ds.targets.numpy().astype(np.int64)]
    return tuple(out)


def get(name, **kw):
    if name == "digits":
        return load_digits(**kw)
    if name == "mnist":
        return load_mnist(**kw)
    raise ValueError(name)
