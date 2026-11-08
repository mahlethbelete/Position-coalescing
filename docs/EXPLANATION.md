# Position coalescing

## 1. The problem and my goal

A position refers to one job in a person's work history. The input contains observations of those jobs at different times. Each observation may be incomplete or its columns might change.

My goal is to combine those observations that refer to the same job while preserving genuinely different positions.

Two types of errors are possible:

- **False split:** observations of the same job are treated as separate positions.
- **False merge:** two different jobs are combined into one position.

I designed the matching rules to reduce both, while being particularly careful about false merges because they can destroy information about someone's work history.

There are two important principles behind my approach:

- **No future information:** a position can only be matched using information available at that point in time. This means snapshots must be processed chronologically. A later observation cannot change an earlier matching decision.
- **Stable position ID:** a position ID is created once when the job is first seen. Once assigned, it is never regenerated, rewritten, or edited. It is reused whenever the same position is identified in a later snapshot.

## 2. How matching works

I use an ordered set of matching tiers. The code checks the tiers from strongest to weakest evidence and accepts the first match that produces an unambiguous result.

The matching tiers are:

1. **Company, title, and start date:** all three fields match.
2. **Company and start date:** allows the title to have changed.
3. **Company LinkedIn URL and start date:** uses the company URL when company text may have changed.
4. **Company and title:** matches when one observation is missing its start date.
5. **Start date and similar title:** the start date matches and the title similarity is at least 0.7, or one title is a prefix of the other.
6. **Start date and description:** both fields match, and the description is usable.
7. **Matching when a start date is missing:** one side is missing its start date, with additional company, URL, or title evidence.
8. **Matching with a start date change:** The company, title, and description match, and the start dates are within 12 months of each other. The existing position must also have appeared in the previous snapshot.
9. **Title-only row:** a row without a company or start date can only match an existing position that has no known company.
10. **Company or URL-only row:** a row with only a company or company URL, and no title or start date, can match only when exactly one known position exists at that company or URL.

Stronger evidence gets priority, and weaker evidence cannot override a stronger match.

### Important matching decisions

**Missing fields are never treated as evidence for matching.** For example, two blank start dates are not considered a match. The rules need other information to decide that two records belong to the same position.

**Descriptions need to be at least 40 characters long to count as evidence.** Short or generic descriptions cannot reliably be used to identify a specific job. For example, "Intern" could describe many different positions. I chose 40 characters as a practical starting point to filter out short or generic descriptions. I haven't tested different thresholds against labeled data, so I can't say whether 40 is the best cutoff.

**Different start dates usually mean different positions.** I checked 2,703 groups that share the same company and title but had different start dates. I reviewed a sample of three, and all three were separate positions. This is not a proof that different start dates always mean different jobs. I used it as supporting evidence.

Tier 8 is the exception. It allows a match when:

- The company, title, and usable description are the same.
- The start dates differ by no more than 12 months.
- The existing position appeared in the previous snapshot.

This is intentional so that it can handle a possible date correction or edit without creating a new position every time the date changes.

**When there are multiple possible matches, the system avoids guessing.** When a new row matches more than one existing position, it creates a new position. There is one fallback. If the candidates have the same newest company, title, and start date, it chooses the oldest position.

I chose to leave uncertain matches separate rather than risk merging two different jobs.

## 3. Hard cases and judgment calls

Some situations are difficult because different real-world jobs can have very similar information.

### Why Tier 2 and Tier 3 allow different titles

Tier 2 and Tier 3 help identify positions whose titles change over time. Titles stayed the same 96.8 percent of the time across matched jobs. Of the 8,709 that did change, 44.5 percent were identical after cleanup, text noise only, 49.9 percent were genuinely different wording.
Someone might initially list their role as “Software Intern” and later update it to “Software Engineer Intern”. Requiring an exact title match might create duplicate positions instead of identifying the update.

The LinkedIn URL is missing in 44.5% of the rows, so it cannot always be relied on as the main matching signal. Company text is missing in 0.36% of rows, start date in 15.9%, and title in 1.0%. The URL is useful as additional evidence when company text changes.

