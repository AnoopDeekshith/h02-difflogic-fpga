# H02 Logic Gate Network Project Explained

## A learning guide to the work completed before section 4

Prepared for Anoop on November 17, 2026. Results in this guide come from the saved experiments and independent reviews through November 16. Preparing this guide did not rerun training, implementation, or simulation.

**Where we stand:** we have a small trained digit recognizer, a verified translation into hardware, one FPGA implementation that meets its clock requirement, and several checked ways to measure switching. We are now ready to investigate whether changing training can reduce switching while retaining useful recognition accuracy. We have not yet demonstrated lower power or lower energy.

This guide covers every numbered task in sections 1, 2, and 3. “Through 4.0” means the point immediately before the section 4 experiments. A short final part explains what section 4 and the later sections will do. Some section 2 items remain partial because the fully pipelined design cannot fit the selected FPGA; their successful parts and limitations are both included.

## How to read this guide

Read the big picture first, then section 1 for the model, section 2 for the hardware, and section 3 for switching measurement. Each numbered step explains the question we needed to answer, the work performed, the evidence, and what that evidence allows us to conclude. Examples are teaching examples unless explicitly identified as measured project results.

The most useful distinction to remember is this: **a model can recognize an image incorrectly while the hardware implements that model perfectly**. We separately check recognition quality, hardware correctness, physical feasibility, switching, and energy. They answer different questions.

## The project in one picture

```text
8 by 8 grayscale digit image
        |
Convert 64 pixel values into 192 bits
        |
Train four layers of 1000 two input logic gates
        |
Choose one fixed rule for each gate
        |
NumPy reference computes exact scores and class
        |
Export the same fixed network to Verilog
        |
Check software and hardware outputs agree
        |
Map the design to FPGA cells and check timing
        |
Measure logical changes and simulated hardware activity
        |
NEXT  Train matched models with a switching penalty
        |
LATER  Establish power and energy tradeoffs
```

The class project establishes the path from training to an FPGA workflow. Your extension asks a further question: can we make the learned gate rules reduce the hardware's switching, and ultimately its energy per prediction, without losing too much accuracy? The measurements completed so far give us a way to test that question. They do not yet answer it.

## A small vocabulary before the details

**Bit and logic gate.** A bit is zero or one. A two-input logic gate takes two bits and produces one bit according to a truth table. AND produces one only when both inputs are one. XOR produces one when its inputs differ.

**Logic gate network.** Several layers of such gates form the recognizer. Each gate has two incoming connections. In this project, connections are selected when the model is built and remain fixed during training; training learns which rule each gate should use.

**Soft and hard model.** During soft training, a gate is a weighted mixture of possible rules and may output a value between zero and one. The hard model uses one selected Boolean rule per gate and outputs actual bits. “Discretization” means making that selection.

**RTL and Verilog.** Register transfer level, or RTL, describes hardware behavior around registers and combinational logic. Verilog/SystemVerilog is the language used to write that description. An RTL file is a hardware design description, not evidence that a board has run it.

**FPGA and LUT.** An FPGA contains configurable hardware blocks and routing. A LUT4 is a lookup table capable of implementing a Boolean function of up to four inputs. A learned two-input gate is not necessarily one FPGA LUT: synthesis can simplify, merge, or remove logic.

**Register, flip-flop, and clock.** A flip-flop stores one bit, usually updating at a clock edge. A register is a collection of stored bits. The clock schedules those updates. At 12 MHz, a clock period is about 83.33 nanoseconds.

**Synthesis, packing, placement, and routing.** Synthesis translates RTL into device primitives. Packing groups primitives into physical logic cells. Placement selects locations; routing connects them. All four matter before claiming a design fits and meets timing.

**Latency and throughput.** Latency is the delay for one image between defined boundaries. Throughput is the rate at which completed results can be produced. An assembly line can take several cycles per item but still start a new item every cycle.

**Switching, power, and energy.** Switching is a change in a signal value. Power is the rate of energy consumption, measured in watts. Energy is the accumulated consumption, measured in joules. Counting changes does not directly measure watts or joules because different wires and cells have different electrical loads, and clocks and other activity also consume power.

A useful simplified teaching equation is `dynamic power approximately equals alpha * C * V^2 * f`. Here alpha describes switching activity under the chosen counting convention, C is effective switched capacitance, V is supply voltage, and f is clock frequency. It explains why reducing activity might help when other factors stay comparable. We have not measured the required capacitances or supplied a complete device power model. One transition on a large routed load can cost more energy than one on a small local wire, and extra registers can add clock activity. Static power is another contribution even when data is not changing.

# Section 1  Build and verify the digit recognition model

## Step 1.1  Prepare the toy dataset

We began with the small handwritten-digits dataset bundled with scikit-learn. It contains 1,797 grayscale images, each with 8 by 8 pixels. This is a manageable test problem for checking the entire software-to-hardware path before attempting a larger dataset.

A pixel originally has a brightness value from 0 to 16. We divide by 16 to normalize brightness to the range zero to one. A logic network needs bits, so each pixel is compared with three thresholds: 0.25, 0.50, and 0.75. Each comparison uses “greater than,” so a pixel exactly at a threshold does not pass that threshold.

For example, brightness 0.60 becomes `[1, 1, 0]`: it exceeds the first two thresholds but not the third. Brightness 0.10 becomes `[0, 0, 0]`; brightness 0.90 becomes `[1, 1, 1]`. This is called **thermometer encoding**, because higher brightness fills progressively more bit positions.

Each image therefore becomes 64 pixels times 3 bits, or **192 input bits**. Grayscale describes the original image; thermometer encoding describes how we represent it for the network. Gray coding is a different encoding and has not been tested here.

The historical baseline used 1,347 training images and 450 test images, with class proportions preserved and split seed zero. A later correction creates a validation set for new experiments, explained after section 2. The saved old model retains its historical split and results.

## Step 1.2  Implement all sixteen two input logic rules

