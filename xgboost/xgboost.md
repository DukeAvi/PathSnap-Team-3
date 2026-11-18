# PathSnap — XGBoost Results

PathSnap’s XGBoost model uses six GPS and road-network features to score candidate road segments and select a match for each GPS observation.

The completed model achieved **82.50% Top-1 reference agreement** across **19,160 held-out test observations**, with a recorded inference time of **476.32 ms**.

## Results at a Glance

| Measure | Result |
|---|---:|
| Test trips | 10 |
| Test observations | 19,160 |
| Correctly matched observations | **15,807** |
| Test Top-1 reference agreement | **82.50%** |
| Test reference candidate coverage | **99.75%** |
| Candidate classification accuracy | **94.30%** |
| Precision | **82.08%** |
| Recall | **80.07%** |
| F1 score | **81.06%** |
| Recorded test inference time | **476.32 ms** |

Top-1 reference agreement measures whether the highest-scoring candidate road segment agrees with the geometric weak reference label derived from the supplied route. Every test observation contributes to this score.

## Dataset Used

| Split | Trips | GPS observations | Candidate road segments |
|---|---:|---:|---:|
| Training | 80 | 208,417 | 1,241,756 |
| Held-out test | 10 | 19,160 | 125,525 |
| **Total** | **90** | **227,577** | **1,367,281** |

A candidate is a possible road segment for one GPS observation. XGBoost evaluates the candidates using their feature values and selects the highest-scoring segment for each observation.

## The Six Input Features

| Feature | Meaning | What it contributes |
|---|---|---|
| `distance_m` | Projected distance from the GPS point to the road segment | Measures spatial compatibility |
| `distance_rank` | Candidate’s position when ordered by distance | Expresses relative proximity |
| `heading_difference_deg` | Difference between movement heading and road direction | Adds directional context |
| `projection_fraction` | Position of the projected GPS point along the segment | Describes where the observation falls on the road |
| `segment_length_m` | Length of the directed road segment | Adds road geometry context |
| `displacement_m` | Distance moved since the previous retained GPS observation | Describes movement between observations |

Together, these features describe location, direction, road geometry, and movement.

## Held-Out Test Performance

| Metric | Result |
|---|---:|
| Top-1 reference agreement | **82.50%** |
| Candidate classification accuracy | **94.30%** |
| Precision | **82.08%** |
| Recall | **80.07%** |
| F1 score | **81.06%** |
| Log loss | **0.1370** |

### What These Metrics Mean

| Metric | Explanation |
|---|---|
| Top-1 reference agreement | How often the selected road segment agrees with the reference at an observation |
| Candidate classification accuracy | How often individual candidates are classified correctly |
| Precision | Share of predicted positive candidates that agree with the reference |
| Recall | Share of reference-positive candidates identified by the classifier |
| F1 score | Combined measure of precision and recall |
| Log loss | Measures how well candidate probabilities align with their labels |

Top-1 evaluates the selected road for each observation. Candidate classification metrics evaluate the individual candidate predictions.

## Five-Fold Cross-Validation

The training evaluation uses the shared dataset’s five fixed trip-based folds.

| Fold | Candidate accuracy | Precision | Recall | F1 | Top-1 |
|---|---:|---:|---:|---:|---:|
| 1 | 93.52% | 75.47% | 73.32% | 74.38% | 45.30% |
| 2 | 92.53% | 76.80% | 74.53% | 75.65% | 76.19% |
| 3 | 91.56% | 77.42% | 74.54% | 75.95% | 76.84% |
| 4 | 95.49% | 83.62% | 82.53% | 83.07% | 78.81% |
| 5 | 93.84% | 80.89% | 76.47% | 78.62% | 78.49% |
| **Mean** | **93.39%** | **78.84%** | **76.28%** | **77.53%** | **71.13%** |

Each fold evaluates a separate group of validation trips. The mean gives each fold equal weight.

### Cross-Validation Summary

| Metric | Mean | Standard deviation |
|---|---:|---:|
| Candidate accuracy | 93.39% | 1.48 percentage points |
| Precision | 78.84% | 3.34 percentage points |
| Recall | 76.28% | 3.67 percentage points |
| F1 | 77.53% | 3.46 percentage points |
| Top-1 reference agreement | 71.13% | 14.48 percentage points |
| Log loss | 0.1543 | 0.0273 |

## Candidate Coverage

| Measure | Training | Held-out test |
|---|---:|---:|
| GPS observations | 208,417 | 19,160 |
| Observations with the reference among candidates | 185,349 | 19,112 |
| Reference candidate coverage | 88.93% | **99.75%** |

Candidate coverage describes how often the reference road segment appears among the candidates available to the model.

On the held-out test set, **19,112 of 19,160 observations** included the reference road segment among their candidates.

## Test Candidate Classification Counts

| Reference class | Predicted other candidate | Predicted reference candidate |
|---|---:|---:|
| Other candidate | 103,073 | 3,340 |
| Reference candidate | 3,809 | 15,303 |

These counts describe binary classification across all **125,525 test candidates**. Top-1 selection then chooses the highest-scoring candidate for each GPS observation.

## Runtime

| Operation | Recorded time |
|---|---:|
| Mean training time per cross-validation fold | 18.69 s |
| Mean inference time per cross-validation fold | 1.12 s |
| Final model training | **24.01 s** |
| Held-out test inference | **476.32 ms** |

The final inference measurement covers scoring the prepared test candidates. Raw GPS preparation and candidate generation are separate stages.

## Processing Flow

| Stage | What happens |
|---|---|
| Shared input loading | The notebook loads the prepared six-feature dataset and fixed folds |
| Feature scaling | The fitted scaler transforms the model inputs |
| Candidate scoring | XGBoost assigns a score to each candidate road segment |
| Road selection | The highest-scoring candidate is selected for each observation |
| Evaluation | Selected roads are compared with geometric reference labels |
| Results export | The notebook saves the model and evaluation outputs |

The notebook records its output directory as:

`/content/drive/MyDrive/output/XGBoost_shared6`

*Source: recorded outputs in `PathSnap_XGBoost_Review1_run.ipynb`. Percentages are rounded to two decimal places.*