A URL alone could merge different jobs that one person held at the same company. This is why Tier 3 also requires the start date.

Allowing different titles introduces some risk. 20.9 percent of jobs sit at a company where the same person holds 2 or more positions, which is exactly where this risk shows up. If someone has two different jobs at the same company with the same start date, the system could merge them when the second job appears in a later snapshot. If both jobs appear together in the first observation, they can remain separate because they are created as separate positions. This is a limitation of matching on company and start date without requiring the title to match.

In the 20 examples I read, about half looked like real edits (Production Manager to Chief Operating Officer, Licensing Manager to People Compliance Manager, COO to Owner & COO) . A few looked doubtful (Graphic Design Internship becoming Operations Manager, and Designer grafico becoming Assistente de marketing).

### Missing start dates

A missing start date makes matching harder because it removes one of the strongest signals. Instead of treating two missing dates as equal, I use separate tiers that require other evidence, such as company, title, URL, or description.

A blank start date combined with an altered title or company can still cause the same job to be split into separate positions.

### Rows with no company or title

Rows with only a title are difficult to match because many different positions can have the same title. I only match these rows to an existing position if that position also has no known company.

For rows with only a company or URL, I only match when there is exactly one possible existing position. If multiple positions could match, I leave the row unmatched rather than guess.

I would rather create a new ID than attach the row to the wrong job.

### The two assignment examples

For Case A, When a position appears in an earlier snapshot but is missing from a later one, the system carries it forward. Just because it wasn't not in the latest snapshot, it doesn't automatically mean the person left that job.

For Case B, When a company name or title changes, the system can still identify the position using other fields. For example, if the company LinkedIn URL and start date stay the same, the URL and start date matching tier can recognize the same position even if the company name changes from "Revelio Labs" to "RL".
Once two observations are matched to the same position, the apply_row function in src/match.py updates its values using the following rules.

- If both observations have different values, the newer value wins. Example: Revelio Labs is replaced with RL
- If the new observation has a blank, the old value stays. Example: The old description "Making workforce data more accurate" stays
- If the observation has a blank value and the new observation provides one, the new value fills the gap.

## 4. Cleaning bad data

Before matching, the pipeline removes observations that cannot be used reliably.

The cleaning rules include:

- Invalid observation timestamps or dates.
- Start dates before 1950.
- End dates earlier than start dates.
- End dates more than five years after the observation snapshot.
- Rows with no useful information.

I also fix garbled text where possible.

An invalid row doesn't mean the whole snapshot gets dropped. If other valid rows remain, I keep and process them. I only drop the entire snapshot when no valid rows are left.

In one run, 2,474 out of 3,941,416 snapshots were dropped. All 2,474 were recorded in the dropped log.

The original input files remain unchanged. Cleaning happens during processing, and optional logs record which rows were removed and why.

The pipeline also creates `_state` and `_logs` folders next to the output. `_state` contains the saved position data needed for later updates, while `_logs` contains processing logs. Neither folder is part of the final position output.

## 5. Speed and scaling

I split the data into buckets based on the `user_id`. All observations belonging to the same user go into the same bucket.

This matters because matching depends on a user's previous observations. If their history were split across different workers, those workers would need access to the same user's matching state. Keeping each user's data in one bucket avoids that problem.

The pipeline processes buckets in parallel, using a maximum of four workers. Each worker processes a separate bucket and maintains the state for the users in that bucket.

In my latest local run, processing 11.48 million input rows took 126.2 seconds. The two Docker runs took 127.5 and 127.8 seconds. I haven't tested enough different dataset sizes to establish how processing time grows as the input increases.

The current implementation also has limitations. Large buckets can require more memory and take longer to process, leaving other workers waiting for them to finish. The number of workers is also limited by the available machine resources.

In order to scale further, changes to how data and state are distributed and processed are required.

## 6. Daily updates

The pipeline supports incremental processing for daily updates. The history from the initial processing does not need to be rebuilt from the beginning.

When new snapshots arrive:

