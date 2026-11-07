# Position coalescing: my approach

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
7. **Description with a missing start date:** one side is missing its start date, with additional company, URL, or title evidence.
8. **Description-based edit rule:** the company, title, and description match, but the start dates differ by no more than 12 months. The existing position must also have appeared in the preceding snapshot.
9. **Title-only row:** a row without a company or start date can only match an existing position that has no known company.
10. **Company or URL-only row:** a row with only a company or company URL, and no title or start date, can match only when exactly one known position exists at that company or URL.

Stronger evidence gets priority, and weaker evidence cannot override a stronger match.

### Important matching decisions

**Missing fields are never treated as evidence for matching.** A blank start date does not count as the same start date. Missing information is handled through explicit tiers rather than treating blanks as matching values.

**Descriptions only count as evidence once they are at least 40 characters long.** Short or generic descriptions cannot reliably identify one specific job. For example, "Intern" could apply to many different positions.

**Two different known start dates normally do not merge.** This is backed by a direct check, 2,703 groups shared the same company and title but had different start dates, a sample of 3 were read and all were really separate positions, not the same job. 
Tier 8 is the exception. It allows a match when:
- The company, title, and usable description are the same.
- The start dates differ by no more than 12 months.
- The existing position appeared in the preceding snapshot.

This is intended to handle a possible date correction or edit rather than treating every different date as a new job.

**Ambiguous matches are handled conservatively.** When a new row matches multiple existing positions, the system avoids guessing and creates a new position. If several candidates have the same newest company, title, and start date, the oldest created position wins as a deterministic tie-breaker.

I prioritized avoiding incorrect merges over forcing a match when the available evidence is ambiguous.

## 3. Hard cases and judgment calls

Some situations are difficult because different real-world jobs can have very similar information.

### The same company appears more than once

Why Tier 2 and Tier 3 allow different titles

Tier 2 and Tier 3 help identify positions whose titles change over time. Titles stayed the same 96.8 percent of the time across matched jobs. Of the 8,709 that did change, 44.5 percent were identical after cleanup, text noise only, 49.9 percent were genuinely different wording.
Someone might initially list their role as “Software Intern” and later update it to “Software Engineer Intern”. Requiring an exact title match might create duplicate positions instead of identifying the update.

The LinkedIn URL is missing in 44.5% of the rows, so it cannot always be relied on as the main matching signal. Company text is missing in 0.36% of rows, start date in 15.9%, and title in 1.0%. The URL is useful as additional evidence when company text changes.

A URL alone could merge different jobs that one person held at the same company. This is why Tier 3 also requires the start date.

Allowing different titles introduces some risk. 20.9 percent of jobs sit at a company where the same person holds 2 or more positions, which is exactly where this risk shows up. If someone has two different jobs at the same company with the same start date, the system could merge them when the second job appears in a later snapshot. If both jobs appear together in the first observation, they can remain separate because they are created as separate positions. This is a known limitation of using company and start date without requiring title agreement.

In the 20 examples I read, about half looked like real edits (Production Manager to Chief Operating Officer, Licensing Manager to People Compliance Manager, COO to Owner & COO) . A few looked doubtful (Graphic Design Internship becoming Operations Manager, and Designer grafico becoming Assistente de marketing). 

### Edited titles

Titles can change because of promotions, corrections, or changes in how someone describes their work. I therefore allow some tiers to match positions with different titles when other evidence is strong enough.

The trade-off is that a title change and a genuinely different role can look similar in the available data.

### Missing start dates

A missing start date makes matching harder because it removes one of the strongest signals. Instead of treating two missing dates as equal, I use separate tiers that require other evidence, such as company, title, URL, or description.

A blank start date combined with an altered title or company can still cause the same job to be split into separate positions.

### Rows with no company or title

A title-only row is particularly difficult to match because many people can have the same title. I only allow it to attach to an existing position with no known company.

Similarly, a company-only or URL-only row should not be attached when multiple positions could be candidates. It is only matched when there is exactly one possible existing position.

In these cases, creating a new position is safer than guessing and potentially combining two different jobs.

### The two assignment examples

For Case A, the system carries an existing position forward into later snapshots, even when it is not present in the latest observation. This preserves the user's previously observed work history instead of treating an absent row as proof that the position disappeared.

For Case B, the company LinkedIn URL and start date allow the system to identify the same position when the company name or title changes. For example, an edit from "RL" to "MLE" can still match through the URL-and-start-date tier when those fields remain the same. 
Once two observations are matched to be the same, I apply a simple precedence rule in teh apply_row function in teh src/match.py. The newest position's values always win, unless they are empty. We can see an example of Case B in the assignment.

- When both sides have a value and they are different, the newest value wins. Example: RL wins Revelio Labs
- When the new observation has a blank, the old value stays. Example: The old description "Making workforce data more accurate" stays
- When the observation has no value for a field but the new observation has, It fills the empty field.

