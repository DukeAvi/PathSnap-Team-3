# PathSnap — Trained Model Results

PathSnap combines XGBoost with HMM-style Viterbi decoding to match GPS observations to a directed road network. XGBoost scores the candidate road segments, and Viterbi uses movement and network connectivity to select a consistent sequence.

The completed model achieved **87.84% reference agreement** across **19,160 test observations**, with **99.94% route continuity**.

## Results at a Glance

| Measure | Result |
|---|---:|
| Test observations | 19,160 |
| Correctly matched observations | 16,830 |
| Test reference agreement | **87.84%** |
| Mean accuracy across test trips | **89.82%** |
| Route continuity | **99.94%** |
| Test observations receiving a match | **100%** |
| Test reference candidate coverage | **99.75%** |
| Recorded prediction time | **171.39 ms** |
| Project target range | 85–95% |
| Target achieved | **Yes** |

Reference agreement measures whether the selected road segment matches the geometric weak reference label derived from the supplied route. Every test observation contributes to this score.

Mean trip accuracy gives each trip equal weight. Overall reference agreement gives each observation equal weight.

## What the HMM/Viterbi Stage Adds

| Measure | XGBoost | XGBoost + HMM/Viterbi | Improvement |
|---|---:|---:|---:|
| Test reference agreement | 83.01% | **87.84%** | **4.83 percentage points** |
| Mean trip accuracy | 84.44% | **89.82%** | **5.39 percentage points** |
| Route continuity | 94.83% | **99.94%** | **5.11 percentage points** |
| Correct test observations | 15,904 | **16,830** | **926 additional matches** |

XGBoost evaluates the candidate roads around each GPS observation. The HMM/Viterbi stage adds the surrounding movement context: how the vehicle moves between observations and which transitions are feasible through the directed road network.

Together, these stages improve both reference agreement and route continuity.

## Dataset Used

| Split | Trips | GPS observations | Candidate road segments |
|---|---:|---:|---:|
| Training | 80 | 208,417 | 1,241,756 |
| Held-out test | 10 | 19,160 | 125,525 |
| **Total** | **90** | **227,577** | **1,367,281** |

A candidate is a possible road segment for one GPS observation. Each observation can have several candidates, which the model scores before sequence decoding.

Test reference candidate coverage was **99.75%**, meaning the reference road segment was included among the generated candidates for that proportion of test observations.

## Results for Each Test Trip

| Trip ID | Observations | Correct matches | Reference agreement |
|---|---:|---:|---:|
| 00000000 | 2,503 | 2,402 | 95.96% |
| 00000007 | 1,354 | 1,197 | 88.40% |
| 00000009 | 1,049 | 951 | 90.66% |
| 00000040 | 2,995 | 2,826 | 94.36% |
| 00000052 | 262 | 259 | 98.85% |
| 00000056 | 3,958 | 3,377 | 85.32% |
| 00000065 | 768 | 654 | 85.16% |
| 00000076 | 1,486 | 1,362 | 91.66% |
| 00000077 | 3,911 | 3,007 | 76.89% |
| 00000091 | 874 | 795 | 90.96% |
| **Overall** | **19,160** | **16,830** | **87.84%** |

The arithmetic mean of the ten trip scores is **89.82%**.

## How the Model Works

| Stage | What happens |
|---|---|
| GPS preparation | Observations are ordered by time and prepared for feature calculation. |
| Candidate generation | Nearby directed road segments become possible matches. |
| Feature extraction | Each candidate receives 18 GPS and road-network features. |
| Scaling | The saved StandardScaler transforms the features using its fitted training statistics. |
| XGBoost scoring | The trained classifier assigns a positive-class score to each candidate. |
| Network transitions | Directed road distances and observed movement determine transition scores. |
| Viterbi decoding | The decoder selects the highest-scoring candidate sequence under the model. |

### The 18 Input Features

| Feature group | Features |
|---|---|
| Distance and ranking | GPS-to-road distance, distance rank, distance above the nearest candidate |
| Direction | Heading difference, heading validity |
| Position on the road | Projection fraction, distance to start node, distance to end node |
| Road geometry | Segment length |
| Movement | Displacement, time gap, speed, acceleration |
| Network structure | Start-node outgoing degree, end-node incoming degree, start-node incoming degree, end-node outgoing degree |
| Candidate context | Candidate count |