Two Boolean inputs have four possible combinations: `00`, `01`, `10`, and `11`. A rule can independently choose zero or one for each combination, giving 2 to the power of 4, or **16 possible rules**. These include AND, OR, XOR, constant zero, constant one, input forwarding, and negated rules.

We give each rule an ID by reading its four output bits in that input order, from most significant to least significant. AND has truth-table outputs `0001`, so its ID is 1. XOR has outputs `0110`, so its ID is 6. Keeping this convention consistent matters: a mismatch between Python and Verilog would silently change the model.

The implementation contains Boolean truth tables, differentiable soft formulas, and corresponding Verilog expressions. Tests exercise all 16 rules at all four Boolean input combinations. The soft formulas must agree with the Boolean rules when their inputs are exactly zero or one. That establishes the basic building blocks before we connect thousands of gates.

## Step 1.3  Build the trainable network

Directly choosing one of 16 rules is a discrete decision, which is difficult to optimize using ordinary gradients. Instead, every gate starts with 16 trainable numbers. A softmax turns those numbers into positive mixture weights that add up to one. The gate's soft output is the weighted sum of the 16 rule outputs.

For a teaching example, if AND has weight 0.7 and OR has weight 0.3, inputs `1, 0` produce approximately 0.3 from that simplified mixture. Training adjusts the weights so that, after several layers, the correct digit receives a high score. The actual code keeps all 16 alternatives, not just these two.

The baseline has **four layers with 1,000 gates each**, or 4,000 learned gate slots. Every gate reads two positions from the previous layer. Connections are selected at initialization using a seeded random construction; gradient training changes gate-choice weights, not connection indices.

The final 1,000 outputs are split into ten groups of 100, one group for each digit. **GroupSum** sums a group's outputs to form that digit's score. In the hard model, a score is an integer from 0 to 100. If 37 gates in digit 5's group output one, digit 5 receives raw score 37.

During training the head divides all group sums by `tau = 10`. This changes the scale used by the classification loss. Hardware uses the raw integer sums. Dividing all scores by the same positive number does not change which class is largest.

## Step 1.4  Train the unpenalized baseline

We trained the toy network for **60 epochs**, using seed zero, batch size 100, the Adam optimizer, and learning rate 0.01. An epoch means one pass through the training examples; minibatches are smaller groups processed during that pass. The switching-penalty weight was zero, so this run optimized recognition without a switching objective.

The saved experiment is `runs/digits_w1000`. It contains the selected gates and connections in `model.json`, metrics and arguments in `metrics.json`, and the saved test inputs and labels. These files are the starting point for the later hardware and activity work. The baseline was not retrained each time a measurement script was added.

There is a methodological limitation: the historical training procedure monitored test accuracy during training. Repeatedly inspecting the test set can influence choices, even unintentionally. We preserve this model as an **exploratory baseline**, rather than presenting it as a clean validation-selected research result. New control and penalty runs must use the corrected protocol.

## Step 1.5  Lock each gate to one rule

After soft training, each gate chooses the rule with its largest learned weight. The other 15 alternatives disappear from inference. This converts the relaxed model into a Boolean network that can be implemented with ordinary digital logic.

For example, if a gate's highest weight belongs to XOR, the exported model stores XOR's ID, 6, together with the two input indices. It no longer needs a softmax or a weighted sum when recognizing an image. The hardware evaluates the chosen XOR rule directly.

The saved JSON is the common handoff: NumPy and the Verilog exporter read the same gate IDs and connections. Discretization may change predictions because a mixture and its largest component need not behave identically. We therefore measured that change rather than assuming it was harmless.

## Step 1.6  Measure recognition accuracy and the discretization gap

Recognition accuracy compares the predicted digit with the dataset's actual digit label. On the historical 450-image test set:

| Version | Correct images | Accuracy |
|---|---:|---:|
| Soft model | 422 of 450 | 93.78 percent |
| Hard model | 421 of 450 | 93.56 percent |
| NumPy hard reference | 421 of 450 | 93.56 percent |

The **discretization gap** is about **0.22 percentage points**, corresponding to one fewer correct image. This tells us that hardening the model had a small accuracy cost in this experiment. It does not establish the same gap for other seeds, datasets, widths, or penalty strengths.

A crucial example: suppose the true image is digit 8, and both Python and RTL predict 3 with identical scores. That is a recognition error, but the hardware translation is correct. Conversely, Python and RTL might both predict 8 while disagreeing on one score; recognition succeeds, but exact implementation verification fails.

## Step 1.7  Build the independent NumPy reference

We created a separate hard-model implementation in `dlgn/hard.py`, using NumPy rather than the trainable PyTorch layers. It is the project's **golden reference**: hardware must match its integer scores and predicted class.

For each layer, it gathers the saved two inputs for every gate and looks up the selected rule's bit. It then sums the last-layer bits by class. Prediction chooses the greatest score. If several classes tie, the **lowest class index wins**. With scores `[3, 7, 7]`, class 1 wins, not class 2.

Hard PyTorch scores are divided by tau, whereas NumPy scores are raw integers. The check multiplies the PyTorch scores by tau before comparing, allowing small floating-point roundoff on that side. The saved baseline confirms agreement. The separate implementation reduces the risk that a single shared coding mistake hides across the model and exporter, although no finite collection of tests proves universal correctness.

## Step 1.8  Export the network as Verilog

The exporter turns each selected gate into a Verilog expression and connects it to the saved input indices. It builds balanced adder trees to count ones in each class group, then chooses the highest-scoring class while preserving the lowest-index tie rule.

A gate selecting XOR and connected to inputs 2 and 9 becomes an expression equivalent to `input[2] ^ input[9]`. Hardware synthesis can later simplify or combine these expressions. The exporter also adds input and output registers and a delayed valid signal identifying meaningful results.

The original core has two register stages: input capture and output storage. From the edge that captures an image, its output becomes available one elapsed clock period later; a downstream register captures that result on the following edge. The distinction between register-stage count and elapsed periods is explained fully in step 2.10.

## Step 1.9  Generate reference vectors and a self checking testbench