- New input is split into buckets, and only buckets with input files are processed.
- Only those buckets need to be processed and rewritten.
- Snapshots older than the latest processed snapshot are skipped and logged because processing them would violate the chronological order.
- Previously assigned position IDs are retained through the saved state, so existing positions can continue across runs.

This avoids rebuilding the full history for every update. But the pipeline still processes the full contents of each affected bucket instead of just updating only the users who have new snapshots.

## 7. How I checked the results

I checked the runtime, output, and matching results.

### Runtime and memory

In the latest run with logs enabled, the pipeline processed approximately 11.48 million input rows in 127.2 seconds. Splitting the input into buckets took 21.0 seconds, and peak worker memory was 875 MB.

The latest local run without logs took 126.2 seconds. The Docker runs took 127.5 seconds and 127.8 seconds.

An earlier run reached 2,125 MB during the initial split. I haven't investigated why memory usage was higher in that run, so 875 MB can't be treated as a guaranteed maximum.

For the daily update comparison, processing took approximately 11.6 seconds, compared with 130.7 seconds for the initial run.

### Output and consistency across runs

The final output contained:

- 13,086,335 rows.
- 468,966 positions.
- Zero duplicate `(position_id, asof_ts)` keys.

I used a checksum script to compare the outputs from the full run, split processing, and Docker runs. It calculated a hash for each output row and added the hashes into one value. All three produced the same row count and checksum (`17054104815118782646`).

This shows that the results were consistent across runs but it does not prove that every position was matched correctly.

### Remaining duplicate candidates

I ran the latest duplicate-pair analysis and it returned 1,798 possible duplicates. These were just potential matches to review, not confirmed errors.

The breakdown was:

- 530: description not shared when the later position was created.
- 415: start dates differ by more than 12 months, with the same company and title.
- 334: start date missing, with nothing else shared.
- 164: start edit within 12 months, but company or title changed.
- 137: start dates differ by more than 12 months, with company or title changed.
- 109: blocked by ambiguity because there was more than one candidate.
- 60: start edit within 12 months, but the old position was not seen in the previous snapshot.
- 49: start edit within 12 months, same company, and similar title.

These cases explain why the existing rules did not merge the pairs. Some lack enough shared evidence, and the others maybe different jobs.

### Company-name suffix investigation and fix

I also investigated company names involving legal suffixes such as Ltd, Limited, Inc, Corp, and LLC.

The investigation found 1,965 candidate groups. I reviewed a random sample of 40 groups, and all 40 looked like the same job based on the information available. This was my judgment from the sample, not independent ground truth.

I added legal-suffix removal to the company key so that names such as "Company Ltd" and "Company Limited" can be treated as the same company for matching.

After the change, the candidate groups dropped from 1,965 to zero, and the output contained 2,138 fewer positions. I didn't manually verify every affected position, so I am not sure if all of those reductions were correct.

Some company-name differences can still remain, including abbreviations such as "BofA", spelling differences, translations, and differences between subsidiaries and parent companies.

### Title-edit investigation

The latest title-edit analysis found:

- Company + start: 90,322 matched rows. Of these, 30 had the same title after cleaning, 23,594 had similar titles, and 24,613 had different titles, and 42,085 had no title change at all.
- URL + start: 10,846 matched rows. Of these, 236 had the same title after cleaning, 278 had similar titles, and 504 had different titles, and 9,828 had no title change at all.

Together, these tiers matched 25,117 rows with different titles, approximately 0.22% of the 11.48 million input rows. Some differences may be legitimate title edits, but others could be incorrect merges. I don't have labels to determine how many belong to each group.

### Rules versus a score

I experimented with a separate scoring approach. It was precise on the cases where it found a candidate, but its coverage was low. I also hadn't tested its false-merge rate on genuinely new positions.

I kept the ordered rules for the main matcher because each tier has specific evidence requirements, and the matching process is easier to follow.

I haven't compared both approaches using a labeled set of matching and non-matching examples, so I can't say which would perform better overall.

### Synthetic test and manual review

On the synthetic test, the matcher achieved 0.9936 precision and 0.975 recall. These are results on synthetic data, not measurements of real-world accuracy.

