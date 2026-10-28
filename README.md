# H02: Differentiable Logic Gate Networks on FPGA

ECE 210 (Brain-Inspired Machine Learning), UC Santa Cruz.

Train a network where every neuron is a two-input logic gate (Petersen et al.,
"Deep Differentiable Logic Gate Networks", NeurIPS 2022), lock each gate to one
rule, export the result as Verilog, and prove the hardware matches the software
bit for bit. Extension: measure switching power and train the network to switch less.

## Pipeline

```
train (soft gates)  ->  discretize (hard gates)  ->  Verilog + testbench  ->  simulate (bit-exact)  ->  synthesize (LUTs, Fmax, power)
scripts/train.py        dlgn/hard.py                  scripts/export.py         sim/run_sim.sh             synth/
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q        # should print: 4 passed
```

## Toy run (8x8 digits, about a minute on a laptop CPU)

```bash
python scripts/train.py --dataset digits --width 1000 --depth 4 --tau 10 --epochs 60 --out runs/digits_w1000
python scripts/export.py runs/digits_w1000
bash sim/run_sim.sh runs/digits_w1000/rtl_comb   # expect: PASS
```

## Layout

| Path | What it does |
|---|---|
| `dlgn/gates.py` | The 16 gates: truth tables, soft formulas, Verilog expressions |
| `dlgn/model.py` | The trainable network (logic layers + group sum), plus the switching-activity penalty |
| `dlgn/hard.py` | Bit-exact NumPy reference model (the "golden model" the RTL must match) |
| `dlgn/export_verilog.py` | Writes `dlgn_top.sv`, a self-checking testbench, and test vectors |
| `dlgn/difflogic_import.py` | Converts a model trained with the official difflogic library |
| `scripts/train.py` | Train, discretize, report soft vs. hard accuracy |
| `scripts/export.py` | Export a trained run to RTL |
| `sim/run_sim.sh` | Run the testbench with Verilator, Icarus, or Vivado xsim |
| `tests/` | Gate-table checks and a random-network RTL vs. software check |