A simulator needs inputs and expected answers. We generated hexadecimal files containing encoded image bits, expected integer scores, and expected classes. A **testbench** is the simulation program that drives the hardware description and checks its responses.

The files include `x.hex`, `exp_scores.hex`, `exp_class.hex`, and `tb_dlgn.sv`. Input bit zero is the least significant bit in its packed word. Class zero occupies the lowest score positions. A consistent packing convention prevents accidental bit reversal.

The testbench streams images and checks every score and class whenever output valid is asserted. Checking scores is stronger than checking only the winner. For example, scores 37 and 36 may still lead to the same winning digit, but their mismatch reveals an implementation defect that a class-only check would miss.

## Step 1.10  Verify the hardware bit for bit

We simulated the exported design and compared its outputs with the NumPy answers. The original core passed **450 of 450 saved images**, including all ten integer class scores and the predicted class. The fully layer-pipelined version later passed the same check.

“450 of 450 exact” does not mean 100 percent digit-recognition accuracy. It means 100 percent agreement with the reference for those supplied inputs. Recognition remains 421 correct labels out of 450 for the hard model.

This is also not formal equivalence over every possible input. A 192-bit input space contains vastly more patterns than the 450 digit images. Smaller exhaustive synthetic tests strengthen specific logic and pipeline checks, but the trained model's reported result remains a finite-vector verification result.

## Step 1.11  Maintain regression tests

Regression tests repeatedly check important properties as the project changes. They cover gate truth tables, soft formulas, randomly generated networks, register configurations, score ties, UART handling, constraints, stale artifacts, waveform counting, measurement windows, and report consistency.

The latest saved independent review, at step 3.10, records **255 tests passing with no skips**, in 13.94 seconds after its corrections. Earlier notes list smaller totals because they describe earlier stages. Those numbers are historical snapshots, not competing current totals. This guide did not rerun that suite.

Tests include deliberate failures: changing an archived file, bypassing a synchronizer, or injecting an input pulse must cause rejection. Independent verification also used separate decoders and counting implementations, rather than relying only on the production script's own assertions. These checks are evidence of care within their scope, not a guarantee against every possible defect.

# Section 2  Establish FPGA cost and feasible performance

## Step 2.1  Synthesize the original core

We used Yosys to map the original Verilog core to iCE40 FPGA primitives. Synthesis answers what configurable logic the design needs after simplification; it does not yet establish physical fit or clock speed.

The original **core-only** result was **2,929 LUT4s, 268 flip-flops, and 123 carry cells**. Carry cells help implement arithmetic such as the score sums. These numbers exclude the UART interface.

Why are there fewer than 4,000 LUTs when the network has 4,000 learned gates? A gate that always outputs zero may disappear, forwarding rules may become wires, and several expressions may fit into one LUT. Learned gate count and mapped hardware cost describe different things. This is one reason a training objective that counts logical activity must later be checked after synthesis.

## Step 2.2  Add a register after every logic layer

We exported a second architecture using `--pipeline`. It stores each of the four learned layers' outputs in registers, creating shorter combinational sections. The trained rules and connections stay the same.

Think of four workers in an assembly line. One image occupies each stage while a newer image enters behind it. More stages increase the delay for a single image in clock periods, but can allow a faster clock if the resulting hardware fits and meets timing.

This version has six register stages: input, four layer boundaries, and output. Its result becomes available five elapsed periods after input capture; downstream capture occurs after six. It can accept one new input each cycle in RTL simulation. That ability alone does not prove a faster physical implementation.

## Step 2.3  Verify the pipelined version

Adding registers can misalign data and valid indicators even when the Boolean equations are unchanged. We therefore replayed the same 450 images and exact reference scores through the pipelined core.

It passed **450 of 450 images**, checking every score and class. This verifies that the added delay does not change the computed result for those vectors. Random-network tests also exercise the register configuration.

A typical bug would be comparing image A's delayed result with image B's expected answer. The delayed valid signal and ordered checks make this visible. Functional success here does not resolve resource capacity or achievable clock frequency; those require the implementation flow below.

## Step 2.4  Measure the resource cost of full layer pipelining

The pipelined core synthesized to **4,528 LUT4s, 3,523 flip-flops, and 123 carry cells**. Compared with the original core, it requires many more stored intermediate bits and more LUTs. Register boundaries also prevent some optimization across layers.

| Historical core-only design | LUT4s | Flip-flops | Carry cells | Register stages |
|---|---:|---:|---:|---:|
| Original core | 2,929 | 268 | 123 | 2 |
| Registers after every layer | 4,528 | 3,523 | 123 | 6 |

We cannot simply add LUT and flip-flop counts to predict cell usage. A physical logic cell can sometimes hold compatible logic and a register together; other combinations require separate cells. Packing determines the actual requirement. The complete pipelined UART design subsequently exceeds capacity.

## Step 2.5  Establish the FPGA implementation tool flow

The selected target is the **iCE40 UltraPlus UP5K in the SG48 package**, associated with the iCEBreaker board. It has 5,280 logic cells. The recorded flow uses Yosys 0.63, nextpnr-ice40 0.11.1_2, and IceStorm 1.1_1.

Before debugging a large neural network, we ran a small 24-bit counter through synthesis, packing, placement, routing, timing, and bitstream generation. A **bitstream** is the configuration data that can program an FPGA. This small test established that the toolchain itself worked.

The counter used 28 packed cells and met the fixed 12 MHz requirement. Its estimated maximum frequency was 79.74 MHz. That frequency belongs to the counter, not the digit recognizer. The counter bitstream was generated but not programmed onto a board.

## Step 2.6  Add a practical serial interface

The raw core has a large parallel interface, unsuitable for direct laptop wiring. We added a UART adapter so a laptop can send encoded images and receive predictions over the board's existing USB-to-serial bridge. The FPGA top exposes four signals: clock, active-low reset button, serial receive, and serial transmit.

UART is configured as **8N1**: eight data bits, no parity, one stop bit, plus a start bit for each byte. The nominal baud rate is 115,200. With a 12 MHz clock and an integer divider of 104 clocks per bit, the actual generated rate is about **115,384.6 baud**, or 0.16 percent above nominal.

