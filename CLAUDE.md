# H02: Differentiable Logic Gate Networks on FPGA

Project background, dates, plan, status and how Anoop wants to work:
@docs/PROJECT_CONTEXT.md

## How to help

- Anoop is learning this deeply. Explain one small piece at a time, in plain language,
  with a concrete example (What, How, Where, Why, When).
- Wait for him to say "yes, understood" before moving to the next piece.
- Say what a command will do before running anything long or heavy.
- When changing code, explain the change so he understands it.
- When something is decided or finished, update the Status section of docs/PROJECT_CONTEXT.md.

## Base paper

Petersen et al., "Deep Differentiable Logic Gate Networks", NeurIPS 2022.
Local copy: `docs/papers/petersen2022_difflogic.pdf` (kept out of git).
Read the relevant part when an answer depends on the paper instead of guessing:

- Sec. 3-4: logic gate networks and the differentiable relaxation; Table 1 = the 16 gates
- Sec. 4.1: training considerations (GroupSum, tau, initialization, discretization gap)
- Sec. 6, Table 4: MNIST results (small model: 6 x 8,000 gates, 97.69%)
- Sec. 6.5: distribution of learned gates
- Appendix Table 6: architectures and tau per dataset; Table 8: training times

## Commands

```bash
source .venv/bin/activate
python -m pytest tests -q                       # 4 passed
python scripts/train.py --dataset digits --width 1000 --depth 4 --tau 10 --epochs 60 --out runs/digits_w1000
python scripts/export.py runs/digits_w1000      # add --pipeline for 1 register per layer
bash sim/run_sim.sh runs/digits_w1000/rtl_comb  # expect PASS (bit-exact)
```

## Rules for the code

- `dlgn/hard.py` is the golden model. RTL must match its integer class scores and argmax
  bit for bit, with argmax ties going to the lowest class index.
- Gate IDs follow the paper's Table 1: `out = (id >> (3 - (2a + b))) & 1`.
- Activity penalty uses p = batch-mean soft output per gate (`--act-mode batch`).
  The per-sample variant is an ablation only.
