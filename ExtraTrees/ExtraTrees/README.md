# PathSnap with Extra Trees

This notebook uses an Extra Trees classifier to match noisy GPS readings to nearby directed road segments. It scores the road candidates for each GPS point and selects the candidate with the highest match probability.

[Open the notebook](ExtraTrees_PathSnap_Shared6_Visuals.ipynb)

## Run in Google Colab

1. Open `ExtraTrees_PathSnap_Shared6_Visuals.ipynb` in Colab with a CPU runtime.
2. Place `PathSnap_shared6.zip` under **My Drive → PathSnap_ip** or directly under **My Drive**. If `PathSnap_ip` is under **Shared with me**, add a shortcut to it in **My Drive**. Alternatively, upload the ZIP to Colab's Files panel and set `USE_DRIVE = False` in Step 1.
3. Run the notebook from top to bottom. Steps 4 and 5 run validation and student testing. Step 6 displays metrics, confusion matrices, EDA plots, and a trip map. Step 7 downloads the results ZIP.

The notebook uses NumPy, pandas, scikit-learn, joblib, Matplotlib, and Folium. The saved Colab run used **scikit-learn 1.6.1**. The training archive and original road data are supplied separately.

## Dataset and model

The Shared6 archive contains prepared road candidates, estimated reference labels, and five fixed trip folds. For each GPS point, the preparation code retains up to eight directed road segments within 75 metres. The model uses these six inputs in order:

1. GPS-to-road distance
2. Candidate distance rank
3. Heading difference
4. Projection fraction along the candidate segment
5. Road segment length
6. GPS displacement since the preceding retained reading

The model has **48 randomized decision trees**, with maximum depth **16**, minimum leaf size **6**, square-root feature sampling, and random seed **42**. Each tree scores a candidate, and the ensemble averages those scores. A `StandardScaler` is fitted on the training rows for each fold and fitted again on the full training split for the final model.

Cross-validation holds out whole trips using the five supplied folds across **80 training trips**. The final model is fitted on all 80 trips and evaluated on **10 separate student-test trips**.

## Results from the saved notebook run

| Metric | Five-fold validation mean | Student test |
| --- | ---: | ---: |
| Observation-level Top-1 accuracy | 70.63% | **81.78%** |
| Candidate-level Macro F1 | 86.37% | 88.65% |
| Candidate-level log loss | 0.1648 | 0.1497 |

The model selected the reference road for **15,669 of 19,160** student-test GPS points. The nearest-road baseline scored **57.41%** on the same points. The reference road was absent from the candidate list for **48** points, which count as misses in Top-1. Top-1 measures agreement with the estimated point labels. Assessing whether the predicted segments form a continuous route requires a separate evaluation.

## Map and exported results

Step 6D uses **Esri World Imagery** for the satellite background. The GPS trace is available from the Shared6 data. Add the original `Student folder.zip` to Colab or set `RAW_DATA_ROOT` to the extracted Student folder for the reference and predicted road overlays. Set `SHOW_SATELLITE = False` to draw the dataset's streets as the background if the satellite tiles fail to load and the original data is available.

Step 7 downloads `pathsnap_extra_trees_shared6_results.zip`. It contains the fitted scaler and classifier pipeline, metrics CSVs, per-point predictions, fold assignments, run configuration, plots, and Folium map HTML.