```text
Request  26 bytes
A5 5A  followed by 24 encoded image bytes

Reply  13 bytes
5A A5  predicted class  score 0 through score 9
```

The request contains the 192 already encoded bits, not raw grayscale pixels. Byte zero holds bits zero through seven. Each score fits in one unsigned byte because the maximum is 100. The laptop must send one request and wait for the complete reply; there is no queue or hardware flow control.

The adapter handles overlapping header prefixes, incomplete requests, reset, framing errors, and an approximately 250 millisecond receive timeout. There is no checksum or automatic retry, so a valid-looking byte with corrupted data is not detected by framing alone. RX uses a two-stage synchronizer; reset asserts asynchronously and releases synchronously.

Both historical UART architectures passed all 450 simulated images using an accelerated eight-clocks-per-bit testbench setting. Focused tests use the real 104-cycle divider. Acceleration affects the testbench, not generated hardware. A live serial host client and actual board communication remain future work.

Adding the adapter also has a hardware cost. These are the historical complete UART designs before the head-pipeline and atomic-image corrections in step 2.8:

| Historical UART design | LUT4s | Flip-flops | Carry cells |
|---|---:|---:|---:|
| Original core with UART | 3,440 | 648 | 167 |
| Full layer pipeline with UART | 5,059 | 3,903 | 167 |

These are synthesis counts, not packed physical-cell requirements. The next step explains why separate LUT and flip-flop counts did not establish that the pipelined version could fit.

## Step 2.7  Add clock and pin constraints and check packing

The implementation tools need to know the physical pins and timing requirement. The pin constraint file maps the 12 MHz clock to SG48 pin 35, reset button to pin 10, RX to pin 6, and TX to pin 9. The clock constraint specifies an approximately 83.333 nanosecond period.

We also check the synthesized connectivity of the RX and reset synchronizers. For RX, only the second sampling register should feed the receiver. These structural checks reduce the risk of a wiring error. They do not model metastability or certify its physical failure probability.

Packing revealed an important limitation:

| Historical UART design before the later correction | Packed cells | Capacity | Outcome |
|---|---:|---:|---|
| Original | 3,795 | 5,280 | Within cell capacity |
| Full layer pipeline | 6,236 | 5,280 | Too large |

The scripts now save the capacity failure and return failure status instead of treating successful packing commands as overall success. No timing exceptions were added to hide internal paths. The asynchronous interface still needs appropriate physical review before deployment.

## Step 2.8  Route the design and fix the timing bottleneck

The original UART design routed, but its **7.26 MHz estimated maximum** failed the unchanged **12 MHz** requirement. Correct RTL simulation could not fix that physical timing problem. We preserved the failed run and changed the architecture.

The solution was a smaller **head-only pipeline**. It stores the ten class scores in a register bank, then finds the winning class using a balanced comparison tree. Instead of serially comparing ten scores, the tree compares pairs and then their winners. Equal scores keep the lower index. This separates score generation from class selection without registering all 4,000 learned outputs.

We also added an **atomic completed-image register** in the UART adapter. Previously, receiving each byte could change part of the core input. Now the core sees a new complete image only after the packet is assembled. Otherwise, partial images would create switching unrelated to actual inference requests and confuse activity comparisons. This change does not add clock gating.

| Candidate | Packed cells | Timing outcome |
|---|---:|---|
| Historical original UART | 3,795 | Routed but failed 12 MHz at 7.26 MHz estimate |
| Corrected head-only pipeline and atomic image input | 4,160 | Routed and passed 12 MHz; estimated maximum 19.3858566 MHz |
| Full layer plus head pipeline and atomic image input | 6,575 | Over 5,280-cell capacity; rejected before routing |

The corrected feasible candidate uses **3,449 LUT4s, 911 flip-flops, and 167 carry cells**. Its three register stages preserve exact scores and predictions. It passed all 450 UART images; a synthesized-cell functional check passed 12 images using the real UART divider. Independent verification reran implementation and added exhaustive synthetic checks, including ties and odd class counts.

These versions differ in several implementation details, so their table records feasibility rather than an isolated experiment proving one change's speedup. Steps 2.8 through 2.10 remain partial as a two-architecture physical comparison because the full pipeline has no routed result.

To keep implementation evidence trustworthy, every attempt uses a fresh output directory and records its final status. Fingerprints bind source files, parameters, and mapped netlists to the reports. A failed new attempt must not inherit old successful outputs. This prevents a stale timing report from being mistaken for a successful implementation of changed hardware.

## Step 2.9  Audit the saved clock estimate

We wrote a report reader that checks archived status, hashes, parameters, target, completed route evidence, capacity, and the final clock result. It avoids accidentally reading an old frequency line or attaching newly exported parameters to an older route.

The saved feasible candidate's **estimated Fmax is 19.3858566 MHz**, corresponding to a slowest synchronous path of **51.584 nanoseconds**. At the required 12 MHz, the available period is about 83.333 nanoseconds, so the implementation meets that requirement.

| Critical path contribution | Delay in nanoseconds |
|---|---:|
| Source register clock-to-output | 1.390 |
| Routed connections | 33.865 |
| Combinational logic | 15.505 |
| Destination setup requirement | 0.824 |
| Total | 51.584 |

The path goes from an input register through gate logic and score summation to a score register. Routing contributes more delay than the Boolean logic itself, showing why gate count alone does not predict speed.

This step revalidated saved implementation evidence; it did not newly route the design or measure a board frequency. The 19.39 MHz estimate is not a change to the operating clock or UART divider. The full pipeline still has no physical Fmax because it does not fit.

## Step 2.10  Define latency and throughput precisely

The parameter `LAT` counts register stages. From the input-capture edge, output availability takes `LAT - 1` elapsed periods; downstream register capture takes `LAT` periods. The feasible head-only design works as follows:

| Clock edge | What happens to one image |
|---|---|
| 0 | Input register captures the image |
| 1 | Score bank captures calculated scores |
| 2 | Output registers present class, scores, and valid after the edge |
| 3 | A downstream register can capture those outputs |