## 4. Cleaning bad data

Before matching, the pipeline removes observations that cannot be used reliably.

The cleaning rules include:

- Invalid observation timestamps or dates.
- Start dates before 1950.
- End dates earlier than start dates.
- End dates more than five years after the observation snapshot.
- Rows with no useful information.

I also repair garbled text where possible.

A snapshot is only considered corrupted and dropped when no valid rows survive cleaning. If some rows are invalid but others are valid, the valid rows are still processed.

The original input data is not modified. Cleaning happens in the processing pipeline, and optional logs can record which rows were removed and why. This makes it possible to inspect discarded records without changing the source data.

2,474 of 3,941,416 snapshots were dropped, and all of them appear in the dropped log.

The `_state` and `_logs` folders are stored next to the output. They contain processing state and logs; they are not part of the position output, and readers ignore them.

## 5. Speed and scaling

I partition the data into buckets based on the user. All observations belonging to the same user go into the same bucket.

We need to keep a user's history together because matching relies on their past data. If we split it across workers, we would need to constantly synchronize that user's state. Keeping users in the same bucket allows different buckets to be processed in parallel.

The pipeline processes buckets in parallel, with a maximum of four workers. Each bucket maintains its own state, so workers can process different users independently.

The processing cost is expected to grow approximately linearly with the number of rows under a similar workload. However, the current implementation is limited by bucket size, available memory, and the resources of the machine. A large bucket or unusually large user can put pressure on a single worker, especially on a 16 GB machine.

In order to scale further, there would need to be changes in the design. The 100-billion-row estimate is a rough extrapolation, not a measured benchmark.

## 6. Daily updates

The pipeline supports incremental processing for daily updates. The history from the initial processing does not need to be rebuilt from the beginning.

When new snapshots arrive:

- The pipeline identifies which buckets are affected.
- Only those buckets need to be processed and rewritten.
- Snapshots older than the latest processed snapshot are skipped and logged because processing them would violate the chronological order.
- Re-running the same input does not create new positions or repeat completed work.

This makes daily updates cheaper than processing the entire dataset again.

## 7. How I checked the results

I used different checks to evaluate the implementation.

### Runtime and memory

In the latest run with logs enabled, the pipeline processed approximately 11.48 million input rows in 127.2 seconds. The split processing took 21.0 seconds. Peak worker memory was 875 MB.

The latest local run without logs took 126.2 seconds. The Docker runs took 127.5 seconds and 127.8 seconds.

The split run's initial pass had previously reached 2,125 MB. I have not investigated the cause of that higher memory usage, so I would not treat the lower memory figure as a guaranteed maximum.

The daily update took approximately 11.6 seconds, compared with 130.7 seconds for the initial processing run used in that comparison.

### Output and consistency across runs

The final output contained:

- 13,086,335 rows.
- 468,966 positions.
- Zero duplicate `(position_id, asof_ts)` keys.

I compared the checksums from the full run, the initial run followed by split processing, and the Docker runs. They matched.

The checksum was `17054104815118782646`.

The matching checksum between the full and split runs also supports the chronological processing approach: splitting the work did not change the final output in these tests. These checks provide evidence of consistency, not proof that every position was matched correctly.

### Duplicate-pair investigation

The latest duplicate-pair analysis reported 1,798 possible duplicate pairs. These are candidates identified by the analysis, not 1,798 confirmed errors or a total count of all duplicates.

The breakdown was:

- 530: description not shared when the later position was created.
- 415: start dates differ by more than 12 months, with the same company and title.
- 334: start date missing, with nothing else shared.
- 164: start edit within 12 months, but company or title changed.
- 137: start dates differ by more than 12 months, with company or title changed.
- 109: blocked by ambiguity because there was more than one candidate.
- 60: start edit within 12 months, but the old position was not seen in the previous snapshot.
- 49: start edit within 12 months, same company, and similar title.

This analysis helps explain why the remaining pairs were not automatically merged. Some lack enough shared evidence, while others could represent genuinely different jobs.

### Company-name suffix investigation and fix

I also investigated company-name variations involving legal suffixes such as "Ltd", "Limited", "Inc", "Corp", and "LLC".

The investigation found 1,965 candidate groups. I reviewed a random sample of 40 groups, and all 40 looked like the same job based on the information available. This was my judgment from the sample, not independent ground truth.

I then added legal-suffix removal to the company key so that names such as "Company Ltd" and "Company Limited" can be treated as the same company for matching.

After the fix, the candidate groups went from 1,965 to zero, and the output contained 2,138 fewer positions. This shows the effect of the normalization change. It does not prove that every removed position was a confirmed duplicate.

Some company-name differences can still remain, including abbreviations such as "BofA", spelling differences, translations, and differences between subsidiaries and parent companies.

### Title-edit investigation

The latest title-edit analysis found:

