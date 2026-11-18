# PathSnap — Logistic Regression Results

PathSnap’s Logistic Regression model uses six GPS and road-network features to score candidate road segments and select a match for each GPS observation. Features are standardized before fitting the classifier.

The completed model achieved **80.97% Top-1 reference agreement** across **19,160 held-out test observations**.

## Results at a Glance

| Measure | Result |
|---|---:|
| Test trips | 10 |
| Test observations | 19,160 |
| Correctly matched observations | **15,513** |
| Test Top-1 reference agreement | **80.97%** |
| Top-1 agreement on covered observations | **81.17%** |
| Test reference candidate coverage | **99.75%** |
| Candidate classification accuracy | **93.10%** |
| Candidate Macro F1 | **86.35%** |
| Recorded test inference time | **0.00631 s** |

Top-1 reference agreement measures whether the model’s highest-scoring candidate matches the geometric weak reference road segment derived from the supplied route.

The overall score includes every test observation. The covered-observation score considers observations whose reference road segment appears among the generated candidates.

## Dataset Used

| Split | Trips | GPS observations | Candidate road segments | Reference-positive candidates |
|---|---:|---:|---:|---:|
| Training | 80 | 208,417 | 1,241,756 | 185,349 |
| Held-out test | 10 | 19,160 | 125,525 | 19,112 |
| **Total** | **90** | **227,577** | **1,367,281** | **204,461** |

A candidate is a possible road segment for one GPS observation. Logistic Regression assigns a positive-class probability to each candidate, and the highest-scoring candidate becomes the selected match.

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
| Top-1 reference agreement | **80.97%** |
| Top-1 agreement on covered observations | **81.17%** |
| Candidate classification accuracy | **93.10%** |
| Precision | **78.81%** |
| Recall | **74.80%** |
| F1 score | **76.75%** |
| Macro F1 | **86.35%** |
| Log loss | **0.1800** |
| Mean trip Top-1 agreement | **82.47%** |
| Exact sequence accuracy | **0.00%** |

### What These Metrics Mean

| Metric | Explanation |
|---|---|
| Top-1 reference agreement | How often the selected road segment agrees with the reference at an observation |
| Candidate classification accuracy | How often individual candidates are classified correctly |
| Precision | Share of predicted positive candidates that agree with the reference |
| Recall | Share of reference-positive candidates identified by the classifier |
| F1 score | Combined measure of precision and recall |
| Macro F1 | Equal-weight average of the F1 scores for both candidate classes |
| Log loss | Measures how well predicted candidate probabilities align with their labels |
| Mean trip Top-1 agreement | Average of each test trip’s observation-level Top-1 agreement |
| Exact sequence accuracy | Share of trips for which every observation is matched correctly |

Top-1 evaluates the final road selection for each observation. Candidate classification metrics evaluate individual candidates using a probability threshold of 0.5.

## Five-Fold Cross-Validation

The training evaluation uses the shared dataset’s five fixed trip-based folds. A `StandardScaler` is fitted separately on each fold’s training partition, without using validation data.

| Fold | Candidate accuracy | Precision | Recall | F1 | Macro F1 | Top-1 |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 92.59% | 72.49% | 68.04% | 70.19% | 82.98% | 44.87% |
| 2 | 91.44% | 75.32% | 66.96% | 70.90% | 82.94% | 74.86% |
| 3 | 90.37% | 75.66% | 68.03% | 71.64% | 82.92% | 75.81% |
| 4 | 93.85% | 76.51% | 78.00% | 77.25% | 86.85% | 77.68% |
| 5 | 92.93% | 79.36% | 70.64% | 74.75% | 85.32% | 77.16% |
| **Mean** | **92.23%** | **75.87%** | **70.33%** | **72.95%** | **84.20%** | **70.07%** |

Each fold assesses a separate group of validation trips. The mean gives each fold equal weight.

### Cross-Validation Summary

| Metric | Mean | Standard deviation |
|---|---:|---:|
| Candidate accuracy | 92.23% | 1.35 percentage points |
| Precision | 75.87% | 2.47 percentage points |
| Recall | 70.33% | 4.49 percentage points |
| F1 | 72.95% | 2.97 percentage points |
| Macro F1 | 84.20% | 1.80 percentage points |
| Top-1 reference agreement | 70.07% | 14.14 percentage points |
| Top-1 agreement on covered observations | 78.74% | 4.31 percentage points |
| Log loss | 0.1933 | 0.0242 |

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
| Other candidate | 102,569 | 3,844 |
| Reference candidate | 4,816 | 14,296 |

These counts describe binary classification across all **125,525 test candidates**. Final Top-1 selection chooses one candidate per GPS observation.

## Runtime

| Operation | Recorded time |
|---|---:|
| Mean training time per cross-validation fold | 1.9705 s |
| Mean inference time per cross-validation fold | 0.0194 s |
| Final model training | **2.08508 s** |
| Held-out test inference | **0.00631 s** |

The final inference measurement covers probability scoring of prepared test candidates. Raw GPS preparation, feature scaling, candidate generation, and Top-1 selection are separate stages.

## Processing Flow

| Stage | What happens |
|---|---|
| Shared input loading | The notebook loads the prepared six-feature dataset and fixed folds |
| Feature scaling | `StandardScaler` standardizes the features using training data only |
| Candidate scoring | Logistic Regression assigns a positive-class probability to each candidate road segment |
| Road selection | The highest-scoring candidate is selected for each observation; ties use distance rank and arc ID |
| Evaluation | Selected roads are compared with geometric weak reference labels |
| Visualization | A sample GPS trip is plotted; road layers require the original network files |

The final classifier uses `LogisticRegression(solver="lbfgs", C=1.0, max_iter=1000, class_weight=None, random_state=42)`.

Route continuity is not reported because the shared feature archive lacks road-network endpoint data. The notebook does not record a model-results export directory.

*Source: recorded outputs in `Logistic_Regression.ipynb`. Percentages are rounded to two decimal places. Dataset observation and coverage counts follow the shared six-feature dataset totals supplied with the reference format; the notebook directly confirms trip counts, candidate counts, classification results, and evaluation scores.*