At the qualified 12 MHz, two periods are **166.67 nanoseconds** and three periods are **250 nanoseconds**. These are cycle-equivalent times, not measured physical signal arrival times. The initiation interval is one: the standalone core can accept a new image every clock, giving a calculated interface capacity of **12 million images per second** if supplied continuously.

The UART demo is much slower because it transfers bytes. Its checked request-start to final-reply-stop interval is **40,528.5 clocks**, or **3.377375 milliseconds** at 12 MHz. With the benchmark's ideal immediate host, request starts are 40,529 clocks apart, giving about **296.08 images per second**. USB buffering and operating-system delays are absent.

Adding all request and reply byte times gives 40,560 clocks, but this is not a strict wall-time lower bound: the last request stop bit and the beginning of the reply can overlap on separate wires. The benchmark checks the complete final reply stop bit.

The full layer plus head pipeline has seven stages, six periods to output and seven to downstream capture in RTL simulation. Because it cannot fit, we withhold timing-qualified nanoseconds and throughput. We also keep UART workload power separate from streaming-core capacity when planning future energy calculations.

The performance benchmark itself initially failed with `Missing reply bytes`: it mistook a temporary simulator scheduling state for completion while the last reply byte was starting. The correction changed the testbench to observe the last byte becoming busy and then returning to ready, including its complete stop bit. FPGA RTL was not changed for this fix. The failed evidence remains under `runs/digits_w1000/uart_comb_head/performance.ygvi6bc5/`; independent tests exercise the shipped benchmark and its completion boundary to prevent this mistake from returning.

## The important correction to future training experiments

The original 93.56 percent baseline trained on all 1,347 training-pool examples and exposed test metrics during training. The corrected protocol partitions that pool into **1,077 training images and 270 validation images**, leaving 450 test images separate. A fixed split seed is distinct from the model seed, allowing repeated initializations on the same data partition.

Validation is the practice exam used to select settings. Test is the final exam used after selection. Current code monitors validation during training and saves split indices and a checkpoint, but still evaluates test at the end of each run. Step 4.10 must allow sweeps to defer that evaluation and save validation switching and ordered inputs.

We must retrain both the zero-penalty control and penalized models under the same corrected conditions. Comparing the old larger-training-set baseline with a new smaller-training-set penalty run would change two things at once. The already inspected digits test set also remains exploratory; adding a validation split cannot make past inspection disappear.

# Section 3  Measure switching before claiming energy savings

## Step 3.1  Count logical changes in Python

For every image, NumPy records the four layers' 4,000 Boolean outputs. We compare neighboring images in the saved order and count output bits that differ. There are **449 neighboring pairs** among 450 images.

The baseline has **628,169 changes out of 1,796,000 opportunities**, because 4,000 gates times 449 image pairs equals 1,796,000. The average is **0.34976002 changes per gate per image pair**. This does not mean each gate changes 35 percent of a clock period; it is a fraction of adjacent-image bit comparisons.

For example, states `001`, `101`, and `100` have two changed bits across six bit-pair opportunities, giving one third. The first state establishes the baseline; it is not itself a transition. Input order matters, so we save the sequence rather than treating an unordered image set as a complete workload definition.

## Step 3.2  Verify waveform recording

A **VCD**, or Value Change Dump, records simulated values and timestamps. Before counting it, we checked that enabling recording does not change inference behavior and that the required signals are actually observable.

Fresh eight-image checks covered the original and head-only cores, with recording both off and on. All scores and classes matched in every run. Off produced no VCD; on included clock, reset, valid, image input, layer buses, and outputs, with advancing timestamps and appropriate widths. Source and reference-vector hashes matched across modes.

Waveforms were also viewed using Surfer and the VaporView extension in VS Code. Unknown startup values are not predictions; outputs are meaningful only when reset is inactive and output valid is asserted. One practical detail is that any nonempty `DUMP` environment variable enables recording, including `DUMP=0`.

This step established observability on eight distinct saved images. It was not the later 450-image capture and did not measure power or validate a switching total.

## Step 3.3  Capture the full baseline waveform

We then captured all **450 images in their original saved order**, using the historical model and the feasible head-only standalone core. The workload supplies one image per clock without gaps. This is a streaming core experiment, not slow UART packet traffic.

The nominal clock is 12 MHz. With one-picosecond simulation precision, the chosen period is **83,334 picoseconds**, a declared rounding of the ideal 83,333.333 period. Future matched captures must use the same setting. The FPGA requirement itself remains 12 MHz.

All 450 integer score vectors and classes passed. The capture retained startup, reset, pipeline fill, and drain. It saved transaction indices, an event ledger, original row order, source hashes, tool identities, and fresh reference vectors. Independent decoding checked the actual recorded image words and responses, not just a printed PASS line.

The primary trace is about 6.48 MB and spans about 38.08 microseconds including startup and drain. That whole duration is not automatically an energy denominator. Separate measurement windows are needed to compare corresponding image states at different pipeline positions.

## Step 3.4  Implement a careful waveform transition counter

The parser counts **changed bits**, not simply changed bus records. A bus update from `0011` to `0101` contains two bit changes. It also distinguishes a rise from a fall and keeps unknown or high-impedance states separate from known binary transitions.

The first observed value initializes a signal's state and contributes no toggle. A sequence `0 -> X -> 1` has two unknown-involving changes; the counter does not invent a known `0 -> 1` transition across that gap. Two names sharing one VCD identifier are true aliases and count once. Distinct identifiers remain separate even if they always carry equal values.

The full trace has **1,843,155 known bit changes**, but that total includes clocks, startup, drain, duplicate layer views, output logic, and simulation bookkeeping. It is a diagnostic, not the learned network's useful-work total.

Icarus records one final value per identifier at a timestamp, so zero-delay waveforms do not expose all intermediate simulator updates or physical hazards. The parser can retain multiple events if a file contains them, but synthetic parser capability does not create physical glitch evidence.

## Step 3.5  Define comparable measurement windows

