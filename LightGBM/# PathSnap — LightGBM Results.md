# PathSnap — LightGBM Results

PathSnap’s LightGBM model uses six GPS and road-network features to score candidate road segments and select a match for each GPS observation.

The completed model achieved **82.44% Top-1 reference agreement** across **19,160 held-out test observations**.

## Results at a Glance

| Measure | Result |
|---|---:|
| Test trips | 10 |
| Test observations | 19,160 |
| Correctly matched observations | **15,796** |
| Test Top-1 reference agreement | **82.44%** |
| Top-1 agreement on covered observations | **82.65%** |
| Test reference candidate coverage | **99.75%** |
| Observations with at least one candidate | **100%** |
| Candidate classification accuracy | **94.28%** |
| Candidate Macro F1 | **88.84%** |
| Recorded test inference time | **1.05 s** |

Top-1 reference agreement measures whether the model’s highest-scoring candidate matches the geometric weak reference road segment derived from the supplied route.

The overall score includes every test observation. The covered-observation score considers observations whose reference road segment appears among the generated candidates.

## Dataset Used

| Split | Trips | GPS observations | Candidate road segments | Reference-positive candidates |
|---|---:|---:|---:|---:|
| Training | 80 | 208,417 | 1,241,756 | 185,349 |
| Held-out test | 10 | 19,160 | 125,525 | 19,112 |
| **Total** | **90** | **227,577** | **1,367,281** | **204,461** |

A candidate is a possible road segment for one GPS observation. LightGBM scores these candidates, and the highest-scoring candidate becomes the selected match.

A reference-positive candidate is a candidate road segment that agrees with the supplied geometric reference label.

## The Six Input Features

| Feature | Meaning | What it contributes |
|---|---|---|
| `distance_m` | Projected distance from the GPS point to the road segment | Measures spatial compatibility |
| `distance_rank` | Candidate’s position when ordered by distance | Expresses relative proximity |
| `heading_difference_deg` | Difference between movement heading and road direction | Adds directional context |
| `projection_fraction` | Position of the projected GPS point along the segment | Describes where the observation falls on the road |
| `segment_length_m` | Length of the directed road segment | Adds road geometry context |
| `displacement_m` | Distance moved since the previous retained GPS observation | Describes movement between observations |

The model combines location, direction, road geometry, and recent movement when evaluating each candidate.

## Held-Out Test Performance

| Metric | Result |
|---|---:|
| Top-1 reference agreement | **82.44%** |
| Top-1 agreement on covered observations | **82.65%** |
| Candidate classification accuracy | **94.28%** |
| Precision | **81.83%** |
| Recall | **80.28%** |
| F1 score | **81.05%** |
| Macro F1 | **88.84%** |
| Log loss | **0.1375** |

### What These Metrics Mean

| Metric | Explanation |
|---|---|
| Top-1 reference agreement | How often the selected road segment agrees with the reference at an observation |
| Candidate classification accuracy | How often individual candidates are classified correctly |
| Precision | Share of predicted positive candidates that agree with the reference |
| Recall | Share of reference-positive candidates identified by the classifier |
| F1 score | Combined measure of precision and recall |
| Macro F1 | Equal-weight average of the F1 scores for both candidate classes |
| Log loss | Measures how well the predicted candidate probabilities align with their labels |

Top-1 evaluates the final road selection for each observation. Candidate classification metrics evaluate the individual candidate scores.

## Five-Fold Cross-Validation

The training evaluation uses the shared dataset’s five fixed trip-based folds.

| Fold | Candidate accuracy | Precision | Recall | F1 | Macro F1 | Top-1 |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 93.52% | 75.39% | 73.48% | 74.42% | 85.36% | 45.31% |
| 2 | 92.55% | 76.87% | 74.64% | 75.74% | 85.67% | 76.28% |
| 3 | 91.56% | 77.48% | 74.42% | 75.92% | 85.40% | 76.93% |
| 4 | 95.58% | 84.23% | 82.41% | 83.31% | 90.38% | 78.72% |
| 5 | 93.81% | 80.69% | 76.45% | 78.51% | 87.45% | 78.27% |
| **Mean** | **93.40%** | **78.93%** | **76.28%** | **77.58%** | **86.85%** | **71.10%** |

Each fold assesses a separate group of validation trips. The mean gives each fold equal weight.

### Cross-Validation Summary

| Metric | Mean | Standard deviation |
|---|---:|---:|
| Candidate accuracy | 93.40% | 1.50 percentage points |
| Precision | 78.93% | 3.54 percentage points |
| Recall | 76.28% | 3.59 percentage points |
| F1 | 77.58% | 3.53 percentage points |
| Macro F1 | 86.85% | 2.15 percentage points |
| Top-1 reference agreement | 71.10% | 14.45 percentage points |
| Top-1 agreement on covered observations | 79.87% | 4.33 percentage points |
| Log loss | 0.1543 | 0.0273 |

## Candidate Coverage

| Measure | Training | Held-out test |
|---|---:|---:|
| Observations | 208,417 | 19,160 |
| Observations with the reference among candidates | 185,349 | 19,112 |
| Reference candidate coverage | 88.93% | **99.75%** |
| Observations with at least one candidate | 194,813 | **19,160** |

Candidate coverage describes the input available to the classifier. On the test set, every observation had at least one candidate, and **19,112 observations** included the reference road segment among their candidates.

## Test Candidate Classification Counts

| Reference class | Predicted other candidate | Predicted reference candidate |
|---|---:|---:|
| Other candidate | 103,007 | 3,406 |
| Reference candidate | 3,768 | 15,344 |

These counts describe binary classification across all **125,525 test candidates**. Final Top-1 selection chooses one candidate per GPS observation.

## Runtime

| Operation | Recorded time |
|---|---:|
| Mean training time per cross-validation fold | 19.65 s |
| Mean inference time per cross-validation fold | 2.60 s |
| Final model training | **23.65 s** |
| Held-out test inference | **1.05 s** |

The final inference measurement covers scoring the prepared test candidates. Raw GPS preparation and candidate generation are separate stages.

## Processing Flow

| Stage | What happens |
|---|---|
| Shared input loading | The notebook loads the prepared six-feature dataset and fixed folds |
| Candidate scoring | LightGBM assigns a score to each candidate road segment |
| Road selection | The highest-scoring candidate is selected for each observation |
| Evaluation | Selected roads are compared with geometric reference labels |
| Results export | Metrics and model outputs are saved to the configured output directory |

The notebook records its output directory as:

`/content/drive/MyDrive/output/LightGBM`

*Source: recorded outputs in `PathSnap_LightGBM_Shared6_run.ipynb`. Percentages are rounded to two decimal places.*