- Company + start: 90,322 matched rows. Of these, 30 had the same title after cleaning, 23,594 had similar titles, and 24,613 had different titles, and 42,085 had no title change at all.
- URL + start: 10,846 matched rows. Of these, 236 had the same title after cleaning, 278 had similar titles, and 504 had different titles, and 9,828 had no title change at all.

Together, the two tiers matched 25,117 rows with different titles, approximately 0.22% of the 11.48 million input rows.

This shows how many rows were matched despite having different titles. It is not a measured false-match rate. Some differences are legitimate title edits, while others could represent different roles.

### Rules versus a score

I also experimented with a separate scoring approach. It was precise on the cases where it found a candidate, but its coverage was low. The experiment did not test the false-merge rate for genuinely new positions, so it could not establish how safely the score distinguishes different jobs.

I chose the ordered rules for the main matcher because they are easier to understand and explain: each tier has specific evidence requirements, and the stronger evidence is checked first.

I did not compare the rule-based matcher and the scoring approach on a labeled set of real matching and non-matching pairs. Therefore, I cannot claim that one has better overall accuracy than the other.

### Synthetic test and manual review

On the synthetic test, the matcher achieved 0.9936 precision and 0.975 recall. These are results on synthetic data, not measurements of real-world accuracy.

Most of the synthetic splits came from a blank start date combined with an altered title or company. There were also 30 merged IDs that I could not explain, so the test still has cases that need investigation.

I also used a small manual review with assistance to inspect matching examples. The verdicts were prefilled by an AI assistant, so this was not an independent manual evaluation.

The dataset does not provide ground-truth labels for whether every pair of observations represents the same real-world job. Therefore, I cannot claim a measured overall precision or recall for the real dataset.

## 8. Limits and what I would do next

There are several limitations in the current approach.

- **Thresholds are judgment calls:** the 40-character description threshold, 0.7 title similarity threshold, and 12-month date window were selected as practical rules. They were not tuned against a labeled ground-truth dataset.
- **Rehires can remain separate:** if someone leaves a company and returns with a different start date, the system normally treats the return as a separate position. This is intentional because the two periods may represent different jobs.
- **Some company-name variations can remain:** legal suffixes are now handled, but abbreviations, spelling differences, translations, and subsidiaries can still prevent a match.
- **Blank start dates can cause false splits:** when a start date is missing and the title or company also changes, the system may not have enough evidence to recognize the same job.
- **Title abbreviations can cause false splits:** if the title is abbreviated and the company and URL also change, the available matching signals may not be strong enough.
- **Two real roles can be merged:** company and start date can be insufficient when someone has multiple roles at the same company with the same start date.
- **State files are Python-specific:** the current state uses Python serialization, which limits portability and makes it less suitable as a long-term distributed state format.
- **Memory varies:** worker memory depends on the bucket and workload. The split run's initial pass reached 2,125 MB, and I have not investigated the cause.
- **There is no ground-truth accuracy measurement:** the available checks do not prove the real-world precision or recall of the matcher.
- **Acronym investigation:** I considered to make the matching logic to catch abbrevations like RL stands for Revelio Labs when company linkedin URL is not present. I tested this by scanning the full output that qualify for that case and I found 131 candidate pairs across 468,966 positions. The number of clean, useful cases is under 40 from almost half a million positions. I decided against adding this as a matching tier. 

My next improvements would be to create a labeled evaluation set, inspect ambiguous matches more systematically, and investigate the unexplained synthetic merged IDs and memory spike. I would also consider using a scoring model to help rank candidates when several positions are plausible. I would not replace the current rules with a score until it had been evaluated against labeled examples.

The analysis scripts used for these investigations are not included in the submitted zip.

## 9. What I would change for 100 billion rows

The current implementation would need architectural changes before it could handle 100 billion rows.

Using the latest local run without logs, 11.48 million rows took 126.2 seconds, or approximately 91,000 rows per second. If that rate stayed constant, processing 100 billion rows would take roughly 13 days on one machine. With 100 machines and perfectly linear scaling, it would take approximately three hours.

These are rough extrapolations. They assume the same processing rate and linear scaling, and ignore data skew, I/O, communication between machines, and other overhead. Actual processing time would likely be higher.

First, I would replace the Python-specific state files with a more scalable storage format, such as Parquet for batch-oriented data or a key-value store for state that needs frequent lookups and updates.

Second, I would use multi-stage partitioning. Partitioning by user is necessary to keep a user's history together, but at this scale I would also need a strategy for distributing large partitions and handling skewed users.

Third, I would move processing to a distributed environment with many machines rather than relying on four local workers.

I would also introduce state compaction, more robust recovery, and coordination for concurrent updates.

The current system demonstrates chronological matching, stable IDs, parallel bucket processing, and incremental updates. Those are useful foundations, but they do not mean the existing implementation can directly scale to 100 billion rows.