The input register and output registers represent the same image at different times. Comparing one common sample index without accounting for pipeline delay could accidentally compare image A at the input with image B at the output.

We therefore define a separate frame-aligned window for each observation. Every window contains **450 known settled states and 449 neighboring image pairs**. The first state's value establishes the baseline; counts begin after it. Later-stage windows shift to preserve the same image pairs.

For the head-only core, canonical layer samples begin at 291,670 ps and end at 37,708,636 ps. Registered scores/classes shift two clocks later, from 458,338 ps to 37,875,304 ps. Each adjacent-state window spans 449 simulated periods. These staggered windows are not one shared physical interval for energy integration.

Independent review found an important bug: checking only sample endpoints could accept a short between-sample input pulse or a pulse during drain if the input returned to its expected value. Such pulses can create activity even though endpoint values look correct. The fix checks **every input-port change** against the exact falling-edge schedule and held-input drain. Preserved malformed traces are now rejected, and the verifier rechecked the correction.

## Step 3.6  Separate signal categories and avoid double counting

We classified every observed identifier by its role: learned layer outputs, forwarding copies, data registers, score-bank view, output logic, clock, control, and testbench bookkeeping. Whole-trace categories reconcile with the raw counter; a different report selects aligned logical observations.

For example, an unregistered `l1` bus can simply forward `l1_c`. Distinct VCD IDs make both visible, but summing them would count the same logical layer twice. The canonical learned-network metric uses only **`l1_c` through `l4_c`**.

| Layer | Settled changes | Changes per gate per image pair |
|---|---:|---:|
| First layer | 126,546 | 0.28183964 |
| Second layer | 144,016 | 0.32074833 |
| Third layer | 167,436 | 0.37290869 |
| Fourth layer | 190,171 | 0.42354343 |
| All learned layers | 628,169 | 0.34976002 |

The full trace has 1,036 unique identifiers and separately reports 10,897 unknown-involving bit changes, largely associated with startup. The aligned learned-layer windows contain known states and exclude startup. The input, score-bank, and class observations have their own counts and widths; they are not extra learned gates.

These categories describe RTL observations. They are not a complete physical register inventory or a device power breakdown. In particular, the packed score-bank view observes stored values without representing a second physical bank.

## Step 3.7  Match logical activity against NumPy exactly

Agreement on one grand total is insufficient: two incorrect signals could produce the same number of toggles. We compared actual settled values, each adjacent-image XOR mask identifying changed positions, and per-gate counts.

Across **14 observations and 450 images**, there were **zero discrepancies**. The canonical learned-layer total is the same **628,169 out of 1,796,000**, with 314,079 rises and 314,090 falls. Six images with tied class scores also preserve the lowest-index prediction rule.

Separate scalar-gate and waveform decoders independently checked the results. Tests include wrong states that preserve aggregate counts, bit-order errors, repeated images, known/unknown pulses, and provenance faults. One initial test incorrectly assumed repeated inputs necessarily create tied class scores; the fixture was corrected so repeated-input constancy and deliberate score ties are checked separately.

This establishes that the software logical-change measurement and matched settled RTL observation agree for this workload. It does not validate a power estimator, prove training benefit, or include real routing hazards.

## Step 3.8  Measure activity after FPGA mapping

Synthesis changes the circuit, so logical-gate counts are only one view. We performed a fresh **standalone head-only core mapping** explicitly targeting iCE40 UltraPlus and instrumented the unique net bits connected to top-level or cell ports. A net bit is counted once even if several names refer to it.

This mapping produced **2,912 LUT4s, 339 flip-flops, 123 carry cells, and 3,569 observed unique net bits**. It is a different top and mapping protocol from the historical routed UART board; these counts must not replace that board's implementation numbers.

The zero-delay mapped simulation passed all 450 score/class comparisons. Its whole-trace activity was:

| Driver category | Known bit flips |
|---|---:|
| LUT outputs | 569,566 |
| Flip-flop outputs | 51,053 |
| Carry outputs | 23,856 |
| Data inputs | 22,071 |
| Clock input | 914 |
| Control inputs | 3 |
| Total | 667,463 |

There were zero unknown-involving changes in this mapped trace; the mapped register initialization policy differs from the original RTL startup model. The complete-burst window contains 667,290 known flips.

These are **zero-delay mapped-net activity counts**, not physical glitches, power, or energy. They use a different signal population from the 4,000 learned outputs, so 667,463 versus 628,169 is not a measured increase or decrease of the same quantity. This step also makes no new placement, timing, or capacity claim.

## Step 3.9  Estimate glitches using routed delays

A gate can briefly change and change back while its inputs arrive at different times. Such temporary transitions are called **glitches**. To investigate them, we used the routed head-only UART board design with delays exported in **SDF**, the Standard Delay Format.

The script rerouted the archived inputs with SDF output and required a byte-identical configuration bitstream. It consistently renamed all 4,169 cells because Icarus could not parse the original escaped names. Both timed and zero-delay versions processed the first eight saved images at the real 104-cycle UART divider; all reply scores and classes matched NumPy, and the timed and untimed per-net settled-change counts agreed. This checks internal settled-change counts; it is not an archived comparison of every internal settled value on every clock. The exact state-by-state comparison in step 3.7 has a different scope.

For each net, the experiment counts timed transitions and compares values sampled just before successive rising edges. **Extra transitions equal timed transitions minus settled changes.** Clocks are excluded from that ratio because they can return to the same sampled phase while toggling normally between samples.

| Routed category | Nets | Timed transitions | Settled changes | Extra transitions |
|---|---:|---:|---:|---:|
| Core including scores and class selection | 3,252 | 32,580 | 12,178 | 20,402 |
| UART and adapter interface | 1,022 | 2,923,403 | 1,723,025 | 1,200,378 |
| Unclassified board-related logic | 41 | 529,032 | 528,932 | 100 |
| Global buffers and I/O | 6 | 1,364 | 1,364 | 0 |
| All non-clock nets | 4,321 | 3,486,379 | 2,265,499 | 1,220,880 |