Most of the synthetic splits came from a blank start date combined with an altered title or company. There were also 30 merged IDs that I could not explain, so the test still has cases that need investigation.

I also manually reviewed a sample of matching examples across several users. The cases I found consistent with the limitations already described below, including the 12 month start edit window and the risk of a position becoming disconnected from its own later history.

The dataset does not provide ground-truth labels for whether every pair of observations represents the same real-world job. Therefore, I cannot claim a measured overall precision or recall for the real dataset.

## 8. Limits and what I would do next

The current matching rules work for the cases I tested, but there are still situations where the available information is not enough to identify a position confidently.

- The 40-character description threshold, 0.7 title similarity threshold, and 12-month date window were selected as practical starting points. I haven't tested different values against labeled data so I can't say these are the best thresholds.
- If someone leaves a company and later returns, will usually create a separate position because the start date is different. I kept this logic because a return could be a truly new job, and I don't have enough evidence to assume it is the same one.
- I added normalization for legal suffixes such as Ltd and Inc, but other differences like subsidiary names, abbrevations or spelling differences can still cause problems.
- When a start date is missing and the title or company also changes, matching becomes difficult. The system may create a new position even when the observation refers to an existing job.
- If the title is abbreviated and the company and URL also change, the available matching signals may not be strong enough.
- Another risk is when someone holds two different roles at the same company with the same start date. Since some tiers rely on company and start date, teh system could combine those roles incorrectly.
- The current state uses Python serialization. It works for the current implementation but it is harder to use across different languages and in a distributed environmnet which leads to considering more portable storage format.
- Memory usage also needs more investigation. Most recent runs used around 875 MB of peak worker memory, but an earlier split run reached 2,125 MB during its initial pass. I haven't identified why it was higher in that run.
- I don't have labeled real-world data showing which observations belong to the same job. So I just reported runtime, consistency checks, manual checks and synthetic tests.
- I also considered adding acronym matching for cases where the company LinkedIn URL is missing, such as matching "RL" to "Revelio Labs". I tested this by scanning the full output that qualify for that case and I found 131 candidate pairs across 468,966 positions. The number of clean, useful cases is under 40 from almost half a million positions. I decided not to add this as a matching tier because it could lead to incorrect merges alone.

My next step would be to build a labeled dataset of matching and non-matching examples from real observations. This would let me measure precision and recall, test different thresholds, and compare the current tier-based approach with the scoring approach I experimented with. I would also review the ambiguous matches to see whether additional evidence could resolve some of them without increasing false merges.

Beyond matching accuracy, I would investigate the 30 unexplained merged IDs in the synthetic test and the memory spike from the earlier split run. For larger datasets, I would also look at reducing the amount of state each worker needs to load and exploring a more scalable way to store and access position state than Python serialization.

The analysis scripts used for these investigations are not included in the submitted zip.

## 9. What I would change for 100 billion rows

The current implementation would need architectural changes before it could handle 100 billion rows.

Using the latest local run without logs, 11.48 million rows took 126.2 seconds, or approximately 91,000 rows per second. If that rate stayed constant, processing 100 billion rows would take approximately 13 days on one machine. With 100 machines and perfectly linear scaling, it would take approximately three hours.

These are rough guesses. They assume the same processing rate and linear scaling, communication between machines, and other overhead. Actual processing time would likely be higher.

First, I would replace Python serialization for storing position state. It works for the current implementation, but loading and rewriting large state files would become expensive at this scale. I would investigate a key-value store for looking up and updating individual users' position state, while using Parquet for storing larger batches of historical data.

Second, I would keep partitioning by user so that all observations for one user are processed together. I would also improve workload balancing so that large partitions do not leave some workers with significantly more work than others.

Third, I would move from multiprocessing on one machine to distributed processing across multiple machines. Each machine could process different partitions, allowing the workload to be spread across a larger cluster.

I would also introduce state compaction, more robust recovery, and coordination for concurrent updates.

The current system demonstrates chronological matching, stable IDs, parallel bucket processing, and incremental updates. However, the current implementation would need significant changes before it could handle 100 billion rows.
