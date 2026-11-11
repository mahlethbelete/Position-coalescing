# Position coalescing

Reads repeated snapshots of professional profiles and assigns every job a stable `position_id`, so the same job keeps the same ID across snapshots. Deleted jobs are carried forward, edited jobs keep their ID, and no future snapshot is ever used to decide an earlier one.

My explanation of the design decisions, tradeoffs and results is in `docs/EXPLANATION.md`.

## Build

```
docker build --platform linux/amd64 -t position-coalescing .
```

Or load the submitted tarball instead of building:

```
docker load -i position-coalescing.tar
```

## Run

```
docker run --rm -v ${input_directory_path}:/input:ro -v ${output_directory_path}:/output position-coalescing
```

* `/input` must contain parquet files (subfolders are searched too).
* `/output` receives the result. Use an absolute path for both folders.

## Output

* `part_XXXX.parquet`: one file per bucket of users, with the columns `asof_ts, user_id, company_raw, company_linkedin_url, title_raw, location_raw, description, startdate, enddate, position_id`. The primary key is (`position_id`, `asof_ts`). If the input names the URL column `company_website`, it is written as `company_linkedin_url`.
* Only (`user_id`, `asof_ts`) pairs that exist in the input are written. Snapshots with no usable rows are discarded.
* `_state/`: saved matching state used for daily updates. Parquet readers ignore it.
* `_logs/`: dropped rows, dropped snapshots, match decisions and field changes. Written only when the container is started with `-e WRITE_LOGS=1`.

## Daily updates

Run the same command with the new day's parquet files as `/input` and the same `/output` folder as before. Only the buckets that contain affected users are rewritten, and the new rows are written to `part_XXXX_rNNNN.parquet`. A snapshot older than the latest one already processed for a user is skipped and logged. Running the same input again changes nothing. With an empty `/output` folder the run is a full initial run.

## Settings (optional environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `INPUT_DIR` | `/input` | folder with the parquet files |
| `OUTPUT_DIR` | `/output` | folder for the result |
| `WORKERS` | up to 4 | number of worker processes |
| `WRITE_LOGS` | `0` | set to `1` to write `_logs/` |
| `TARGET_BUCKET_ROWS` | `150000` | target number of rows per bucket |
| `SCRATCH_DIR` | system temp | where temporary bucket files are written |

Example: `docker run --rm -e WRITE_LOGS=1 -v ... -v ... position-coalescing`

## Code

* `main.py`: entry point.
* `src/pipeline.py`: splits users into buckets, runs the workers, writes output and state.
* `src/clean.py`: drops unusable rows and snapshots.
* `src/keys.py`: text, company, URL and description keys.
* `src/match.py`: the matching tiers and position IDs.
* `src/score.py`: an experimental similarity score. It is not used by `main.py`.
* `tests/`: tests (`pip install pytest`, then `python -m pytest -q`).
* `notebooks/explore_dataset.ipynb`: the data exploration that led to the design.
* `tools/`: scripts that reproduce the numbers in `docs/EXPLANATION.md`. Run them from the project folder with `PYTHONPATH=.` set:
  * `python tools/check_output.py OUTPUT INPUT`: row, position and snapshot counts, and the duplicate-key check
  * `python tools/checksum_output.py OUTPUT`: output checksum
  * `python tools/verify_dropped.py OUTPUT INPUT`: every missing snapshot is in the dropped log (needs `WRITE_LOGS=1`)
  * `python tools/find_duplicates.py OUTPUT`: possible duplicate positions (needs `WRITE_LOGS=1`)
  * `python tools/evaluate_accuracy.py INPUT`: synthetic precision and recall
  * `python tools/check_future_dates.py INPUT`: future start and end dates
  * `python tools/check_tier3_title_risk.py OUTPUT`: title changes in the URL + start tier
  * `python tools/check_acronym_candidates.py OUTPUT`: acronym company candidates

## Result on the 10M row sample (4 CPUs, one machine)

11,480,179 input rows became 12,931,257 output rows with 462,712 positions, in about 2 minutes (126 to 128 s) using about 0.9 GB per worker. The result is identical whether it is produced in one run or as an initial run followed by a daily update.