The core ratio is **20,402 / 12,178 = 1.675 extra transitions per settled change**. Equivalently, about 2.675 timed transitions occur per settled change on these nets and this workload. About 63 percent of those timed transitions are extra. This is not a correction factor for the different circuits and workloads in steps 3.7 or 3.8.

A teaching example is XOR between a signal and a delayed copy of itself. Once settled, both copies match and XOR is zero. During a change, one arrives first and briefly makes XOR one before it returns to zero: two extra transitions without any settled change.

The result has important limits. Icarus uses **inertial filtering**, which removes sufficiently narrow pulses, so the count is model-dependent. Only one delay corner and eight images were used; this is not electrical measurement or a strict bound on real silicon. Icarus does not support the SDF setup/hold timing checks here, so this activity simulation is not a complete timing signoff. The “core” category includes score and class-selection logic, not just learned gates. Four name-classified nets may belong with the adapter; reclassification would change the core ratio to about 1.81 without changing raw events.

Bitstream evidence exists in this experiment, but **no FPGA board has been programmed or electrically measured**. Independent review checked applied delays and recomputed counts. The result tells us glitches deserve attention; it does not show lower energy or demonstrate that the penalty reduces them.

## Step 3.10  Compare complementary switching metrics

We finally put the different measurements alongside each other with explicit populations, workloads, and denominators. This prevents a large raw count from being mistaken for worse efficiency merely because it includes more signals or more idle cycles.

The planned training surrogate uses `2p(1-p)`, where `p` is a gate's probability of outputting one. If consecutive inputs are independent, a gate changes on `0 -> 1` or `1 -> 0`, whose probabilities add to that expression. A gate with `p = 0.5` has surrogate 0.5; a gate always zero or always one has surrogate zero.

For the saved hard-output data, the mean surrogate is **0.34656**, the exact random-permutation expectation is **0.34733**, and measured saved-order switching is **0.34976**. For a fixed set of `n` images with `m` ones, random permutation gives `2m(n-m)/(n(n-1))`, equal to `2p(1-p) * n/(n-1)`.

The gap between surrogate and saved-order rate is about 0.00320. About 24 percent is the finite-sample factor; about 76 percent is this ordering's deviation, within the shuffle spread. The saved order is about 0.74 shuffle standard deviations above expectation overall. These are not independent confirmations of the surrogate: near-random ordering makes this relationship hold almost by construction.

Switching rises across layers from approximately 0.28 to 0.42. **499 of 4,000 gates**, or about 12.5 percent, never switch on these 450 inputs: 220, 177, 99, and 3 by layer. “Never on these inputs” does not prove they are constant for every possible image.

Input order can materially change switching without changing the model. A separate saved diagnostic grouped images by label and reduced the logical rate to about 0.23872. That is an ordering demonstration, not a learned optimization or proposed real workload. A correlated video stream can differ substantially from shuffled static images.

For a tiny example, `0, 1, 0, 1` and `0, 0, 1, 1` both have two ones and therefore the same `p = 0.5` and surrogate 0.5. The first sequence changes on all three neighboring pairs, while the second changes on only one of three. The surrogate cannot distinguish those orders because it sees their shared proportion of ones, not the arrangement.

The surrogate describes settled logical gate outputs and omits mapped capacitance, clocks, registers, and hazards. Moreover, this retrospective comparison uses **hard outputs on test images**, whereas training uses **soft outputs on training batches**. Their agreement here does not establish that optimizing the soft penalty will improve mapped activity or energy. That is the next experimental question.

# At the boundary of section 4

## What is already implemented but not yet experimentally established

The code supports `classification loss + lambda * mean[2p(1-p)]`. Here `p` is the **batch mean for each gate**, followed by averaging the activity terms across gates. Lambda controls the pressure toward lower surrogate switching. Lambda zero is the unpenalized control.

The distinction between batch and sample matters. Suppose a gate outputs hard zero on half the images and hard one on the other half. Per-sample `2a(1-a)` is always zero, even though the gate may switch frequently between images. Using the batch mean gives `p = 0.5` and activity surrogate 0.5. The per-sample option mainly encourages decisive soft outputs and remains an ablation, not the intended activity objective.

One-epoch smoke checks exercised the corrected training and penalty code path. They do not demonstrate a useful model, reliable accuracy improvement, reduced switching, or reduced energy. Preserving the old lambda-zero run is completed step 4.2; meaningful matched penalty experiments are still pending.

## Brief plan for the remaining work

**First, prepare fair selection in 4.10.** Allow sweeps to skip test evaluation, save ordered validation inputs and hard switching alongside accuracy, define selection criteria, and archive exact configurations, partitions, and checkpoints. Routine parser and validator cleanup is recorded as preparation, not a research result.

**Then run matched training in 4.3 through 4.5.** Train a fresh zero-penalty control and penalized versions on identical splits, architecture, training budget, and matched seeds. Sweep lambda using validation data, then repeat selected settings across seeds. Report failures and accuracy costs as well as improvements.

**Verify and implement selected models in 4.6 through 4.8.** Every selected model gets its own NumPy score/class reference and RTL checks. Hold FPGA target, head architecture, clock, ordered inputs, and workload fixed for comparisons. Measure resource cost, timing, settled switching, mapped activity, and relevant timed activity. Plot accuracy versus switching first; only add energy axes when energy evidence exists.

**Keep optional questions separate.** Step 4.9 compares the per-sample ablation. Step 4.11 investigates Gray coding after identifying useful signals. Pixel recoding requires retraining and fair controls for bit width and quantization; counter or score recoding requires exact-function and area/timing/activity checks. Gray coding is not automatically beneficial and is different from grayscale imagery.

**Establish power and energy in section 5.** Select a supported device-specific power-analysis flow or electrical measurement setup. Report static and dynamic power separately, state activity coverage and operating conditions, and calculate energy using completed predictions in the same measured workload interval. Vivado on an AMD FPGA would be a separate target experiment, not power evidence for this iCE40 implementation.