These features describe where the GPS point lies, how it is moving, and how each candidate connects to the road network.

## Training and Parameter Selection

| Setting | Value |
|---|---|
| Training trips | 80 |
| Cross-validation | Five fixed trip-based folds |
| Decoder optimisation | Seeded Optuna Bayesian search |
| Decoder trials | 80 |
| Decoder selection score | 79.72% |
| XGBoost trees | 200 |
| Learning rate | 0.05 |
| Maximum tree depth | 6 |
| Minimum child weight | 10 |
| L2 regularisation | 1.0 |
| Execution device | CPU |
| XGBoost worker threads | 4 |
| Random seed | 42 |

The decoder selection score is the mean pointwise agreement across the five training folds using out-of-fold emission scores.

The exported run uses the configured XGBoost settings and applies Bayesian optimisation to the decoder parameters. Model settings were frozen before the held-out test evaluation.

### Selected Decoder Settings

| Parameter | Selected value | Role |
|---|---:|---|
| Base transition scale | 10.0441 m | Sets the base tolerance for differences between road distance and observed displacement |
| Displacement scale factor | 0.09169 | Adjusts transition tolerance with movement distance |
| Transition speed allowance | 23.2005 m/s | Defines the speed component of transition feasibility |
| Transition distance allowance | 126.7208 m | Adds distance flexibility to the transition rule |
| Maximum observation gap | 30 s | Defines the gap threshold for sequence continuation |
| Jitter tolerance | 15 m | Accommodates small positional fluctuations |
| Directed graph search limit | 3,000 m | Bounds road-network distance searches |

## XGBoost Candidate Classification

The emission classifier also records how well it distinguishes reference candidates from other candidates.

| Metric | Test result |
|---|---:|
| Candidate classification accuracy | 94.62% |
| Precision | 82.98% |
| Recall | 81.35% |
| F1 score | 82.16% |
| Macro F1 | 89.50% |
| Log loss | 0.1294 |

These metrics describe candidate scoring. The final sequence is assessed using observation-level reference agreement and route continuity.

## Runtime

| Operation | Recorded time |
|---|---:|
| Final XGBoost fit | 9.68 s |
| Training graph and lattice preparation | 101.86 s |
| Test graph and lattice preparation | 9.66 s |
| Test scaling and XGBoost scoring | 148.28 ms |
| Test Viterbi decoding | 23.12 ms |
| **Combined test scoring and decoding** | **171.39 ms** |
| Complete recorded training and evaluation run | 265.73 s |

The **171.39 ms** measurement covers scoring and decoding for all **19,160 test observations** using prepared features and geometry. Feature preparation and graph construction are separate stages.

The complete recorded run took approximately **4 minutes 26 seconds**, excluding dependency installation.

## Understanding Route Continuity

Route continuity measures whether consecutive selected road segments can be connected through a feasible directed road path.

| Evaluation component | Definition |
|---|---|
| Observation pairs assessed | 19,150 |
| Time-gap rule | Greater than 0 and at most 30 seconds |
| Directed-distance rule | At most `80 × time_gap + 150` metres |
| Jitter tolerance | 15 metres |
| Final continuity score | **99.94%** |

This fixed evaluation rule provides a consistent comparison between XGBoost and the combined pipeline. The decoder uses its separately selected transition parameters when choosing the sequence.

## What the Export Contains

| Component | Included files |
|---|---|
| Trained emission model | `selected18_xgboost_model.ubj` |
| Fitted feature scaler | `selected18_scaler.joblib` |
| Model configuration | `selected18_model_config.json` |
| Frozen decoder settings | `decoder_config.json` |
| Feature documentation | `feature_schema_18.csv`, `shared_protocol.json` |
| Inference and decoding source | `predict.py`, `fast_decoder.py`, supporting modules |
| Recorded results | Overall metrics, per-trip metrics, fold results, model comparison |
| Reproduction inputs | Prepared test candidates, observations, matching geometry caches |
| Executed results notebook | `PathSnap_HMM_Results.ipynb` |
| File verification | `SHA256SUMS.json` |

*Source: the result tables, configuration files, and recorded metrics in `PathSnap_HMM_Trained.zip`. Percentages are rounded to two decimal places.*
