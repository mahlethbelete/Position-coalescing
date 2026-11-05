
**Outline for your explanation (write each part in your own words):**
1. **Problem and approach:** what a position is, no future information, and a stable `position_id`.
2. **Matching:**
   * Tiers from strongest to weakest evidence.
   * Missing fields never count as evidence.
   * Descriptions count only at 40 or more characters.
   * Two different starts never merge, except the 12 month edit rule.
3. **Hard cases:** same company twice, edited titles, blank start, blank title and title only rows. Explain why you chose a new position over a guess.
4. **Cleaning:** which rows are dropped and why, that originals stay untouched, and the optional logs.
5. **Scale:** buckets by user, 4 workers, state per user, and cost that grows linearly with rows. Say the 100B estimate is rough, not measured.
6. **Daily updates:** the `_state` folder, only the affected buckets are rewritten, late snapshots are skipped and logged, and a rerun of the same input does nothing.
7. **Evidence you measured:**
   * 11.48M rows in about 145 s, with about 1 GB per worker.
   * Daily update 9.6 s against 138 s.
   * Checksums match between the full run, the daily update and Docker.
   * Duplicate pairs went from 47,609 to 1,805.
   * The manual review is small and was done with help.
8. **Limits:**
   * Thresholds are judgment calls, not tuned on labeled data.
   * Rehires with different starts stay separate.
   * Company spelling variants can leave duplicates.
   * The same company and same start can merge two real roles.
   * The state files are Python specific.
   * Memory varies from 1 to 2.2 GB.
9. **At 100B rows:** a parquet or key value state store, multi stage partitioning and many machines.




# Position coalescing: my approach

## 1. The problem and my goal
A position refers to one job in a person's work history. The input contains observations of those jobs at different times. Each observation may be incomplete or its columns might change.
My goal is to combine thsoe observations that refer to teh same job while preserving the work history of users at previous observations.


## 2. How matching works

I used different matching tiers. The code now checks the tiers, from stronger to weaker evidence, and accepts the first match that qualifies.
1. 

## 3. Hard cases and judgment calls
## 4. Cleaning bad data
## 5. Speed and scaling
## 6. Daily updates
## 7. How I checked accuracy
## 8. Limits and what I would do next