**Deploy in section 6 when hardware is ready.** Confirm board revision and connection, build the host client, program a validated bitstream, and compare actual board scores/classes with Python. Electrical measurements must specify whether they cover an FPGA rail or the entire board. A slow UART demo and a fully utilized streaming core need distinct workload reporting.

**Prepare deliverables in section 7.** Consolidate experiment tables and preserve raw artifacts; generated `runs/` files are currently gitignored. Expand to MNIST only after the controlled baseline is sound; loading support exists, but no saved MNIST benchmark is established. Write the report and slides alongside experiments, and obtain Professor Eshraghian's review of a concrete manuscript before submission. The recorded course deadline is December 4, 2026; venue deadlines require separate confirmation.

## What the research can and cannot claim today

| Question | Current evidence |
|---|---|
| Does the toy model recognize digits? | Historical hard accuracy is 93.56 percent on the saved test set |
| Does RTL match the hard software model? | Yes for tested vectors, including all scores and tie behavior |
| Is there a feasible implementation on the selected FPGA? | Head-only candidate routes and meets 12 MHz in the tools |
| Does the full pipeline fit? | No; current candidate needs 6,575 of 5,280 cells |
| Can we measure logical and simulated mapped activity? | Yes, with independently reviewed counts and provenance |
| Do timing-model glitches matter in the baseline? | They are substantial on the eight-image routed-board experiment |
| Has the penalty reduced switching across matched trained models? | Not yet tested |
| Has lower power or energy been demonstrated? | No |
| Is the idea established as novel? | No; literature differentiation and actual comparative results remain necessary |

The supported research question is whether gate-rule learning with a switching surrogate can improve **mapped or measured energy at comparable accuracy**. The present work is a carefully checked foundation for that experiment. Fewer unweighted logical transitions alone would remain a useful intermediate result, not proof of lower joules per prediction.

# Evidence and practical reference

## Where to find the project material

Paths below are relative to the project repository. They remain meaningful after downloading this guide, although the source files themselves require the repository. Some older summary paragraphs predate steps 3.8 through 3.10; the specific numbered results and final review verdicts provide the relevant detailed scope.

- `docs/PROJECT_CHECKLIST.md` gives numbered status and pending work.
- `docs/PROJECT_CONTEXT.md` gives project background, goals, historical results, and decisions.
- `docs/steps/README.md` indexes the individual learning notes.
- `docs/steps/1.1-prepare-the-digits-data.md` through `1.11-run-the-regression-tests.md` cover dataset, model, export, and exact verification.
- `docs/steps/2.1-synthesize-the-original-core.md` through `2.10-compare-latency-and-throughput.md` cover hardware resources, tools, interface, implementation, and performance.
- `docs/steps/3.1-measure-python-switching.md` through `3.10-report-complementary-switching-metrics.md` define the activity measurements and their limitations.
- `docs/UART_INTERFACE.md` specifies packets, pin assignments, divider, recovery behavior, and interface limits.
- `docs/reviews/step-2.8-independent-review.md`, `step-2.9-independent-review.md`, and `step-2.10-independent-review.md` record implementation and performance review.
- `docs/reviews/step-3.2-independent-review.md` through `step-3.10-independent-review.md` record the measurement reviews, findings, and correction rechecks.
- `docs/results/` contains tracked JSON summaries and fingerprints for steps 2.8 onward.
- `dlgn/data.py`, `gates.py`, `model.py`, and `hard.py` implement encoding, gate rules, training model, and golden reference.
- `dlgn/export_verilog.py`, `dlgn/uart_export.py`, `rtl/`, `scripts/`, `sim/`, and `synth/` contain export, interface, measurement, simulation, and FPGA-flow code.

The raw primary routed implementation is `runs/digits_w1000/uart_comb_head/implementation.UVAx2g/`; the independent route is `implementation.ogVBqL/`. The full baseline capture is `runs/digits_w1000/baseline-waveform.xs90rtvt/`, with independent capture `baseline-waveform.q2umneq1/`. Mapped evidence is under `runs/digits_w1000/mapped-activity.57fn0ze0/`; routed timed evidence is under `runs/step3.9-glitch/timed-activity.0hvnej44/`.

These generated directories are gitignored. A fresh clone needs separately archived artifacts or reproduced runs to recheck their hashes. Tracked summaries preserve reported results but do not replace every raw file needed for full reproduction.

## Commands for inspection and reproduction

The commands below are reference instructions, not new runs performed for this guide. Run them from the repository root with the required environment and local artifacts. Simulation and implementation can generate fresh outputs; preserve earlier evidence and read the individual step note before a long run.

Check the regression suite:

```bash
.venv/bin/python -m pytest tests -q
```

Inspect the historical core simulation:

```bash
bash sim/run_sim.sh runs/digits_w1000/rtl_comb
bash sim/run_sim.sh runs/digits_w1000/rtl_pipe
```

Revalidate the saved feasible timing archive, writing a separate temporary summary:

```bash
.venv/bin/python scripts/report_timing.py \
  runs/digits_w1000/uart_comb_head/implementation.UVAx2g \
  --out /tmp/h02-timing-check.json
```

Create a fresh complete standalone baseline capture:

```bash
.venv/bin/python scripts/capture_baseline_waveform.py runs/digits_w1000 \
  --export runs/digits_w1000/uart_comb_head \
  --implementation runs/digits_w1000/uart_comb_head/implementation.UVAx2g
```

Reanalyze the existing mapped capture:

```bash
.venv/bin/python scripts/capture_mapped_activity.py analyze \
  runs/digits_w1000/mapped-activity.57fn0ze0
```

Reproduce the eight-image timed experiment, which takes roughly five minutes in the recorded environment:

```bash
.venv/bin/python scripts/capture_timed_activity.py --n 8
```

Regenerate the complementary metrics into a temporary file:

```bash
.venv/bin/python scripts/report_switching_metrics.py \
  --out /tmp/h02-switching-metrics-check.json
```

Do not rerun a training command into `runs/digits_w1000`. That directory is the preserved historical baseline, and today's trainer uses a different validation protocol. New experiments need their own output directories and matched controls.
